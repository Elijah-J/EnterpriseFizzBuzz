"""
Enterprise FizzBuzz Platform - Recommendation Engine Module

"Because you evaluated 15, you might enjoy 45."

Implements a Netflix-style recommendation engine for integers, featuring:
- NumberFeatures: rich feature extraction for every number (parity, primality,
  Fibonacci membership, zodiac sign via n%12, and digit sum)
- UserProfile: tracks evaluated numbers and builds preference vectors
- CollaborativeFilter: cosine similarity on a user-item interaction matrix
- ContentBasedFilter: feature-vector similarity between numbers
- HybridBlender: 60/40 weighted blend with serendipity injection
- ColdStartHandler: popular-items fallback for new users
- RecommendationExplainer: human-readable explanations for why a number was
  recommended ("Because you evaluated 15 (FizzBuzz, Aries)...")
- RecommendationEngine: orchestrator that ties all components together
- RecommendationDashboard: ASCII dashboard for recommendation analytics

This module provides comprehensive number profiling and delivers
personalized evaluation recommendations tailored to each user's
history, preferences, and arithmetic engagement patterns.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ZODIAC_SIGNS: list[str] = [
    "Aries", "Taurus", "Gemini", "Cancer",
    "Leo", "Virgo", "Libra", "Scorpio",
    "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]


# ---------------------------------------------------------------------------
# Number Feature Extraction
# ---------------------------------------------------------------------------

def _is_perfect_square(n: int) -> bool:
    """Check if n is a perfect square (non-negative)."""
    if n < 0:
        return False
    root = int(math.isqrt(n))
    return root * root == n


def _is_prime(n: int) -> bool:
    """Determine primality using trial division.

    For the Enterprise FizzBuzz Platform, this is more than sufficient.
    We considered implementing AKS or Miller-Rabin, but decided that
    deterministic trial division better reflects the straightforward
    nature of the problem we're over-engineering.
    """
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


def _is_fibonacci(n: int) -> bool:
    """Check Fibonacci membership using the classic mathematical identity.

    A number n is a Fibonacci number if and only if 5n^2 + 4 or 5n^2 - 4
    is a perfect square. This was proven by Ira Gessel in 1972, and it
    remains one of the most satisfying closed-form membership tests in
    all of recreational mathematics. We are using it to recommend integers.
    """
    if n < 0:
        return False
    discriminant = 5 * n * n
    return _is_perfect_square(discriminant + 4) or _is_perfect_square(discriminant - 4)


def _digit_sum(n: int) -> int:
    """Compute the digit sum of the absolute value of n."""
    return sum(int(d) for d in str(abs(n)))


def _zodiac_sign(n: int) -> str:
    """Assign a zodiac sign to a number based on n % 12.

    Because every integer deserves an astrological identity. The mapping
    is deterministic and utterly meaningless, which makes it a perfect
    fit for a recommendation engine feature vector.
    """
    return ZODIAC_SIGNS[abs(n) % 12]


def _fizzbuzz_label(n: int) -> str:
    """Compute the canonical FizzBuzz classification for a number."""
    if n % 15 == 0:
        return "FizzBuzz"
    if n % 3 == 0:
        return "Fizz"
    if n % 5 == 0:
        return "Buzz"
    return str(n)


@dataclass(frozen=True)
class NumberFeatures:
    """Rich feature vector for a single integer.

    Every number in the FizzBuzz universe is characterized by five
    features that collectively define its "personality":
    - parity: 0 for even, 1 for odd (the most fundamental personality trait)
    - is_prime: 1 if prime, 0 otherwise (the introverts of the number line)
    - is_fibonacci: 1 if Fibonacci, 0 otherwise (the golden-ratio enthusiasts)
    - zodiac_index: n%12, mapping to one of 12 zodiac signs
    - digit_sum: sum of digits (a number's "vibe check")

    Together these features allow the recommendation engine to compute
    meaningful (citation needed) similarity between any two integers.
    """

    number: int
    parity: int              # 0=even, 1=odd
    is_prime: int            # 0 or 1
    is_fibonacci: int        # 0 or 1
    zodiac_index: int        # 0..11
    digit_sum: int

    @property
    def zodiac_sign(self) -> str:
        return ZODIAC_SIGNS[self.zodiac_index]

    @property
    def fizzbuzz_label(self) -> str:
        return _fizzbuzz_label(self.number)

    def to_vector(self) -> list[float]:
        """Convert to a numeric feature vector for similarity computation."""
        return [
            float(self.parity),
            float(self.is_prime),
            float(self.is_fibonacci),
            float(self.zodiac_index) / 11.0,   # Normalize to [0, 1]
            float(self.digit_sum) / 45.0,       # Max digit sum for reasonable numbers
        ]

    @staticmethod
    def extract(n: int) -> NumberFeatures:
        """Extract the full feature profile for a number.

        This is the core feature engineering step. In a real recommendation
        system, this would involve deep learning embeddings, graph neural
        networks, and a team of 12 data scientists. Here, it involves
        modulo arithmetic and a zodiac lookup table.
        """
        return NumberFeatures(
            number=n,
            parity=n % 2,
            is_prime=1 if _is_prime(n) else 0,
            is_fibonacci=1 if _is_fibonacci(n) else 0,
            zodiac_index=abs(n) % 12,
            digit_sum=_digit_sum(n),
        )


# ---------------------------------------------------------------------------
# User Profile
# ---------------------------------------------------------------------------

@dataclass
class UserProfile:
    """Tracks a user's FizzBuzz evaluation history and preference vector.

    Every user of the Enterprise FizzBuzz Platform deserves a rich
    behavioral profile that captures their number evaluation preferences.
    The preference vector is the centroid of all evaluated numbers' feature
    vectors, because apparently we need collaborative filtering for modulo
    arithmetic.
    """

    user_id: str
    evaluated_numbers: list[int] = field(default_factory=list)
    _feature_cache: dict[int, NumberFeatures] = field(
        default_factory=dict, repr=False
    )

    def record_evaluation(self, number: int) -> None:
        """Record that the user evaluated a number.

        In the real world, this would trigger a Kafka event, update a
        feature store, and retrain an embedding model. Here, it appends
        to a list.
        """
        if number not in self.evaluated_numbers:
            self.evaluated_numbers.append(number)
        if number not in self._feature_cache:
            self._feature_cache[number] = NumberFeatures.extract(number)

    @property
    def preference_vector(self) -> list[float]:
        """Compute the user's preference vector as the centroid of evaluated number features.

        If the user has evaluated no numbers, returns a zero vector.
        The centroid approach assumes that a user's taste in integers is
        the average of all integers they've tasted, which is about as
        scientifically valid as recommending movies based on average
        runtime of films you've watched.
        """
        if not self.evaluated_numbers:
            return [0.0] * 5

        vectors = []
        for n in self.evaluated_numbers:
            if n not in self._feature_cache:
                self._feature_cache[n] = NumberFeatures.extract(n)
            vectors.append(self._feature_cache[n].to_vector())

        dim = len(vectors[0])
        centroid = [0.0] * dim
        for v in vectors:
            for i in range(dim):
                centroid[i] += v[i]
        count = len(vectors)
        return [c / count for c in centroid]

    def get_features(self, number: int) -> NumberFeatures:
        """Get cached features for a number, computing if needed."""
        if number not in self._feature_cache:
            self._feature_cache[number] = NumberFeatures.extract(number)
        return self._feature_cache[number]


# ---------------------------------------------------------------------------
# Similarity Computation
# ---------------------------------------------------------------------------

def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors.

    cos(theta) = dot(a, b) / (||a|| * ||b||)

    Returns 0.0 if either vector has zero norm, because the cosine of
    the angle between nothing and something is philosophically undefined
    but practically zero. We choose pragmatism over existential crisis.
    """
    if len(a) != len(b):
        return 0.0

    dot_product = sum(ai * bi for ai, bi in zip(a, b))
    norm_a = math.sqrt(sum(ai * ai for ai in a))
    norm_b = math.sqrt(sum(bi * bi for bi in b))

    if norm_a < 1e-12 or norm_b < 1e-12:
        return 0.0

    return dot_product / (norm_a * norm_b)


# ---------------------------------------------------------------------------
# Collaborative Filter
# ---------------------------------------------------------------------------

class CollaborativeFilter:
    """User-based collaborative filtering for FizzBuzz recommendations.

    "Users who evaluated 15 also evaluated 30, 45, and 60."

    This implements classic user-based collaborative filtering with cosine
    similarity on the user-item interaction matrix. In production systems,
    this would use matrix factorization (SVD, ALS) or deep collaborative
    filtering. Here, it uses nested for-loops on Python lists, which is
    arguably more honest about what's actually happening.
    """

    def __init__(self, max_similar_users: int = 10) -> None:
        self._max_similar_users = max_similar_users

    def find_similar_users(
        self,
        target: UserProfile,
        all_users: list[UserProfile],
    ) -> list[tuple[UserProfile, float]]:
        """Find the most similar users to the target, ranked by cosine similarity.

        Returns a list of (user, similarity_score) tuples, sorted by
        descending similarity. The target user is excluded because
        recommending yourself to yourself, while philosophically
        interesting, is not useful.
        """
        target_vec = target.preference_vector
        similarities: list[tuple[UserProfile, float]] = []

        for user in all_users:
            if user.user_id == target.user_id:
                continue
            if not user.evaluated_numbers:
                continue
            sim = cosine_similarity(target_vec, user.preference_vector)
            similarities.append((user, sim))

        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[: self._max_similar_users]

    def recommend(
        self,
        target: UserProfile,
        all_users: list[UserProfile],
        n: int = 5,
    ) -> list[tuple[int, float]]:
        """Generate recommendations based on similar users' evaluations.

        For each number evaluated by similar users but NOT by the target,
        compute a weighted score based on how similar the recommending
        user is. Returns (number, score) tuples sorted by descending score.
        """
        similar_users = self.find_similar_users(target, all_users)
        if not similar_users:
            return []

        evaluated_set = set(target.evaluated_numbers)
        candidate_scores: dict[int, float] = {}

        for user, sim in similar_users:
            if sim <= 0.0:
                continue
            for num in user.evaluated_numbers:
                if num not in evaluated_set:
                    candidate_scores[num] = candidate_scores.get(num, 0.0) + sim

        ranked = sorted(candidate_scores.items(), key=lambda x: x[1], reverse=True)
        return ranked[:n]


# ---------------------------------------------------------------------------
# Content-Based Filter
# ---------------------------------------------------------------------------

class ContentBasedFilter:
    """Content-based filtering using number feature vectors.

    "Because 45 shares features with 15: both are FizzBuzz, both are
    divisible by 3 and 5, and both are Aries."

    This recommends numbers whose feature vectors are most similar to the
    user's preference vector (centroid of their evaluated numbers). It's
    the recommendation equivalent of "you liked apples, so here are more
    apples" — reliable but predictable.
    """

    def recommend(
        self,
        profile: UserProfile,
        candidate_pool: list[int],
        n: int = 5,
    ) -> list[tuple[int, float]]:
        """Generate recommendations based on feature similarity to user preferences.

        Computes cosine similarity between each candidate's feature vector
        and the user's preference vector. Excludes already-evaluated numbers.
        """
        pref_vec = profile.preference_vector
        evaluated_set = set(profile.evaluated_numbers)

        scored: list[tuple[int, float]] = []
        for num in candidate_pool:
            if num in evaluated_set:
                continue
            features = NumberFeatures.extract(num)
            sim = cosine_similarity(pref_vec, features.to_vector())
            scored.append((num, sim))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:n]


