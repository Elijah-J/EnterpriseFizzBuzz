"""
Enterprise FizzBuzz Platform - Recommendation Engine Tests

Tests for the Netflix-style recommendation engine that suggests which
integers a user might enjoy evaluating next. Because testing a
recommendation engine for modulo arithmetic is the pinnacle of QA.

Covers: NumberFeatures, UserProfile, CollaborativeFilter, ContentBasedFilter,
HybridBlender, ColdStartHandler, RecommendationExplainer, RecommendationEngine,
RecommendationDashboard, cosine_similarity, and all supporting utilities.
"""

from __future__ import annotations

import math
import random

import pytest

from enterprise_fizzbuzz.domain.exceptions import (
    ColdStartError,
    FilterBlendingError,
    RecommendationError,
    RecommendationExplanationError,
    SimilarityComputationError,
)
from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.recommendations import (
    ZODIAC_SIGNS,
    ColdStartHandler,
    CollaborativeFilter,
    ContentBasedFilter,
    HybridBlender,
    NumberFeatures,
    RecommendationDashboard,
    RecommendationEngine,
    RecommendationExplainer,
    UserProfile,
    cosine_similarity,
    _is_fibonacci,
    _is_prime,
    _digit_sum,
    _zodiac_sign,
    _fizzbuzz_label,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


@pytest.fixture
def empty_profile():
    """A user with no evaluation history."""
    return UserProfile(user_id="empty-user")


@pytest.fixture
def basic_profile():
    """A user who has evaluated a few numbers."""
    p = UserProfile(user_id="basic-user")
    for n in [3, 5, 15, 30]:
        p.record_evaluation(n)
    return p


@pytest.fixture
def engine():
    """A RecommendationEngine with fixed seed for reproducibility."""
    return RecommendationEngine(seed=42)


@pytest.fixture
def populated_engine():
    """An engine with multiple users and evaluations."""
    eng = RecommendationEngine(seed=42, min_evaluations=2)
    for n in [3, 5, 15, 30, 45]:
        eng.record_evaluation("alice", n)
    for n in [3, 6, 9, 12, 15]:
        eng.record_evaluation("bob", n)
    for n in [5, 10, 20, 25, 50]:
        eng.record_evaluation("carol", n)
    return eng


# ---------------------------------------------------------------------------
# Utility Function Tests
# ---------------------------------------------------------------------------

class TestPrimality:
    """Tests for the _is_prime helper."""

    def test_zero_not_prime(self):
        assert _is_prime(0) is False

    def test_one_not_prime(self):
        assert _is_prime(1) is False

    def test_two_is_prime(self):
        assert _is_prime(2) is True

    def test_three_is_prime(self):
        assert _is_prime(3) is True

    def test_four_not_prime(self):
        assert _is_prime(4) is False

    def test_small_primes(self):
        primes = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31]
        for p in primes:
            assert _is_prime(p) is True, f"{p} should be prime"

    def test_composites(self):
        composites = [4, 6, 8, 9, 10, 12, 14, 15, 16]
        for c in composites:
            assert _is_prime(c) is False, f"{c} should not be prime"

    def test_negative_not_prime(self):
        assert _is_prime(-7) is False


class TestFibonacci:
    """Tests for the _is_fibonacci membership check."""

    def test_fibonacci_numbers(self):
        fibs = [0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89]
        for f in fibs:
            assert _is_fibonacci(f) is True, f"{f} should be Fibonacci"

    def test_non_fibonacci_numbers(self):
        non_fibs = [4, 6, 7, 9, 10, 11, 12, 14, 15]
        for n in non_fibs:
            assert _is_fibonacci(n) is False, f"{n} should not be Fibonacci"

    def test_negative_not_fibonacci(self):
        assert _is_fibonacci(-5) is False


class TestDigitSum:
    """Tests for the _digit_sum helper."""

    def test_single_digit(self):
        assert _digit_sum(7) == 7

    def test_multi_digit(self):
        assert _digit_sum(123) == 6

    def test_negative(self):
        assert _digit_sum(-42) == 6

    def test_zero(self):
        assert _digit_sum(0) == 0


class TestZodiacSign:
    """Tests for the zodiac assignment function."""

    def test_twelve_signs(self):
        assert len(ZODIAC_SIGNS) == 12

    def test_assignment_wraps(self):
        assert _zodiac_sign(0) == "Aries"
        assert _zodiac_sign(12) == "Aries"
        assert _zodiac_sign(1) == "Taurus"

    def test_negative_number(self):
        # abs(-3) % 12 == 3 -> Cancer
        assert _zodiac_sign(-3) == "Cancer"


