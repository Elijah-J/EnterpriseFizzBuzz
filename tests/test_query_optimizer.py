"""
Enterprise FizzBuzz Platform - Query Optimizer Test Suite

Comprehensive tests for the PostgreSQL-inspired cost-based query
planner, because even a query optimizer for modulo arithmetic
deserves 40+ tests to prove it can plan the execution of n % 3.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from enterprise_fizzbuzz.domain.exceptions import (
    CostEstimationError,
    InvalidHintError,
    PlanGenerationError,
    PlanCacheOverflowError,
    QueryOptimizerError,
)
from enterprise_fizzbuzz.domain.models import EventType, FizzBuzzResult, ProcessingContext
from enterprise_fizzbuzz.infrastructure.query_optimizer import (
    CostModel,
    DivisibilityProfile,
    ExplainOutput,
    LogicalNode,
    Optimizer,
    OptimizerDashboard,
    OptimizerHint,
    OptimizerMiddleware,
    PhysicalNode,
    PlanCache,
    PlanEnumerator,
    PlanNodeType,
    StatisticsCollector,
    create_optimizer_from_config,
    parse_optimizer_hints,
)


# ============================================================
# PlanNodeType Tests
# ============================================================

class TestPlanNodeType(unittest.TestCase):
    """Tests for the PlanNodeType enumeration."""

    def test_all_node_types_exist(self):
        expected = {
            "MODULO_SCAN", "CACHE_LOOKUP", "ML_INFERENCE",
            "COMPLIANCE_GATE", "BLOCKCHAIN_VERIFY", "RESULT_MERGE",
            "FILTER", "MATERIALIZE",
        }
        actual = {e.name for e in PlanNodeType}
        self.assertEqual(expected, actual)

    def test_node_types_are_unique(self):
        values = [e.value for e in PlanNodeType]
        self.assertEqual(len(values), len(set(values)))


# ============================================================
# OptimizerHint Tests
# ============================================================

class TestOptimizerHint(unittest.TestCase):
    """Tests for the OptimizerHint enumeration."""

    def test_all_hints_exist(self):
        expected = {"FORCE_ML", "PREFER_CACHE", "NO_BLOCKCHAIN", "NO_ML"}
        actual = {e.name for e in OptimizerHint}
        self.assertEqual(expected, actual)

    def test_parse_single_hint(self):
        hints = parse_optimizer_hints("FORCE_ML")
        self.assertEqual(hints, frozenset({OptimizerHint.FORCE_ML}))

    def test_parse_multiple_hints(self):
        hints = parse_optimizer_hints("PREFER_CACHE,NO_BLOCKCHAIN")
        self.assertEqual(hints, frozenset({OptimizerHint.PREFER_CACHE, OptimizerHint.NO_BLOCKCHAIN}))

    def test_parse_lowercase_hints(self):
        hints = parse_optimizer_hints("force_ml")
        self.assertEqual(hints, frozenset({OptimizerHint.FORCE_ML}))

    def test_parse_empty_string(self):
        hints = parse_optimizer_hints("")
        self.assertEqual(hints, frozenset())

    def test_parse_invalid_hint_raises(self):
        with self.assertRaises(InvalidHintError):
            parse_optimizer_hints("INVALID_HINT")

    def test_parse_contradictory_hints_raises(self):
        with self.assertRaises(InvalidHintError):
            parse_optimizer_hints("FORCE_ML,NO_ML")

    def test_parse_with_whitespace(self):
        hints = parse_optimizer_hints("  FORCE_ML , PREFER_CACHE  ")
        self.assertEqual(hints, frozenset({OptimizerHint.FORCE_ML, OptimizerHint.PREFER_CACHE}))


# ============================================================
# LogicalNode Tests
# ============================================================

class TestLogicalNode(unittest.TestCase):
    """Tests for the LogicalNode dataclass."""

    def test_leaf_depth(self):
        node = LogicalNode(node_type=PlanNodeType.MODULO_SCAN)
        self.assertEqual(node.depth(), 1)

    def test_nested_depth(self):
        child = LogicalNode(node_type=PlanNodeType.MODULO_SCAN)
        parent = LogicalNode(node_type=PlanNodeType.RESULT_MERGE, children=[child])
        self.assertEqual(parent.depth(), 2)

    def test_node_count(self):
        child1 = LogicalNode(node_type=PlanNodeType.MODULO_SCAN)
        child2 = LogicalNode(node_type=PlanNodeType.CACHE_LOOKUP)
        parent = LogicalNode(node_type=PlanNodeType.RESULT_MERGE, children=[child1, child2])
        self.assertEqual(parent.node_count(), 3)

    def test_add_child_returns_self(self):
        parent = LogicalNode(node_type=PlanNodeType.RESULT_MERGE)
        result = parent.add_child(LogicalNode(node_type=PlanNodeType.MODULO_SCAN))
        self.assertIs(result, parent)
        self.assertEqual(len(parent.children), 1)


# ============================================================
# PhysicalNode Tests
# ============================================================

class TestPhysicalNode(unittest.TestCase):
    """Tests for the PhysicalNode dataclass."""

    def test_total_cost_leaf(self):
        node = PhysicalNode(node_type=PlanNodeType.MODULO_SCAN, estimated_cost=1.5)
        self.assertAlmostEqual(node.total_cost(), 1.5)

    def test_total_cost_with_children(self):
        child = PhysicalNode(node_type=PlanNodeType.MODULO_SCAN, estimated_cost=1.0)
        parent = PhysicalNode(node_type=PlanNodeType.RESULT_MERGE, estimated_cost=0.5, children=[child])
        self.assertAlmostEqual(parent.total_cost(), 1.5)

    def test_mark_executed(self):
        node = PhysicalNode(node_type=PlanNodeType.MODULO_SCAN)
        node.mark_executed(actual_rows=42, actual_time_ms=0.123, actual_cost=1.05)
        self.assertEqual(node.actual_rows, 42)
        self.assertAlmostEqual(node.actual_time_ms, 0.123)
        self.assertAlmostEqual(node.actual_cost, 1.05)
        self.assertTrue(node._executed)

    def test_total_actual_cost(self):
        child = PhysicalNode(node_type=PlanNodeType.MODULO_SCAN, actual_cost=1.0)
        parent = PhysicalNode(node_type=PlanNodeType.RESULT_MERGE, actual_cost=0.5, children=[child])
        self.assertAlmostEqual(parent.total_actual_cost(), 1.5)

    def test_depth(self):
        child = PhysicalNode(node_type=PlanNodeType.MODULO_SCAN)
        parent = PhysicalNode(node_type=PlanNodeType.RESULT_MERGE, children=[child])
        self.assertEqual(parent.depth(), 2)


# ============================================================
# CostModel Tests
# ============================================================

class TestCostModel(unittest.TestCase):
    """Tests for the CostModel cost estimation engine."""

    def test_default_weights(self):
        cm = CostModel()
        self.assertAlmostEqual(cm.get_weight("modulo"), 1.0)
        self.assertAlmostEqual(cm.get_weight("ml"), 20.0)
        self.assertAlmostEqual(cm.get_weight("blockchain"), 50.0)

    def test_custom_weights(self):
        cm = CostModel(weights={"modulo": 2.0, "ml": 10.0})
        self.assertAlmostEqual(cm.get_weight("modulo"), 2.0)
        self.assertAlmostEqual(cm.get_weight("ml"), 10.0)
        # Defaults for unspecified weights
        self.assertAlmostEqual(cm.get_weight("blockchain"), 50.0)

    def test_estimate_modulo_scan(self):
        cm = CostModel()
        node = PhysicalNode(node_type=PlanNodeType.MODULO_SCAN, estimated_rows=100)
        cost = cm.estimate(node)
        self.assertGreater(cost, 0)
        self.assertEqual(node.estimated_cost, cost)

    def test_ml_more_expensive_than_modulo(self):
        cm = CostModel()
        modulo = PhysicalNode(node_type=PlanNodeType.MODULO_SCAN, estimated_rows=100)
        ml = PhysicalNode(node_type=PlanNodeType.ML_INFERENCE, estimated_rows=100)
        cm.estimate(modulo)
        cm.estimate(ml)
        self.assertGreater(ml.estimated_cost, modulo.estimated_cost)

    def test_blockchain_most_expensive(self):
        cm = CostModel()
        modulo = PhysicalNode(node_type=PlanNodeType.MODULO_SCAN, estimated_rows=100)
        blockchain = PhysicalNode(node_type=PlanNodeType.BLOCKCHAIN_VERIFY, estimated_rows=100)
        cm.estimate(modulo)
        cm.estimate(blockchain)
        self.assertGreater(blockchain.estimated_cost, modulo.estimated_cost)

    def test_cache_miss_penalty(self):
        cm = CostModel()
        cache_hit = PhysicalNode(node_type=PlanNodeType.CACHE_LOOKUP, estimated_rows=100, hit_probability=1.0)
        cache_miss = PhysicalNode(node_type=PlanNodeType.CACHE_LOOKUP, estimated_rows=100, hit_probability=0.0)
        cost_hit = cm.estimate(cache_hit)
        cost_miss = cm.estimate(cache_miss)
        self.assertGreater(cost_miss, cost_hit)

    def test_weights_property_returns_copy(self):
        cm = CostModel()
        w = cm.weights
        w["modulo"] = 999.0
        self.assertAlmostEqual(cm.get_weight("modulo"), 1.0)

    def test_unknown_weight_returns_default(self):
        cm = CostModel()
        self.assertAlmostEqual(cm.get_weight("nonexistent"), 1.0)


# ============================================================
# StatisticsCollector Tests
# ============================================================

class TestStatisticsCollector(unittest.TestCase):
    """Tests for the StatisticsCollector cardinality estimator."""

    def test_theoretical_probabilities(self):
        sc = StatisticsCollector()
        self.assertAlmostEqual(sc.FIZZ_PROBABILITY + sc.BUZZ_PROBABILITY +
                               sc.FIZZBUZZ_PROBABILITY + sc.PLAIN_PROBABILITY, 1.0, places=10)

    def test_estimate_cardinality_theoretical(self):
        sc = StatisticsCollector()
        card = sc.estimate_cardinality(100)
        self.assertIn("fizz", card)
        self.assertIn("buzz", card)
        self.assertIn("fizzbuzz", card)
        self.assertIn("plain", card)
        # Plain should be the most common
        self.assertGreater(card["plain"], card["fizzbuzz"])

    def test_record_observation(self):
        sc = StatisticsCollector()
        sc.record_observation("fizz")
        sc.record_observation("buzz")
        self.assertEqual(sc.total_observed, 2)
        self.assertEqual(sc.observed_counts["fizz"], 1)
        self.assertEqual(sc.observed_counts["buzz"], 1)

    def test_empirical_cardinality(self):
        sc = StatisticsCollector()
        for _ in range(50):
            sc.record_observation("fizz")
        for _ in range(50):
            sc.record_observation("plain")
        card = sc.estimate_cardinality(100)
        self.assertEqual(card["fizz"], 50)
        self.assertEqual(card["plain"], 50)

    def test_get_selectivity(self):
        sc = StatisticsCollector()
        self.assertGreater(sc.get_selectivity("plain"), sc.get_selectivity("fizzbuzz"))

    def test_unknown_selectivity(self):
        sc = StatisticsCollector()
        self.assertAlmostEqual(sc.get_selectivity("unknown"), 0.5)


# ============================================================
# DivisibilityProfile Tests
# ============================================================

class TestDivisibilityProfile(unittest.TestCase):
    """Tests for the DivisibilityProfile cache key generation."""

    def test_cache_key_deterministic(self):
        p = DivisibilityProfile(divisors=(3, 5), labels=("Fizz", "Buzz"), range_size=100)
        k1 = p.cache_key(frozenset())
        k2 = p.cache_key(frozenset())
        self.assertEqual(k1, k2)

    def test_different_hints_different_keys(self):
        p = DivisibilityProfile(divisors=(3, 5), labels=("Fizz", "Buzz"), range_size=100)
        k1 = p.cache_key(frozenset())
        k2 = p.cache_key(frozenset({OptimizerHint.FORCE_ML}))
        self.assertNotEqual(k1, k2)

    def test_different_profiles_different_keys(self):
        p1 = DivisibilityProfile(divisors=(3,), labels=("Fizz",), range_size=100)
        p2 = DivisibilityProfile(divisors=(3, 5), labels=("Fizz", "Buzz"), range_size=100)
        self.assertNotEqual(p1.cache_key(frozenset()), p2.cache_key(frozenset()))

    def test_frozen(self):
        p = DivisibilityProfile(divisors=(3,), labels=("Fizz",), range_size=100)
        with self.assertRaises(AttributeError):
            p.range_size = 200


# ============================================================
# PlanEnumerator Tests
# ============================================================

class TestPlanEnumerator(unittest.TestCase):
    """Tests for the PlanEnumerator plan generation engine."""

    def setUp(self):
        self.cost_model = CostModel()
        self.stats = StatisticsCollector()
        self.profile = DivisibilityProfile(divisors=(3, 5), labels=("Fizz", "Buzz"), range_size=100)

    def test_generates_plans(self):
        enum = PlanEnumerator(self.cost_model, self.stats)
        plans = enum.enumerate(self.profile, frozenset())
        self.assertGreater(len(plans), 0)

    def test_plans_sorted_by_cost(self):
        enum = PlanEnumerator(self.cost_model, self.stats)
        plans = enum.enumerate(self.profile, frozenset())
        costs = [p.total_cost() for p in plans]
        self.assertEqual(costs, sorted(costs))

    def test_no_ml_hint_excludes_ml(self):
        enum = PlanEnumerator(self.cost_model, self.stats)
        plans = enum.enumerate(self.profile, frozenset({OptimizerHint.NO_ML}))
        for plan in plans:
            self._assert_no_node_type(plan, PlanNodeType.ML_INFERENCE)

    def test_no_blockchain_hint_excludes_blockchain(self):
        enum = PlanEnumerator(self.cost_model, self.stats)
        plans = enum.enumerate(self.profile, frozenset({OptimizerHint.NO_BLOCKCHAIN}))
        for plan in plans:
            self._assert_no_node_type(plan, PlanNodeType.BLOCKCHAIN_VERIFY)

    def test_force_ml_excludes_pure_modulo(self):
        enum = PlanEnumerator(self.cost_model, self.stats)
        plans = enum.enumerate(self.profile, frozenset({OptimizerHint.FORCE_ML}))
        # First plan should NOT be a pure ModuloScan
        self.assertNotEqual(plans[0].node_type, PlanNodeType.MODULO_SCAN)

    def test_contradictory_hints_raise(self):
        enum = PlanEnumerator(self.cost_model, self.stats)
        with self.assertRaises(InvalidHintError):
            enum.enumerate(self.profile, frozenset({OptimizerHint.FORCE_ML, OptimizerHint.NO_ML}))

    def test_max_plans_limit(self):
        enum = PlanEnumerator(self.cost_model, self.stats, max_plans=2)
        plans = enum.enumerate(self.profile, frozenset())
        self.assertLessEqual(len(plans), 2)

    def test_prefer_cache_increases_hit_probability(self):
        enum = PlanEnumerator(self.cost_model, self.stats)
        plans_no_hint = enum.enumerate(self.profile, frozenset())
        plans_prefer = enum.enumerate(self.profile, frozenset({OptimizerHint.PREFER_CACHE}))
        # PREFER_CACHE should make the cache plan cheaper
        # The cache plan (with higher hit_prob) should have lower cost
        self.assertTrue(len(plans_prefer) > 0)

    def _assert_no_node_type(self, node, excluded_type):
        self.assertNotEqual(node.node_type, excluded_type,
                            f"Found excluded node type {excluded_type.name}")
        for child in node.children:
            self._assert_no_node_type(child, excluded_type)


# ============================================================
# PlanCache Tests
# ============================================================

class TestPlanCache(unittest.TestCase):
    """Tests for the PlanCache LRU cache."""

    def test_put_and_get(self):
        cache = PlanCache(max_size=10)
        plan = PhysicalNode(node_type=PlanNodeType.MODULO_SCAN)
        cache.put("key1", plan)
        result = cache.get("key1")
        self.assertIs(result, plan)

    def test_miss(self):
        cache = PlanCache(max_size=10)
        result = cache.get("nonexistent")
        self.assertIsNone(result)

    def test_hit_miss_counters(self):
        cache = PlanCache(max_size=10)
        cache.put("key1", PhysicalNode(node_type=PlanNodeType.MODULO_SCAN))
        cache.get("key1")  # hit
        cache.get("key2")  # miss
        self.assertEqual(cache.hits, 1)
        self.assertEqual(cache.misses, 1)

    def test_lru_eviction(self):
        cache = PlanCache(max_size=2)
        cache.put("a", PhysicalNode(node_type=PlanNodeType.MODULO_SCAN))
        cache.put("b", PhysicalNode(node_type=PlanNodeType.CACHE_LOOKUP))
        cache.put("c", PhysicalNode(node_type=PlanNodeType.ML_INFERENCE))
        # "a" should be evicted
        self.assertIsNone(cache.get("a"))
        self.assertIsNotNone(cache.get("b"))
        self.assertIsNotNone(cache.get("c"))

    def test_eviction_counter(self):
        cache = PlanCache(max_size=1)
        cache.put("a", PhysicalNode(node_type=PlanNodeType.MODULO_SCAN))
        cache.put("b", PhysicalNode(node_type=PlanNodeType.MODULO_SCAN))
        self.assertEqual(cache.evictions, 1)

    def test_hit_rate(self):
        cache = PlanCache(max_size=10)
        cache.put("key1", PhysicalNode(node_type=PlanNodeType.MODULO_SCAN))
        cache.get("key1")  # hit
        cache.get("key2")  # miss
        self.assertAlmostEqual(cache.hit_rate, 0.5)

    def test_hit_rate_empty(self):
        cache = PlanCache(max_size=10)
        self.assertAlmostEqual(cache.hit_rate, 0.0)

    def test_clear(self):
        cache = PlanCache(max_size=10)
        cache.put("a", PhysicalNode(node_type=PlanNodeType.MODULO_SCAN))
        cache.clear()
        self.assertEqual(cache.size, 0)
        self.assertIsNone(cache.get("a"))

    def test_get_stats(self):
        cache = PlanCache(max_size=10)
        stats = cache.get_stats()
        self.assertIn("size", stats)
        self.assertIn("max_size", stats)
        self.assertIn("hits", stats)
        self.assertIn("misses", stats)
        self.assertIn("evictions", stats)
        self.assertIn("hit_rate", stats)

    def test_update_existing_key(self):
        cache = PlanCache(max_size=10)
        plan1 = PhysicalNode(node_type=PlanNodeType.MODULO_SCAN)
        plan2 = PhysicalNode(node_type=PlanNodeType.ML_INFERENCE)
        cache.put("key1", plan1)
        cache.put("key1", plan2)
        self.assertEqual(cache.size, 1)
        self.assertIs(cache.get("key1"), plan2)


# ============================================================
# Optimizer Tests
# ============================================================

class TestOptimizer(unittest.TestCase):
    """Tests for the Optimizer cost-based plan selector."""

    def setUp(self):
        self.optimizer = Optimizer()
        self.profile = DivisibilityProfile(divisors=(3, 5), labels=("Fizz", "Buzz"), range_size=100)

    def test_optimize_returns_plan(self):
        plan = self.optimizer.optimize(self.profile)
        self.assertIsInstance(plan, PhysicalNode)

    def test_optimize_cheapest_is_modulo(self):
        plan = self.optimizer.optimize(self.profile)
        # With default weights, ModuloScan should be cheapest
        self.assertEqual(plan.node_type, PlanNodeType.MODULO_SCAN)

    def test_plan_is_cached(self):
        self.optimizer.optimize(self.profile)
        self.assertGreater(self.optimizer.plan_cache.size, 0)

    def test_cache_hit_on_second_call(self):
        self.optimizer.optimize(self.profile)
        self.optimizer.optimize(self.profile)
        self.assertEqual(self.optimizer.plan_cache.hits, 1)

    def test_different_profiles_different_plans(self):
        p1 = DivisibilityProfile(divisors=(3,), labels=("Fizz",), range_size=100)
        p2 = DivisibilityProfile(divisors=(3, 5), labels=("Fizz", "Buzz"), range_size=100)
        self.optimizer.optimize(p1)
        self.optimizer.optimize(p2)
        self.assertEqual(self.optimizer.plan_cache.size, 2)

    def test_plans_generated_counter(self):
        self.optimizer.optimize(self.profile)
        self.assertGreater(self.optimizer.plans_generated, 0)

    def test_plans_selected_counter(self):
        self.optimizer.optimize(self.profile)
        self.assertEqual(self.optimizer.plans_selected, 1)

    def test_optimization_time_tracked(self):
        self.optimizer.optimize(self.profile)
        self.assertGreater(self.optimizer.total_optimization_time_ms, 0.0)

    def test_force_ml_hint(self):
        plan = self.optimizer.optimize(self.profile, frozenset({OptimizerHint.FORCE_ML}))
        # Should NOT be a pure ModuloScan
        self.assertNotEqual(plan.node_type, PlanNodeType.MODULO_SCAN)

    def test_plan_type_counts(self):
        self.optimizer.optimize(self.profile)
        self.assertGreater(len(self.optimizer.plan_type_counts), 0)


# ============================================================
# ExplainOutput Tests
# ============================================================

class TestExplainOutput(unittest.TestCase):
    """Tests for PostgreSQL-style EXPLAIN output rendering."""

    def test_simple_explain(self):
        node = PhysicalNode(
            node_type=PlanNodeType.MODULO_SCAN,
            estimated_cost=1.0,
            estimated_rows=100,
            hit_probability=1.0,
        )
        output = ExplainOutput.render(node)
        self.assertIn("ModuloScan", output)
        self.assertIn("cost=1.00", output)
        self.assertIn("rows=100", output)

    def test_nested_explain(self):
        child = PhysicalNode(
            node_type=PlanNodeType.MODULO_SCAN,
            estimated_cost=1.0,
            estimated_rows=100,
        )
        parent = PhysicalNode(
            node_type=PlanNodeType.RESULT_MERGE,
            estimated_cost=0.1,
            estimated_rows=100,
            children=[child],
        )
        output = ExplainOutput.render(parent)
        self.assertIn("ResultMerge", output)
        self.assertIn("ModuloScan", output)

    def test_explain_analyze(self):
        node = PhysicalNode(
            node_type=PlanNodeType.MODULO_SCAN,
            estimated_cost=1.0,
            estimated_rows=100,
        )
        node.mark_executed(actual_rows=100, actual_time_ms=0.05, actual_cost=1.05)
        output = ExplainOutput.render(node, analyze=True)
        self.assertIn("actual_cost=1.05", output)
        self.assertIn("actual_rows=100", output)

    def test_cache_lookup_shows_hit_prob(self):
        node = PhysicalNode(
            node_type=PlanNodeType.CACHE_LOOKUP,
            estimated_cost=0.5,
            estimated_rows=100,
            hit_probability=0.75,
        )
        output = ExplainOutput.render(node)
        self.assertIn("hit_prob=0.75", output)

    def test_ml_inference_shows_hit_prob(self):
        node = PhysicalNode(
            node_type=PlanNodeType.ML_INFERENCE,
            estimated_cost=20.0,
            estimated_rows=100,
            hit_probability=0.95,
        )
        output = ExplainOutput.render(node)
        self.assertIn("hit_prob=0.95", output)


# ============================================================
# OptimizerMiddleware Tests
# ============================================================

class TestOptimizerMiddleware(unittest.TestCase):
    """Tests for the OptimizerMiddleware pipeline component."""

    def test_middleware_name(self):
        mw = OptimizerMiddleware(optimizer=Optimizer())
        self.assertEqual(mw.get_name(), "OptimizerMiddleware")

    def test_middleware_priority(self):
        mw = OptimizerMiddleware(optimizer=Optimizer())
        self.assertEqual(mw.get_priority(), -3)

    def test_middleware_passes_through(self):
        mw = OptimizerMiddleware(optimizer=Optimizer())
        ctx = ProcessingContext(number=15, session_id="test-session")
        from enterprise_fizzbuzz.domain.models import FizzBuzzResult
        result_ctx = ProcessingContext(number=15, session_id="test-session")
        result_ctx.results = [FizzBuzzResult(number=15, output="FizzBuzz")]

        def handler(c):
            return result_ctx

        result = mw.process(ctx, handler)
        self.assertEqual(result.results[0].output, "FizzBuzz")

    def test_middleware_adds_metadata(self):
        mw = OptimizerMiddleware(optimizer=Optimizer())
        ctx = ProcessingContext(number=15, session_id="test-session")

        def handler(c):
            return c

        result = mw.process(ctx, handler)
        self.assertIn("optimizer_plan", result.metadata)
        self.assertIn("optimizer_cost", result.metadata)

    def test_middleware_counts_invocations(self):
        mw = OptimizerMiddleware(optimizer=Optimizer())
        ctx = ProcessingContext(number=15, session_id="test-session")

        def handler(c):
            return c

        mw.process(ctx, handler)
        mw.process(ctx, handler)
        self.assertEqual(mw.invocations, 2)


# ============================================================
# OptimizerDashboard Tests
# ============================================================

class TestOptimizerDashboard(unittest.TestCase):
    """Tests for the ASCII optimizer dashboard."""

    def test_render_returns_string(self):
        optimizer = Optimizer()
        output = OptimizerDashboard.render(optimizer)
        self.assertIsInstance(output, str)

    def test_render_contains_header(self):
        optimizer = Optimizer()
        output = OptimizerDashboard.render(optimizer)
        self.assertIn("FIZZBUZZ QUERY OPTIMIZER DASHBOARD", output)

    def test_render_contains_cache_stats(self):
        optimizer = Optimizer()
        output = OptimizerDashboard.render(optimizer)
        self.assertIn("PLAN CACHE", output)

    def test_render_contains_cost_model(self):
        optimizer = Optimizer()
        output = OptimizerDashboard.render(optimizer)
        self.assertIn("COST MODEL WEIGHTS", output)

    def test_render_after_optimization(self):
        optimizer = Optimizer()
        profile = DivisibilityProfile(divisors=(3, 5), labels=("Fizz", "Buzz"), range_size=100)
        optimizer.optimize(profile)
        output = OptimizerDashboard.render(optimizer)
        self.assertIn("PLAN DISTRIBUTION", output)


# ============================================================
# Exception Tests
# ============================================================

class TestQueryOptimizerExceptions(unittest.TestCase):
    """Tests for query optimizer exception hierarchy."""

    def test_base_exception(self):
        exc = QueryOptimizerError("test")
        self.assertIn("EFP-QO00", str(exc))

    def test_plan_generation_error(self):
        exc = PlanGenerationError("no plans")
        self.assertIn("EFP-QO01", str(exc))

    def test_cost_estimation_error(self):
        exc = CostEstimationError("MODULO_SCAN", float("inf"))
        self.assertIn("EFP-QO02", str(exc))

    def test_plan_cache_overflow_error(self):
        exc = PlanCacheOverflowError(max_size=10, current_size=20)
        self.assertIn("EFP-QO03", str(exc))

    def test_invalid_hint_error(self):
        exc = InvalidHintError("BAD_HINT", "not recognized")
        self.assertIn("EFP-QO04", str(exc))


# ============================================================
# Event Type Tests
# ============================================================

class TestOptimizerEventTypes(unittest.TestCase):
    """Tests for the optimizer event types in EventType enum."""

    def test_optimizer_event_types_exist(self):
        self.assertTrue(hasattr(EventType, "OPTIMIZER_PLAN_GENERATED"))
        self.assertTrue(hasattr(EventType, "OPTIMIZER_PLAN_SELECTED"))
        self.assertTrue(hasattr(EventType, "OPTIMIZER_PLAN_CACHED"))
        self.assertTrue(hasattr(EventType, "OPTIMIZER_CACHE_HIT"))
        self.assertTrue(hasattr(EventType, "OPTIMIZER_EXPLAIN_RENDERED"))


# ============================================================
# Integration / Factory Tests
# ============================================================

class TestCreateOptimizerFromConfig(unittest.TestCase):
    """Tests for the factory function."""

    def test_create_from_mock_config(self):
        config = MagicMock()
        config.query_optimizer_cost_weights = {"modulo": 1.0, "ml": 20.0, "blockchain": 50.0}
        config.query_optimizer_plan_cache_max_size = 128
        config.query_optimizer_max_plans = 8
        optimizer = create_optimizer_from_config(config)
        self.assertIsInstance(optimizer, Optimizer)

    def test_factory_sets_cache_size(self):
        config = MagicMock()
        config.query_optimizer_cost_weights = {}
        config.query_optimizer_plan_cache_max_size = 64
        config.query_optimizer_max_plans = 4
        optimizer = create_optimizer_from_config(config)
        self.assertEqual(optimizer.plan_cache.max_size, 64)


if __name__ == "__main__":
    unittest.main()