# ---------------------------------------------------------------------------
# Hybrid Blender
# ---------------------------------------------------------------------------

class HybridBlender:
    """Blends collaborative and content-based recommendations with serendipity.

    The hybrid approach combines the strengths of both filtering strategies:
    collaborative filtering captures social proof ("everyone loves 15"),
    while content-based filtering captures intrinsic number properties
    ("you like primes, here are more primes"). The serendipity factor
    randomly injects low-similarity items to "break filter bubbles,"
    because even in FizzBuzz, echo chambers are a concern.

    Default blend: 60% collaborative, 40% content-based, with 10%
    serendipity injection. These ratios were determined through extensive
    A/B testing (they were not).
    """

    def __init__(
        self,
        collaborative_weight: float = 0.6,
        content_weight: float = 0.4,
        serendipity_factor: float = 0.1,
        rng: random.Random | None = None,
    ) -> None:
        self._collab_weight = collaborative_weight
        self._content_weight = content_weight
        self._serendipity = serendipity_factor
        self._rng = rng or random.Random()

    def blend(
        self,
        collaborative_recs: list[tuple[int, float]],
        content_recs: list[tuple[int, float]],
        candidate_pool: list[int],
        evaluated_set: set[int],
        n: int = 5,
    ) -> list[tuple[int, float]]:
        """Blend recommendations from both strategies.

        Each candidate's blended score is:
            score = collab_weight * collab_score + content_weight * content_score

        After scoring, serendipity injection may replace some items with
        random candidates from the pool, because nothing says "personalized
        recommendation" like randomly suggesting the number 37 to someone
        who clearly prefers multiples of 5.
        """
        collab_dict = dict(collaborative_recs)
        content_dict = dict(content_recs)

        all_candidates = set(collab_dict.keys()) | set(content_dict.keys())
        blended: dict[int, float] = {}

        for num in all_candidates:
            c_score = collab_dict.get(num, 0.0)
            t_score = content_dict.get(num, 0.0)
            blended[num] = (
                self._collab_weight * c_score + self._content_weight * t_score
            )

        ranked = sorted(blended.items(), key=lambda x: x[1], reverse=True)[:n]

        # Serendipity injection: replace some items with random picks
        if self._serendipity > 0 and ranked and candidate_pool:
            available = [
                c for c in candidate_pool
                if c not in evaluated_set and c not in blended
            ]
            if available:
                num_inject = max(1, int(len(ranked) * self._serendipity))
                for _ in range(num_inject):
                    if not available or not ranked:
                        break
                    inject = self._rng.choice(available)
                    available.remove(inject)
                    # Replace the lowest-scored item
                    ranked[-1] = (inject, 0.01)  # Serendipity score is low but nonzero

        return ranked