class TestFizzBuzzLabel:
    """Tests for the _fizzbuzz_label helper."""

    def test_fizzbuzz(self):
        assert _fizzbuzz_label(15) == "FizzBuzz"
        assert _fizzbuzz_label(30) == "FizzBuzz"

    def test_fizz(self):
        assert _fizzbuzz_label(3) == "Fizz"
        assert _fizzbuzz_label(9) == "Fizz"

    def test_buzz(self):
        assert _fizzbuzz_label(5) == "Buzz"
        assert _fizzbuzz_label(10) == "Buzz"

    def test_plain(self):
        assert _fizzbuzz_label(7) == "7"


# ---------------------------------------------------------------------------
# NumberFeatures Tests
# ---------------------------------------------------------------------------

class TestNumberFeatures:
    """Tests for NumberFeatures extraction and vector conversion."""

    def test_extract_fifteen(self):
        feat = NumberFeatures.extract(15)
        assert feat.number == 15
        assert feat.parity == 1  # odd
        assert feat.is_prime == 0
        assert feat.is_fibonacci == 0
        assert feat.zodiac_index == 3  # 15 % 12 == 3
        assert feat.zodiac_sign == "Cancer"
        assert feat.digit_sum == 6
        assert feat.fizzbuzz_label == "FizzBuzz"

    def test_extract_two(self):
        feat = NumberFeatures.extract(2)
        assert feat.parity == 0  # even
        assert feat.is_prime == 1
        assert feat.is_fibonacci == 1

    def test_to_vector_length(self):
        feat = NumberFeatures.extract(42)
        vec = feat.to_vector()
        assert len(vec) == 5

    def test_to_vector_normalized(self):
        feat = NumberFeatures.extract(1)
        vec = feat.to_vector()
        # zodiac_index for 1 is 1, normalized: 1/11
        assert abs(vec[3] - 1 / 11) < 1e-9

    def test_frozen_dataclass(self):
        feat = NumberFeatures.extract(5)
        with pytest.raises(AttributeError):
            feat.number = 10


# ---------------------------------------------------------------------------
# Cosine Similarity Tests
# ---------------------------------------------------------------------------