# ---------------------------------------------------------------------------
# Cold Start Handler
# ---------------------------------------------------------------------------

class ColdStartHandler:
    """Handles the cold-start problem for new users with insufficient history.

    When a user has evaluated fewer numbers than the minimum required for
    personalized recommendations, the engine falls back to popular items.
    In the FizzBuzz domain, "popular" means numbers that are divisible by
    both 3 and 5 (the FizzBuzz numbers), because everyone loves a good
    FizzBuzz. It's the pumpkin spice latte of modulo arithmetic.
    """

    def __init__(self, fallback_size: int = 10) -> None:
        self._fallback_size = fallback_size

    def is_cold_start(
        self,
        profile: UserProfile,
        min_evaluations: int,
    ) -> bool:
        """Check if a user is in the cold-start phase."""
        return len(profile.evaluated_numbers) < min_evaluations

    def get_popular_items(
        self,
        candidate_pool: list[int],
        evaluated_set: set[int],
    ) -> list[tuple[int, float]]:
        """Return popular items for cold-start users.

        Popularity is defined by a scoring function that rewards:
        - Divisibility by 15 (FizzBuzz): highest popularity
        - Divisibility by 3 or 5 (Fizz/Buzz): medium popularity
        - Fibonacci numbers: bonus popularity
        - Prime numbers: modest popularity boost

        The scores are entirely made up but internally consistent,
        which is more than can be said for most production recommendation
        systems.
        """
        scored: list[tuple[int, float]] = []
        for num in candidate_pool:
            if num in evaluated_set:
                continue
            score = 0.0
            if num % 15 == 0:
                score += 1.0   # FizzBuzz: peak popularity
            elif num % 3 == 0:
                score += 0.6   # Fizz: solid crowd-pleaser
            elif num % 5 == 0:
                score += 0.5   # Buzz: respectable
            else:
                score += 0.1   # Plain number: niche audience

            if _is_fibonacci(num):
                score += 0.3   # Fibonacci bonus
            if _is_prime(num):
                score += 0.2   # Prime bonus

            scored.append((num, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[: self._fallback_size]


# ---------------------------------------------------------------------------
# Recommendation Explainer
# ---------------------------------------------------------------------------

class RecommendationExplainer:
    """Generates human-readable explanations for recommendations.

    "Because you evaluated 15 (FizzBuzz, Aries), you might enjoy 45."

    Explainability is critical in modern recommendation systems. Users
    need to understand *why* a particular integer was recommended to them.
    Without transparency, how can they trust that 45 is truly a number
    they would enjoy evaluating? This module provides that crucial trust
    layer between human and machine.
    """

    @staticmethod
    def explain(
        source_numbers: list[int],
        recommended_number: int,
        score: float,
        reason: str = "feature similarity",
    ) -> str:
        """Generate an explanation for why a number was recommended.

        The signature format is:
            "Because you evaluated 15 (FizzBuzz, Aries), you might enjoy 45."
        """
        if not source_numbers:
            features = NumberFeatures.extract(recommended_number)
            return (
                f"  You might enjoy {recommended_number} "
                f"({features.fizzbuzz_label}, {features.zodiac_sign}). "
                f"[popular item, score={score:.3f}]"
            )

        # Pick the most relevant source (first one is fine for display)
        source = source_numbers[0]
        src_feat = NumberFeatures.extract(source)
        rec_feat = NumberFeatures.extract(recommended_number)

        shared_traits: list[str] = []
        if src_feat.parity == rec_feat.parity:
            shared_traits.append("same parity")
        if src_feat.is_prime == rec_feat.is_prime == 1:
            shared_traits.append("both prime")
        if src_feat.is_fibonacci == rec_feat.is_fibonacci == 1:
            shared_traits.append("both Fibonacci")
        if src_feat.zodiac_sign == rec_feat.zodiac_sign:
            shared_traits.append(f"both {src_feat.zodiac_sign}")
        if src_feat.fizzbuzz_label == rec_feat.fizzbuzz_label:
            shared_traits.append(f"both {src_feat.fizzbuzz_label}")

        trait_str = ", ".join(shared_traits) if shared_traits else reason

        return (
            f"  Because you evaluated {source} "
            f"({src_feat.fizzbuzz_label}, {src_feat.zodiac_sign}), "
            f"you might enjoy {recommended_number} "
            f"({rec_feat.fizzbuzz_label}, {rec_feat.zodiac_sign}). "
            f"[{trait_str}, score={score:.3f}]"
        )

    @staticmethod
    def explain_cold_start(recommended_number: int, score: float) -> str:
        """Explain a cold-start recommendation (popular item)."""
        features = NumberFeatures.extract(recommended_number)
        return (
            f"  You might enjoy {recommended_number} "
            f"({features.fizzbuzz_label}, {features.zodiac_sign}). "
            f"[popular item, score={score:.3f}]"
        )


# ---------------------------------------------------------------------------
# Recommendation Engine (Orchestrator)
# ---------------------------------------------------------------------------

class RecommendationEngine:
    """The Grand Orchestrator of the FizzBuzz Recommendation Pipeline.

    Coordinates collaborative filtering, content-based filtering, hybrid
    blending, cold-start handling, and explainability into a single,
    gloriously over-engineered recommendation service for integers.

    Usage:
        engine = RecommendationEngine()
        engine.record_evaluation("user-1", 15)
        engine.record_evaluation("user-1", 30)
        recs = engine.recommend("user-1", candidate_pool=range(1, 101))
        for number, score, explanation in recs:
            print(explanation)
    """

    def __init__(
        self,
        collaborative_weight: float = 0.6,
        content_weight: float = 0.4,
        serendipity_factor: float = 0.1,
        num_recommendations: int = 5,
        min_evaluations: int = 3,
        max_similar_users: int = 10,
        popular_items_fallback_size: int = 10,
        seed: int | None = None,
    ) -> None:
        self._rng = random.Random(seed)
        self._users: dict[str, UserProfile] = {}
        self._collaborative = CollaborativeFilter(
            max_similar_users=max_similar_users,
        )
        self._content = ContentBasedFilter()
        self._blender = HybridBlender(
            collaborative_weight=collaborative_weight,
            content_weight=content_weight,
            serendipity_factor=serendipity_factor,
            rng=self._rng,
        )
        self._cold_start = ColdStartHandler(
            fallback_size=popular_items_fallback_size,
        )
        self._explainer = RecommendationExplainer()
        self._num_recommendations = num_recommendations
        self._min_evaluations = min_evaluations
        self._evaluation_count = 0

    @property
    def users(self) -> dict[str, UserProfile]:
        """Access all user profiles."""
        return self._users

    @property
    def total_evaluations(self) -> int:
        """Total evaluations recorded across all users."""
        return self._evaluation_count

    def get_or_create_user(self, user_id: str) -> UserProfile:
        """Get or create a user profile."""
        if user_id not in self._users:
            self._users[user_id] = UserProfile(user_id=user_id)
        return self._users[user_id]

    def record_evaluation(self, user_id: str, number: int) -> None:
        """Record that a user evaluated a number."""
        profile = self.get_or_create_user(user_id)
        was_new = number not in profile.evaluated_numbers
        profile.record_evaluation(number)
        if was_new:
            self._evaluation_count += 1

    def recommend(
        self,
        user_id: str,
        candidate_pool: list[int] | range | None = None,
        n: int | None = None,
    ) -> list[tuple[int, float, str]]:
        """Generate personalized recommendations for a user.

        Returns a list of (number, score, explanation) tuples.

        If the user is in the cold-start phase (fewer evaluations than
        the minimum), falls back to popular items. Otherwise, runs the
        full hybrid recommendation pipeline.
        """
        if candidate_pool is None:
            candidate_pool = list(range(1, 101))
        else:
            candidate_pool = list(candidate_pool)

        if n is None:
            n = self._num_recommendations

        profile = self.get_or_create_user(user_id)
        evaluated_set = set(profile.evaluated_numbers)

        # Cold start check
        if self._cold_start.is_cold_start(profile, self._min_evaluations):
            popular = self._cold_start.get_popular_items(
                candidate_pool, evaluated_set
            )[:n]
            results: list[tuple[int, float, str]] = []
            for num, score in popular:
                explanation = self._explainer.explain_cold_start(num, score)
                results.append((num, score, explanation))
            return results

        # Full recommendation pipeline
        all_users = list(self._users.values())

        # Collaborative filtering
        collab_recs = self._collaborative.recommend(
            profile, all_users, n=n * 3
        )

        # Content-based filtering
        content_recs = self._content.recommend(
            profile, candidate_pool, n=n * 3
        )

        # Hybrid blending
        blended = self._blender.blend(
            collab_recs,
            content_recs,
            candidate_pool,
            evaluated_set,
            n=n,
        )

        # Generate explanations
        results = []
        for num, score in blended:
            explanation = self._explainer.explain(
                profile.evaluated_numbers, num, score
            )
            results.append((num, score, explanation))

        return results

    def recommend_for_number(
        self,
        number: int,
        candidate_pool: list[int] | range | None = None,
        n: int = 5,
    ) -> list[tuple[int, float, str]]:
        """Recommend numbers similar to a specific number.

        This is the "item-to-item" recommendation mode: given a number,
        find the most similar numbers by feature vector similarity. Useful
        for "Because you evaluated 15, you might enjoy..." use cases
        without requiring a full user profile.
        """
        if candidate_pool is None:
            candidate_pool = list(range(1, 101))
        else:
            candidate_pool = list(candidate_pool)

        source_features = NumberFeatures.extract(number)
        source_vec = source_features.to_vector()

        scored: list[tuple[int, float]] = []
        for candidate in candidate_pool:
            if candidate == number:
                continue
            feat = NumberFeatures.extract(candidate)
            sim = cosine_similarity(source_vec, feat.to_vector())
            scored.append((candidate, sim))

        scored.sort(key=lambda x: x[1], reverse=True)
        top_n = scored[:n]

        results: list[tuple[int, float, str]] = []
        for num, score in top_n:
            explanation = self._explainer.explain([number], num, score)
            results.append((num, score, explanation))

        return results


# ---------------------------------------------------------------------------
# Recommendation Dashboard
# ---------------------------------------------------------------------------

class RecommendationDashboard:
    """ASCII dashboard for the Recommendation Engine.

    Renders a comprehensive view of the recommendation subsystem,
    including user profiles, feature vectors, similarity matrices,
    and active recommendations. Because if your recommendation engine
    for integers doesn't have an ASCII dashboard, is it even enterprise?
    """

    @staticmethod
    def render(
        engine: RecommendationEngine,
        recommendations: list[tuple[int, float, str]] | None = None,
        target_number: int | None = None,
        width: int = 60,
        show_feature_vectors: bool = True,
        show_user_profiles: bool = True,
        show_similarity_matrix: bool = True,
    ) -> str:
        """Render the full recommendation dashboard."""
        lines: list[str] = []
        sep = "+" + "=" * (width - 2) + "+"
        thin_sep = "+" + "-" * (width - 2) + "+"

        # Header
        lines.append(sep)
        title = "RECOMMENDATION ENGINE DASHBOARD"
        lines.append("|" + title.center(width - 2) + "|")
        subtitle = '"Because you evaluated 15, you might enjoy 45."'
        if len(subtitle) <= width - 4:
            lines.append("|" + subtitle.center(width - 2) + "|")
        lines.append(sep)

        # Engine stats
        lines.append(thin_sep)
        stats_title = "ENGINE STATISTICS"
        lines.append("|" + stats_title.center(width - 2) + "|")
        lines.append(thin_sep)

        num_users = len(engine.users)
        total_evals = engine.total_evaluations

        stats = [
            f"  Total users: {num_users}",
            f"  Total evaluations: {total_evals}",
        ]
        for s in stats:
            lines.append("|" + s.ljust(width - 2) + "|")

        # User profiles
        if show_user_profiles and engine.users:
            lines.append(thin_sep)
            prof_title = "USER PROFILES"
            lines.append("|" + prof_title.center(width - 2) + "|")
            lines.append(thin_sep)

            for uid, profile in engine.users.items():
                line = f"  {uid}: {len(profile.evaluated_numbers)} evals"
                if profile.evaluated_numbers:
                    nums_str = ", ".join(str(n) for n in profile.evaluated_numbers[:8])
                    if len(profile.evaluated_numbers) > 8:
                        nums_str += "..."
                    line += f" [{nums_str}]"
                if len(line) > width - 2:
                    line = line[: width - 5] + "..."
                lines.append("|" + line.ljust(width - 2) + "|")

        # Feature vectors for interesting numbers
        if show_feature_vectors:
            lines.append(thin_sep)
            feat_title = "NUMBER FEATURE VECTORS"
            lines.append("|" + feat_title.center(width - 2) + "|")
            lines.append(thin_sep)

            # Show features for evaluated numbers or a default set
            sample_numbers: list[int] = []
            if target_number is not None:
                sample_numbers = [target_number]
            for profile in engine.users.values():
                sample_numbers.extend(profile.evaluated_numbers[:5])
            if not sample_numbers:
                sample_numbers = [3, 5, 7, 15, 30]

            seen: set[int] = set()
            for num in sample_numbers[:6]:
                if num in seen:
                    continue
                seen.add(num)
                feat = NumberFeatures.extract(num)
                line = (
                    f"  {num:>4}: "
                    f"{'even' if feat.parity == 0 else 'odd ':4s} "
                    f"{'P' if feat.is_prime else '.'} "
                    f"{'F' if feat.is_fibonacci else '.'} "
                    f"{feat.zodiac_sign:12s} "
                    f"dsum={feat.digit_sum}"
                )
                if len(line) > width - 2:
                    line = line[: width - 5] + "..."
                lines.append("|" + line.ljust(width - 2) + "|")

            lines.append("|" + "  Legend: P=prime, F=fibonacci".ljust(width - 2) + "|")

        # Similarity matrix (if multiple users)
        if show_similarity_matrix and len(engine.users) > 1:
            lines.append(thin_sep)
            sim_title = "USER SIMILARITY MATRIX"
            lines.append("|" + sim_title.center(width - 2) + "|")
            lines.append(thin_sep)

            user_list = list(engine.users.values())
            max_show = min(5, len(user_list))

            # Header row
            header = "         "
            for u in user_list[:max_show]:
                short = u.user_id[:6]
                header += f"{short:>8s}"
            if len(header) > width - 2:
                header = header[: width - 5] + "..."
            lines.append("|" + header.ljust(width - 2) + "|")

            # Matrix rows
            for i, u1 in enumerate(user_list[:max_show]):
                row = f"  {u1.user_id[:6]:6s} "
                for j, u2 in enumerate(user_list[:max_show]):
                    if i == j:
                        row += "   1.00 "
                    else:
                        sim = cosine_similarity(
                            u1.preference_vector, u2.preference_vector
                        )
                        row += f"  {sim:5.3f} "
                if len(row) > width - 2:
                    row = row[: width - 5] + "..."
                lines.append("|" + row.ljust(width - 2) + "|")

        # Recommendations
        if recommendations:
            lines.append(thin_sep)
            rec_title = "RECOMMENDATIONS"
            lines.append("|" + rec_title.center(width - 2) + "|")
            lines.append(thin_sep)

            for num, score, explanation in recommendations:
                # Truncate explanation to fit
                if len(explanation) > width - 4:
                    explanation = explanation[: width - 7] + "..."
                lines.append("|" + explanation.ljust(width - 2) + "|")

        # Footer
        lines.append(sep)
        footer = "Powered by Enterprise-Grade Integer Affinity Analytics"
        if len(footer) <= width - 4:
            lines.append("|" + footer.center(width - 2) + "|")
        lines.append(sep)

        return "\n".join(lines)