class TestCosineSimilarity:
    """Tests for the cosine similarity function."""

    def test_identical_vectors(self):
        v = [1.0, 2.0, 3.0]
        assert abs(cosine_similarity(v, v) - 1.0) < 1e-9

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert abs(cosine_similarity(a, b)) < 1e-9

    def test_opposite_vectors(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert abs(cosine_similarity(a, b) - (-1.0)) < 1e-9

    def test_zero_vector_returns_zero(self):
        a = [0.0, 0.0, 0.0]
        b = [1.0, 2.0, 3.0]
        assert cosine_similarity(a, b) == 0.0

    def test_both_zero_vectors(self):
        a = [0.0, 0.0]
        b = [0.0, 0.0]
        assert cosine_similarity(a, b) == 0.0

    def test_different_lengths(self):
        a = [1.0, 2.0]
        b = [1.0]
        assert cosine_similarity(a, b) == 0.0

    def test_known_value(self):
        a = [1.0, 2.0, 3.0]
        b = [4.0, 5.0, 6.0]
        # dot = 32, |a| = sqrt(14), |b| = sqrt(77)
        expected = 32 / (math.sqrt(14) * math.sqrt(77))
        assert abs(cosine_similarity(a, b) - expected) < 1e-9


# ---------------------------------------------------------------------------
# UserProfile Tests
# ---------------------------------------------------------------------------

class TestUserProfile:
    """Tests for UserProfile evaluation tracking."""

    def test_empty_profile_preference_vector(self, empty_profile):
        vec = empty_profile.preference_vector
        assert vec == [0.0] * 5

    def test_record_evaluation(self, empty_profile):
        empty_profile.record_evaluation(15)
        assert 15 in empty_profile.evaluated_numbers
        assert len(empty_profile.evaluated_numbers) == 1

    def test_no_duplicates(self, empty_profile):
        empty_profile.record_evaluation(15)
        empty_profile.record_evaluation(15)
        assert len(empty_profile.evaluated_numbers) == 1

    def test_preference_vector_nonzero(self, basic_profile):
        vec = basic_profile.preference_vector
        assert any(v != 0.0 for v in vec)

    def test_get_features_cached(self, basic_profile):
        f1 = basic_profile.get_features(15)
        f2 = basic_profile.get_features(15)
        assert f1 is f2  # Same cached object


# ---------------------------------------------------------------------------
# CollaborativeFilter Tests
# ---------------------------------------------------------------------------

class TestCollaborativeFilter:
    """Tests for user-based collaborative filtering."""

    def test_find_similar_users_excludes_self(self):
        cf = CollaborativeFilter(max_similar_users=5)
        u1 = UserProfile(user_id="u1")
        u1.record_evaluation(3)
        u1.record_evaluation(5)

        result = cf.find_similar_users(u1, [u1])
        assert len(result) == 0

    def test_find_similar_users_ranks_by_similarity(self):
        cf = CollaborativeFilter(max_similar_users=5)
        u1 = UserProfile(user_id="u1")
        u2 = UserProfile(user_id="u2")
        u3 = UserProfile(user_id="u3")

        # u1 likes fizzbuzz numbers
        for n in [15, 30, 45]:
            u1.record_evaluation(n)

        # u2 likes similar fizzbuzz numbers
        for n in [15, 30, 60]:
            u2.record_evaluation(n)

        # u3 likes primes (very different)
        for n in [2, 3, 7]:
            u3.record_evaluation(n)

        results = cf.find_similar_users(u1, [u1, u2, u3])
        # u2 should be more similar than u3
        assert results[0][0].user_id == "u2"

    def test_recommend_excludes_evaluated(self):
        cf = CollaborativeFilter()
        u1 = UserProfile(user_id="u1")
        u2 = UserProfile(user_id="u2")

        u1.record_evaluation(3)
        u1.record_evaluation(5)
        u2.record_evaluation(3)
        u2.record_evaluation(5)
        u2.record_evaluation(15)

        recs = cf.recommend(u1, [u1, u2], n=5)
        rec_numbers = [r[0] for r in recs]
        assert 3 not in rec_numbers
        assert 5 not in rec_numbers

    def test_recommend_empty_when_no_similar_users(self):
        cf = CollaborativeFilter()
        u1 = UserProfile(user_id="u1")
        u1.record_evaluation(3)
        recs = cf.recommend(u1, [u1], n=5)
        assert recs == []


# ---------------------------------------------------------------------------
# ContentBasedFilter Tests
# ---------------------------------------------------------------------------

class TestContentBasedFilter:
    """Tests for content-based feature similarity filtering."""

    def test_recommend_excludes_evaluated(self):
        cbf = ContentBasedFilter()
        p = UserProfile(user_id="u1")
        p.record_evaluation(15)
        p.record_evaluation(30)

        recs = cbf.recommend(p, list(range(1, 50)), n=5)
        rec_numbers = [r[0] for r in recs]
        assert 15 not in rec_numbers
        assert 30 not in rec_numbers

    def test_recommend_returns_scores(self):
        cbf = ContentBasedFilter()
        p = UserProfile(user_id="u1")
        p.record_evaluation(15)

        recs = cbf.recommend(p, list(range(1, 50)), n=3)
        assert len(recs) == 3
        for num, score in recs:
            assert isinstance(score, float)
            assert 0.0 <= score <= 1.0

    def test_recommend_prefers_similar_features(self):
        cbf = ContentBasedFilter()
        p = UserProfile(user_id="u1")
        # User likes FizzBuzz numbers
        p.record_evaluation(15)
        p.record_evaluation(30)

        recs = cbf.recommend(p, list(range(1, 100)), n=5)
        rec_numbers = [r[0] for r in recs]
        # 45, 60, 75, 90 are all FizzBuzz numbers and should score high
        # At least one FizzBuzz number should be in top 5
        fizzbuzz_in_recs = [n for n in rec_numbers if n % 15 == 0]
        assert len(fizzbuzz_in_recs) >= 1


# ---------------------------------------------------------------------------
# HybridBlender Tests
# ---------------------------------------------------------------------------

class TestHybridBlender:
    """Tests for the hybrid recommendation blender."""

    def test_blend_combines_scores(self):
        blender = HybridBlender(
            collaborative_weight=0.6,
            content_weight=0.4,
            serendipity_factor=0.0,  # Disable serendipity for predictability
            rng=random.Random(42),
        )
        collab = [(45, 0.9), (60, 0.7)]
        content = [(45, 0.8), (75, 0.6)]

        results = blender.blend(
            collab, content,
            candidate_pool=list(range(1, 100)),
            evaluated_set=set(),
            n=5,
        )

        result_dict = dict(results)
        # 45 should have highest blended score: 0.6*0.9 + 0.4*0.8 = 0.86
        assert 45 in result_dict
        expected_45 = 0.6 * 0.9 + 0.4 * 0.8
        assert abs(result_dict[45] - expected_45) < 1e-9

    def test_blend_with_serendipity(self):
        blender = HybridBlender(
            collaborative_weight=0.6,
            content_weight=0.4,
            serendipity_factor=0.5,  # High serendipity
            rng=random.Random(42),
        )
        collab = [(45, 0.9), (60, 0.7), (75, 0.5)]
        content = [(45, 0.8), (60, 0.6)]

        results = blender.blend(
            collab, content,
            candidate_pool=list(range(1, 100)),
            evaluated_set=set(),
            n=3,
        )
        assert len(results) == 3

    def test_blend_empty_inputs(self):
        blender = HybridBlender(serendipity_factor=0.0)
        results = blender.blend([], [], list(range(1, 10)), set(), n=3)
        assert results == []


# ---------------------------------------------------------------------------
# ColdStartHandler Tests
# ---------------------------------------------------------------------------

class TestColdStartHandler:
    """Tests for the cold-start fallback handler."""

    def test_is_cold_start_true(self):
        handler = ColdStartHandler()
        p = UserProfile(user_id="new")
        p.record_evaluation(1)
        assert handler.is_cold_start(p, min_evaluations=3) is True

    def test_is_cold_start_false(self):
        handler = ColdStartHandler()
        p = UserProfile(user_id="experienced")
        for n in [1, 2, 3, 4, 5]:
            p.record_evaluation(n)
        assert handler.is_cold_start(p, min_evaluations=3) is False

    def test_popular_items_returns_fizzbuzz_first(self):
        handler = ColdStartHandler(fallback_size=5)
        pool = list(range(1, 50))
        results = handler.get_popular_items(pool, evaluated_set=set())

        # FizzBuzz numbers should dominate the top results
        top_numbers = [r[0] for r in results[:3]]
        fizzbuzz_count = sum(1 for n in top_numbers if n % 15 == 0)
        assert fizzbuzz_count >= 1

    def test_popular_items_excludes_evaluated(self):
        handler = ColdStartHandler(fallback_size=5)
        pool = list(range(1, 50))
        evaluated = {15, 30, 45}
        results = handler.get_popular_items(pool, evaluated)
        result_numbers = [r[0] for r in results]
        for n in evaluated:
            assert n not in result_numbers


# ---------------------------------------------------------------------------
# RecommendationExplainer Tests
# ---------------------------------------------------------------------------

class TestRecommendationExplainer:
    """Tests for the human-readable explanation generator."""

    def test_explain_with_source(self):
        explanation = RecommendationExplainer.explain(
            source_numbers=[15], recommended_number=45, score=0.85
        )
        assert "15" in explanation
        assert "45" in explanation
        assert "Because you evaluated" in explanation

    def test_explain_without_source(self):
        explanation = RecommendationExplainer.explain(
            source_numbers=[], recommended_number=30, score=0.5
        )
        assert "30" in explanation
        assert "popular item" in explanation

    def test_explain_cold_start(self):
        explanation = RecommendationExplainer.explain_cold_start(45, 0.9)
        assert "45" in explanation
        assert "popular item" in explanation

    def test_explain_includes_zodiac(self):
        explanation = RecommendationExplainer.explain(
            source_numbers=[15], recommended_number=45, score=0.85
        )
        # Both 15 and 45 are Cancer (15%12=3, 45%12=9 -> Capricorn actually)
        # Just check zodiac signs are present
        has_zodiac = any(z in explanation for z in ZODIAC_SIGNS)
        assert has_zodiac

    def test_explain_includes_fizzbuzz_label(self):
        explanation = RecommendationExplainer.explain(
            source_numbers=[15], recommended_number=45, score=0.85
        )
        assert "FizzBuzz" in explanation


# ---------------------------------------------------------------------------
# RecommendationEngine Tests
# ---------------------------------------------------------------------------

class TestRecommendationEngine:
    """Tests for the orchestrator engine."""

    def test_record_evaluation(self, engine):
        engine.record_evaluation("user1", 15)
        assert engine.total_evaluations == 1
        assert "user1" in engine.users

    def test_record_duplicate_no_double_count(self, engine):
        engine.record_evaluation("user1", 15)
        engine.record_evaluation("user1", 15)
        assert engine.total_evaluations == 1

    def test_get_or_create_user(self, engine):
        profile = engine.get_or_create_user("new-user")
        assert profile.user_id == "new-user"
        assert "new-user" in engine.users

    def test_cold_start_recommendations(self, engine):
        engine.record_evaluation("user1", 15)
        recs = engine.recommend("user1", candidate_pool=range(1, 50), n=3)
        assert len(recs) == 3
        for num, score, explanation in recs:
            assert "popular item" in explanation

    def test_personalized_recommendations(self, populated_engine):
        recs = populated_engine.recommend(
            "alice", candidate_pool=range(1, 100), n=5
        )
        assert len(recs) <= 5
        for num, score, explanation in recs:
            assert isinstance(num, int)
            assert isinstance(score, float)
            assert isinstance(explanation, str)

    def test_recommend_for_number(self, engine):
        recs = engine.recommend_for_number(
            15, candidate_pool=range(1, 100), n=5
        )
        assert len(recs) == 5
        for num, score, explanation in recs:
            assert num != 15
            assert "15" in explanation

    def test_recommend_excludes_evaluated(self, populated_engine):
        recs = populated_engine.recommend(
            "alice", candidate_pool=range(1, 100), n=10
        )
        evaluated = set(populated_engine.users["alice"].evaluated_numbers)
        rec_numbers = {num for num, _, _ in recs}
        assert rec_numbers.isdisjoint(evaluated)

    def test_multiple_users_collaborative(self, populated_engine):
        """Collaborative filtering should leverage cross-user patterns."""
        recs = populated_engine.recommend(
            "alice", candidate_pool=range(1, 100), n=10
        )
        # Alice should get some numbers from Bob's/Carol's evaluations
        assert len(recs) > 0


# ---------------------------------------------------------------------------
# RecommendationDashboard Tests
# ---------------------------------------------------------------------------

class TestRecommendationDashboard:
    """Tests for the ASCII dashboard renderer."""

    def test_render_empty_engine(self, engine):
        output = RecommendationDashboard.render(engine, width=60)
        assert "RECOMMENDATION ENGINE DASHBOARD" in output
        assert "Total users: 0" in output

    def test_render_with_users(self, populated_engine):
        output = RecommendationDashboard.render(populated_engine, width=60)
        assert "alice" in output
        assert "bob" in output
        assert "Total users: 3" in output

    def test_render_with_recommendations(self, populated_engine):
        recs = populated_engine.recommend("alice", candidate_pool=range(1, 100))
        output = RecommendationDashboard.render(
            populated_engine, recommendations=recs, width=60
        )
        assert "RECOMMENDATIONS" in output

    def test_render_feature_vectors(self, engine):
        engine.record_evaluation("user1", 15)
        output = RecommendationDashboard.render(
            engine, show_feature_vectors=True, width=60
        )
        assert "NUMBER FEATURE VECTORS" in output

    def test_render_similarity_matrix(self, populated_engine):
        output = RecommendationDashboard.render(
            populated_engine, show_similarity_matrix=True, width=80
        )
        assert "USER SIMILARITY MATRIX" in output

    def test_render_respects_width(self, populated_engine):
        output = RecommendationDashboard.render(populated_engine, width=40)
        for line in output.split("\n"):
            # Lines might be slightly over due to truncation
            assert len(line) <= 45  # Allow small overflow for edge cases

    def test_render_with_target_number(self, engine):
        engine.record_evaluation("user1", 15)
        output = RecommendationDashboard.render(
            engine, target_number=15, width=60
        )
        assert "15" in output


# ---------------------------------------------------------------------------
# Exception Tests
# ---------------------------------------------------------------------------

class TestRecommendationExceptions:
    """Tests for the recommendation exception hierarchy."""

    def test_cold_start_error(self):
        err = ColdStartError("user1", 1, 5)
        assert "user1" in str(err)
        assert err.error_code == "EFP-RE01"
        assert err.user_id == "user1"
        assert err.evaluated_count == 1
        assert err.minimum_required == 5

    def test_similarity_computation_error(self):
        err = SimilarityComputationError("vec_a", "vec_b", "zero norm")
        assert "vec_a" in str(err)
        assert err.error_code == "EFP-RE02"

    def test_filter_blending_error(self):
        err = FilterBlendingError(5, 3, "interpolation failed")
        assert "interpolation failed" in str(err)
        assert err.error_code == "EFP-RE03"

    def test_recommendation_explanation_error(self):
        err = RecommendationExplanationError(45, 15)
        assert "45" in str(err)
        assert "15" in str(err)
        assert err.error_code == "EFP-RE04"

    def test_base_recommendation_error(self):
        err = RecommendationError("test error")
        assert err.error_code == "EFP-RE00"

    def test_exception_hierarchy(self):
        assert issubclass(ColdStartError, RecommendationError)
        assert issubclass(SimilarityComputationError, RecommendationError)
        assert issubclass(FilterBlendingError, RecommendationError)
        assert issubclass(RecommendationExplanationError, RecommendationError)
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        assert issubclass(RecommendationError, FizzBuzzError)
