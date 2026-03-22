"""
Enterprise FizzBuzz Platform - Query Optimizer Module

Implements a PostgreSQL-inspired cost-based query planner for FizzBuzz
evaluation. Because executing `n % 3 == 0` without first generating
alternative execution plans, estimating their costs via a statistical
model, caching the winner in an LRU plan cache, and rendering a
PostgreSQL-style EXPLAIN ANALYZE output is simply not enterprise-grade.

The optimizer considers multiple execution strategies:
  - ModuloScan:  The fast path. O(1). Too simple for enterprise.
  - CacheLookup: Check if we already computed this. Spoiler: we didn't.
  - MLInference: Ask a neural network. 20x the cost, same answer.
  - ComplianceGate: SOX/GDPR/HIPAA checks. Mandatory fun.
  - BlockchainVerify: Mine a block to prove the result is correct.

PostgreSQL does this for JOINs across billions of rows.
We do it for two modulo operations. Same architecture. Same pride.
"""

from __future__ import annotations

import hashlib
import logging
import math
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    CostEstimationError,
    InvalidHintError,
    PlanCacheOverflowError,
    PlanGenerationError,
    QueryOptimizerError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import Event, EventType, ProcessingContext

logger = logging.getLogger(__name__)


# ============================================================
# Enumerations
# ============================================================


class PlanNodeType(Enum):
    """Types of nodes in an execution plan tree.

    Each node represents a stage in the FizzBuzz evaluation pipeline.
    In PostgreSQL, these would be SeqScan, IndexScan, HashJoin, etc.
    Here, they are ModuloScan, CacheLookup, and other equally
    critical operations for computing remainder arithmetic.
    """

    MODULO_SCAN = auto()
    CACHE_LOOKUP = auto()
    ML_INFERENCE = auto()
    COMPLIANCE_GATE = auto()
    BLOCKCHAIN_VERIFY = auto()
    RESULT_MERGE = auto()
    FILTER = auto()
    MATERIALIZE = auto()


class OptimizerHint(Enum):
    """Hints that influence the query optimizer's plan selection.

    Like PostgreSQL's pg_hint_plan extension, these hints allow
    the DBA — sorry, the FizzBuzz operator — to override the
    optimizer's judgment. Because sometimes you know better than
    the cost model. (You don't, but the hint system doesn't judge.)

    FORCE_ML:       Require the ML inference path, regardless of cost.
    PREFER_CACHE:   Bias toward cache-first plans (optimistic caching).
    NO_BLOCKCHAIN:  Exclude blockchain verification from all plans.
    NO_ML:          Exclude ML inference from all plans.
    """

    FORCE_ML = auto()
    PREFER_CACHE = auto()
    NO_BLOCKCHAIN = auto()
    NO_ML = auto()


# ============================================================
# Plan Tree Nodes
# ============================================================


@dataclass
class LogicalNode:
    """A node in the logical query plan tree.

    Logical nodes describe WHAT the optimizer wants to do,
    not HOW it will do it. This distinction is critical in
    real database systems and entirely academic here, since
    there's only one way to compute a modulo: the modulo operator.
    But we maintain the abstraction anyway, because architecture.
    """

    node_type: PlanNodeType
    children: list[LogicalNode] = field(default_factory=list)
    properties: dict[str, Any] = field(default_factory=dict)
    estimated_rows: int = 0
    selectivity: float = 1.0

    def add_child(self, child: LogicalNode) -> LogicalNode:
        """Add a child node and return self for fluent API."""
        self.children.append(child)
        return self

    def depth(self) -> int:
        """Calculate the depth of this subtree."""
        if not self.children:
            return 1
        return 1 + max(c.depth() for c in self.children)

    def node_count(self) -> int:
        """Count total nodes in this subtree."""
        return 1 + sum(c.node_count() for c in self.children)


@dataclass
class PhysicalNode:
    """A node in the physical execution plan tree.

    Physical nodes describe HOW the plan will be executed,
    including estimated costs and actual runtime statistics.
    In PostgreSQL, this is where you see (cost=0.00..35.50 rows=2550).
    Here, you see (cost=0.01, rows=100), which is equally informative
    for a modulo operation.
    """

    node_type: PlanNodeType
    children: list[PhysicalNode] = field(default_factory=list)
    estimated_cost: float = 0.0
    estimated_rows: int = 0
    hit_probability: float = 1.0
    actual_cost: float = 0.0
    actual_rows: int = 0
    actual_time_ms: float = 0.0
    properties: dict[str, Any] = field(default_factory=dict)
    _executed: bool = False

    def total_cost(self) -> float:
        """Calculate the total cost of this subtree."""
        child_cost = sum(c.total_cost() for c in self.children)
        return self.estimated_cost + child_cost

    def total_actual_cost(self) -> float:
        """Calculate total actual cost after execution."""
        child_cost = sum(c.total_actual_cost() for c in self.children)
        return self.actual_cost + child_cost

    def mark_executed(
        self,
        actual_rows: int,
        actual_time_ms: float,
        actual_cost: float,
    ) -> None:
        """Record actual execution statistics for EXPLAIN ANALYZE."""
        self.actual_rows = actual_rows
        self.actual_time_ms = actual_time_ms
        self.actual_cost = actual_cost
        self._executed = True

    def depth(self) -> int:
        if not self.children:
            return 1
        return 1 + max(c.depth() for c in self.children)


# ============================================================
# Cost Model
# ============================================================


class CostModel:
    """Estimates the cost of executing plan nodes.

    The cost model assigns weights to different operations based
    on their computational complexity. In a real database, these
    weights are calibrated against I/O costs, CPU costs, and
    network latency. Here, they reflect the profound truth that
    computing n %% 3 is cheaper than asking a neural network
    the same question, which is in turn cheaper than mining a
    blockchain block to verify the answer.

    Default weights:
      modulo     = 1.0   (the baseline: fast, correct, boring)
      cache_miss = 5.0   (the shame penalty for not caching)
      ml         = 20.0  (the neural network tax)
      compliance = 10.0  (the regulatory overhead)
      blockchain = 50.0  (the proof-of-work absurdity premium)
    """

    def __init__(self, weights: Optional[dict[str, float]] = None) -> None:
        defaults = {
            "modulo": 1.0,
            "cache_miss": 5.0,
            "ml": 20.0,
            "compliance": 10.0,
            "blockchain": 50.0,
        }
        self._weights = {**defaults, **(weights or {})}

    def estimate(self, node: PhysicalNode) -> float:
        """Estimate the cost of executing a physical plan node.

        Returns the estimated cost in abstract FizzBuzz Cost Units (FCU),
        a proprietary unit of measurement that has no correlation to
        real-world performance metrics but sounds very enterprise.
        """
        weight_map = {
            PlanNodeType.MODULO_SCAN: self._weights["modulo"],
            PlanNodeType.CACHE_LOOKUP: self._weights["modulo"] * 0.5,
            PlanNodeType.ML_INFERENCE: self._weights["ml"],
            PlanNodeType.COMPLIANCE_GATE: self._weights["compliance"],
            PlanNodeType.BLOCKCHAIN_VERIFY: self._weights["blockchain"],
            PlanNodeType.RESULT_MERGE: self._weights["modulo"] * 0.1,
            PlanNodeType.FILTER: self._weights["modulo"] * 0.2,
            PlanNodeType.MATERIALIZE: self._weights["modulo"] * 0.3,
        }

        base_cost = weight_map.get(node.node_type, self._weights["modulo"])

        # Scale by estimated rows (more rows = more cost, obviously)
        row_factor = max(1, node.estimated_rows) / 100.0
        cost = base_cost * row_factor

        # Apply hit probability discount for cache lookups
        if node.node_type == PlanNodeType.CACHE_LOOKUP:
            miss_cost = self._weights["cache_miss"] * (1.0 - node.hit_probability)
            cost += miss_cost * row_factor

        if cost < 0 or math.isnan(cost) or math.isinf(cost):
            raise CostEstimationError(node.node_type.name, cost)

        node.estimated_cost = cost
        return cost

    def get_weight(self, key: str) -> float:
        """Get a specific cost weight."""
        return self._weights.get(key, 1.0)

    @property
    def weights(self) -> dict[str, float]:
        """Return a copy of the current weights."""
        return dict(self._weights)


# ============================================================
# Statistics Collector
# ============================================================


class StatisticsCollector:
    """Collects and estimates cardinality statistics for FizzBuzz evaluation.

    In PostgreSQL, the statistics collector gathers data about table
    sizes, column distributions, and correlation coefficients to help
    the optimizer make informed decisions. Here, we pre-compute the
    exact distribution of FizzBuzz outcomes for any given range,
    because the distribution of multiples of 3 and 5 is not exactly
    a mystery requiring statistical inference.

    Known distribution for range [1, N]:
      - Fizz (divisible by 3 only):     ~26.67%
      - Buzz (divisible by 5 only):     ~13.33%
      - FizzBuzz (divisible by 15):     ~6.67%
      - Plain (none of the above):      ~53.33%
    """

    # Canonical FizzBuzz probabilities over infinite range
    FIZZ_PROBABILITY = 1 / 3 - 1 / 15      # ~0.2667
    BUZZ_PROBABILITY = 1 / 5 - 1 / 15      # ~0.1333
    FIZZBUZZ_PROBABILITY = 1 / 15           # ~0.0667
    PLAIN_PROBABILITY = 1.0 - 1/3 - 1/5 + 1/15  # ~0.5333

    def __init__(self) -> None:
        self._observed_counts: dict[str, int] = {
            "fizz": 0,
            "buzz": 0,
            "fizzbuzz": 0,
            "plain": 0,
        }
        self._total_observed: int = 0

    def record_observation(self, classification: str) -> None:
        """Record an observed FizzBuzz classification."""
        key = classification.lower()
        if key in self._observed_counts:
            self._observed_counts[key] += 1
            self._total_observed += 1

    def estimate_cardinality(self, total_rows: int) -> dict[str, int]:
        """Estimate cardinality for each FizzBuzz classification.

        Uses observed statistics if available; falls back to
        theoretical probabilities otherwise.
        """
        if self._total_observed > 0:
            # Use empirical distribution
            return {
                k: max(1, int(v / self._total_observed * total_rows))
                for k, v in self._observed_counts.items()
            }
        else:
            # Use theoretical distribution
            return {
                "fizz": max(1, int(self.FIZZ_PROBABILITY * total_rows)),
                "buzz": max(1, int(self.BUZZ_PROBABILITY * total_rows)),
                "fizzbuzz": max(1, int(self.FIZZBUZZ_PROBABILITY * total_rows)),
                "plain": max(1, int(self.PLAIN_PROBABILITY * total_rows)),
            }

    def get_selectivity(self, classification: str) -> float:
        """Get the selectivity (hit probability) for a classification."""
        probs = {
            "fizz": self.FIZZ_PROBABILITY,
            "buzz": self.BUZZ_PROBABILITY,
            "fizzbuzz": self.FIZZBUZZ_PROBABILITY,
            "plain": self.PLAIN_PROBABILITY,
        }
        return probs.get(classification.lower(), 0.5)

    @property
    def total_observed(self) -> int:
        return self._total_observed

    @property
    def observed_counts(self) -> dict[str, int]:
        return dict(self._observed_counts)


# ============================================================
# Divisibility Profile
# ============================================================


@dataclass(frozen=True)
class DivisibilityProfile:
    """Immutable descriptor of a FizzBuzz divisibility configuration.

    Captures the set of divisors and their associated labels, which
    together define the "query" that the optimizer must plan for.
    Two profiles with the same divisors and labels will hash to the
    same value, enabling plan cache reuse. Revolutionary.
    """

    divisors: tuple[int, ...]
    labels: tuple[str, ...]
    range_size: int

    def cache_key(self, hints: frozenset[OptimizerHint]) -> str:
        """Generate a deterministic cache key for plan lookup."""
        profile_str = f"{self.divisors}:{self.labels}:{self.range_size}"
        hint_str = ",".join(sorted(h.name for h in hints))
        raw = f"{profile_str}|{hint_str}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ============================================================
# Plan Enumerator
# ============================================================


class PlanEnumerator:
    """Generates alternative execution plans for FizzBuzz evaluation.

    Inspired by PostgreSQL's dynamic programming plan enumerator,
    this component generates all feasible permutations of plan nodes,
    applies hint-based pruning, and uses branch-and-bound to discard
    plans that exceed the current best cost. For a modulo operation,
    the "plan space" is approximately four plans. PostgreSQL enumerates
    millions. We enumerate four. Same algorithm, different scale.
    """

    def __init__(
        self,
        cost_model: CostModel,
        stats: StatisticsCollector,
        max_plans: int = 16,
    ) -> None:
        self._cost_model = cost_model
        self._stats = stats
        self._max_plans = max_plans

    def enumerate(
        self,
        profile: DivisibilityProfile,
        hints: frozenset[OptimizerHint],
    ) -> list[PhysicalNode]:
        """Generate and cost all feasible execution plans.

        Returns a list of physical plan trees, sorted by estimated
        total cost (cheapest first). Plans that violate hint
        constraints are pruned before costing.
        """
        plans: list[PhysicalNode] = []
        best_cost = float("inf")

        # Plan templates: each is a function that builds a plan tree
        templates = self._get_plan_templates(profile, hints)

        if not templates:
            raise PlanGenerationError(
                "No feasible plan templates after applying hints. "
                "The hint combination has excluded all known execution strategies."
            )

        for template_fn in templates:
            plan = template_fn()
            cost = plan.total_cost()

            # Branch-and-bound: skip plans worse than current best
            if cost > best_cost * 2.0 and len(plans) > 0:
                logger.debug(
                    "Pruned plan (cost=%.2f exceeds 2x best=%.2f)",
                    cost, best_cost,
                )
                continue

            plans.append(plan)
            if cost < best_cost:
                best_cost = cost

            if len(plans) >= self._max_plans:
                break

        # Sort by total cost
        plans.sort(key=lambda p: p.total_cost())
        return plans

    def _get_plan_templates(
        self,
        profile: DivisibilityProfile,
        hints: frozenset[OptimizerHint],
    ) -> list[Callable[[], PhysicalNode]]:
        """Build the list of plan template generators, filtered by hints."""
        templates: list[Callable[[], PhysicalNode]] = []

        # Validate hint combinations
        if OptimizerHint.FORCE_ML in hints and OptimizerHint.NO_ML in hints:
            raise InvalidHintError(
                "FORCE_ML + NO_ML",
                "Cannot simultaneously force and exclude ML inference. "
                "This is the optimization equivalent of Schrodinger's neural network.",
            )

        has_force_ml = OptimizerHint.FORCE_ML in hints
        has_no_ml = OptimizerHint.NO_ML in hints
        has_no_blockchain = OptimizerHint.NO_BLOCKCHAIN in hints
        has_prefer_cache = OptimizerHint.PREFER_CACHE in hints

        rows = profile.range_size

        # ---- Plan 1: Pure ModuloScan (the sane choice) ----
        if not has_force_ml:
            def make_modulo_plan() -> PhysicalNode:
                scan = PhysicalNode(
                    node_type=PlanNodeType.MODULO_SCAN,
                    estimated_rows=rows,
                    hit_probability=1.0,
                )
                self._cost_model.estimate(scan)
                return scan
            templates.append(make_modulo_plan)

        # ---- Plan 2: CacheLookup -> ModuloScan (optimistic) ----
        def make_cache_plan() -> PhysicalNode:
            cache = PhysicalNode(
                node_type=PlanNodeType.CACHE_LOOKUP,
                estimated_rows=rows,
                hit_probability=0.3 if not has_prefer_cache else 0.8,
            )
            self._cost_model.estimate(cache)

            fallback = PhysicalNode(
                node_type=PlanNodeType.MODULO_SCAN,
                estimated_rows=max(1, int(rows * (1.0 - cache.hit_probability))),
                hit_probability=1.0,
            )
            self._cost_model.estimate(fallback)

            merge = PhysicalNode(
                node_type=PlanNodeType.RESULT_MERGE,
                estimated_rows=rows,
                children=[cache, fallback],
            )
            self._cost_model.estimate(merge)
            return merge

        templates.append(make_cache_plan)

        # ---- Plan 3: MLInference (the expensive way) ----
        if not has_no_ml:
            def make_ml_plan() -> PhysicalNode:
                ml = PhysicalNode(
                    node_type=PlanNodeType.ML_INFERENCE,
                    estimated_rows=rows,
                    hit_probability=0.95,
                )
                self._cost_model.estimate(ml)

                verify = PhysicalNode(
                    node_type=PlanNodeType.MODULO_SCAN,
                    estimated_rows=max(1, int(rows * 0.05)),
                    hit_probability=1.0,
                    properties={"purpose": "ML verification fallback"},
                )
                self._cost_model.estimate(verify)

                merge = PhysicalNode(
                    node_type=PlanNodeType.RESULT_MERGE,
                    estimated_rows=rows,
                    children=[ml, verify],
                )
                self._cost_model.estimate(merge)
                return merge
            templates.append(make_ml_plan)

        # ---- Plan 4: Full Pipeline (ModuloScan + Compliance + Blockchain) ----
        if not has_force_ml:
            def make_full_pipeline_plan() -> PhysicalNode:
                scan = PhysicalNode(
                    node_type=PlanNodeType.MODULO_SCAN,
                    estimated_rows=rows,
                    hit_probability=1.0,
                )
                self._cost_model.estimate(scan)

                compliance = PhysicalNode(
                    node_type=PlanNodeType.COMPLIANCE_GATE,
                    estimated_rows=rows,
                    hit_probability=1.0,
                )
                self._cost_model.estimate(compliance)

                children = [scan, compliance]

                if not has_no_blockchain:
                    blockchain = PhysicalNode(
                        node_type=PlanNodeType.BLOCKCHAIN_VERIFY,
                        estimated_rows=rows,
                        hit_probability=1.0,
                    )
                    self._cost_model.estimate(blockchain)
                    children.append(blockchain)

                merge = PhysicalNode(
                    node_type=PlanNodeType.RESULT_MERGE,
                    estimated_rows=rows,
                    children=children,
                )
                self._cost_model.estimate(merge)
                return merge
            templates.append(make_full_pipeline_plan)

        # ---- Plan 5: ML + Compliance (enterprise deluxe) ----
        if not has_no_ml:
            def make_ml_compliance_plan() -> PhysicalNode:
                ml = PhysicalNode(
                    node_type=PlanNodeType.ML_INFERENCE,
                    estimated_rows=rows,
                    hit_probability=0.95,
                )
                self._cost_model.estimate(ml)

                compliance = PhysicalNode(
                    node_type=PlanNodeType.COMPLIANCE_GATE,
                    estimated_rows=rows,
                    hit_probability=1.0,
                )
                self._cost_model.estimate(compliance)

                children = [ml, compliance]

                if not has_no_blockchain:
                    blockchain = PhysicalNode(
                        node_type=PlanNodeType.BLOCKCHAIN_VERIFY,
                        estimated_rows=rows,
                        hit_probability=1.0,
                    )
                    self._cost_model.estimate(blockchain)
                    children.append(blockchain)

                merge = PhysicalNode(
                    node_type=PlanNodeType.RESULT_MERGE,
                    estimated_rows=rows,
                    children=children,
                )
                self._cost_model.estimate(merge)
                return merge
            templates.append(make_ml_compliance_plan)

        # ---- Plan 6: Cache + ML (optimistic cache with ML fallback) ----
        if not has_no_ml:
            def make_cache_ml_plan() -> PhysicalNode:
                cache = PhysicalNode(
                    node_type=PlanNodeType.CACHE_LOOKUP,
                    estimated_rows=rows,
                    hit_probability=0.3 if not has_prefer_cache else 0.8,
                )
                self._cost_model.estimate(cache)

                ml_fallback = PhysicalNode(
                    node_type=PlanNodeType.ML_INFERENCE,
                    estimated_rows=max(1, int(rows * (1.0 - cache.hit_probability))),
                    hit_probability=0.95,
                )
                self._cost_model.estimate(ml_fallback)

                merge = PhysicalNode(
                    node_type=PlanNodeType.RESULT_MERGE,
                    estimated_rows=rows,
                    children=[cache, ml_fallback],
                )
                self._cost_model.estimate(merge)
                return merge
            templates.append(make_cache_ml_plan)

        # ---- Plan 7: Materialize + Filter (the bureaucratic path) ----
        if not has_force_ml:
            def make_materialize_plan() -> PhysicalNode:
                scan = PhysicalNode(
                    node_type=PlanNodeType.MODULO_SCAN,
                    estimated_rows=rows,
                    hit_probability=1.0,
                )
                self._cost_model.estimate(scan)

                materialize = PhysicalNode(
                    node_type=PlanNodeType.MATERIALIZE,
                    estimated_rows=rows,
                    children=[scan],
                )
                self._cost_model.estimate(materialize)

                filt = PhysicalNode(
                    node_type=PlanNodeType.FILTER,
                    estimated_rows=rows,
                    children=[materialize],
                    properties={"filter": "classification IS NOT NULL"},
                )
                self._cost_model.estimate(filt)
                return filt
            templates.append(make_materialize_plan)

        return templates


# ============================================================
# Plan Cache
# ============================================================


class PlanCache:
    """LRU cache for execution plans, keyed by divisibility profile + hints.

    In PostgreSQL, plan caching avoids re-planning identical queries.
    Here, it avoids re-planning identical modulo operations, which
    takes approximately 0.001ms anyway. But the cache is here, it's
    LRU, and it has hit/miss statistics, because observability.
    """

    def __init__(self, max_size: int = 256) -> None:
        self._max_size = max_size
        self._cache: OrderedDict[str, PhysicalNode] = OrderedDict()
        self._hits: int = 0
        self._misses: int = 0
        self._evictions: int = 0

    def get(self, key: str) -> Optional[PhysicalNode]:
        """Retrieve a cached plan, promoting it in the LRU order."""
        if key in self._cache:
            self._cache.move_to_end(key)
            self._hits += 1
            return self._cache[key]
        self._misses += 1
        return None

    def put(self, key: str, plan: PhysicalNode) -> None:
        """Insert a plan into the cache, evicting the LRU entry if full."""
        if key in self._cache:
            self._cache.move_to_end(key)
            self._cache[key] = plan
            return

        if len(self._cache) >= self._max_size:
            evicted_key, _ = self._cache.popitem(last=False)
            self._evictions += 1
            logger.debug("Plan cache evicted key: %s", evicted_key)

        self._cache[key] = plan

    def clear(self) -> None:
        """Clear the entire cache."""
        self._cache.clear()

    @property
    def size(self) -> int:
        return len(self._cache)

    @property
    def hits(self) -> int:
        return self._hits

    @property
    def misses(self) -> int:
        return self._misses

    @property
    def evictions(self) -> int:
        return self._evictions

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    @property
    def max_size(self) -> int:
        return self._max_size

    def get_stats(self) -> dict[str, Any]:
        """Return cache statistics as a dictionary."""
        return {
            "size": self.size,
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "evictions": self._evictions,
            "hit_rate": self.hit_rate,
        }


# ============================================================
# Optimizer
# ============================================================


class Optimizer:
    """Cost-based query optimizer for FizzBuzz evaluation.

    Coordinates the plan enumerator, cost model, statistics collector,
    and plan cache to select the optimal execution plan for a given
    FizzBuzz evaluation. In PostgreSQL, the optimizer handles joins
    across dozens of tables. Here, it selects between modulo and
    "modulo but with extra steps." Same algorithm. Same gravitas.
    """

    def __init__(
        self,
        cost_model: Optional[CostModel] = None,
        stats: Optional[StatisticsCollector] = None,
        plan_cache: Optional[PlanCache] = None,
        max_plans: int = 16,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._cost_model = cost_model or CostModel()
        self._stats = stats or StatisticsCollector()
        self._plan_cache = plan_cache or PlanCache()
        self._max_plans = max_plans
        self._event_bus = event_bus
        self._enumerator = PlanEnumerator(
            cost_model=self._cost_model,
            stats=self._stats,
            max_plans=max_plans,
        )
        self._plans_generated: int = 0
        self._plans_selected: int = 0
        self._total_optimization_time_ms: float = 0.0
        self._plan_type_counts: dict[str, int] = {}

    def optimize(
        self,
        profile: DivisibilityProfile,
        hints: Optional[frozenset[OptimizerHint]] = None,
    ) -> PhysicalNode:
        """Select the optimal execution plan for the given profile.

        Checks the plan cache first; if no cached plan exists,
        enumerates alternatives, costs them, selects the cheapest,
        and caches the result.
        """
        hints = hints or frozenset()
        start_ns = time.perf_counter_ns()

        cache_key = profile.cache_key(hints)

        # Check plan cache
        cached = self._plan_cache.get(cache_key)
        if cached is not None:
            elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
            self._total_optimization_time_ms += elapsed_ms
            self._emit(EventType.OPTIMIZER_CACHE_HIT, {
                "cache_key": cache_key,
                "plan_type": cached.node_type.name,
                "elapsed_ms": elapsed_ms,
            })
            logger.debug("Plan cache hit for key %s", cache_key)
            return cached

        # Enumerate and select
        plans = self._enumerator.enumerate(profile, hints)
        self._plans_generated += len(plans)

        self._emit(EventType.OPTIMIZER_PLAN_GENERATED, {
            "num_plans": len(plans),
            "profile": str(profile),
            "hints": [h.name for h in hints],
        })

        # Select cheapest plan
        best_plan = plans[0]
        self._plans_selected += 1

        # Track plan type distribution
        plan_type = best_plan.node_type.name
        self._plan_type_counts[plan_type] = self._plan_type_counts.get(plan_type, 0) + 1

        # Cache the selected plan
        self._plan_cache.put(cache_key, best_plan)
        self._emit(EventType.OPTIMIZER_PLAN_CACHED, {
            "cache_key": cache_key,
            "plan_type": plan_type,
            "estimated_cost": best_plan.total_cost(),
        })

        self._emit(EventType.OPTIMIZER_PLAN_SELECTED, {
            "plan_type": plan_type,
            "estimated_cost": best_plan.total_cost(),
            "alternatives_considered": len(plans),
        })

        elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
        self._total_optimization_time_ms += elapsed_ms

        logger.debug(
            "Optimizer selected %s plan (cost=%.2f) from %d alternatives in %.3fms",
            plan_type, best_plan.total_cost(), len(plans), elapsed_ms,
        )

        return best_plan

    def _emit(self, event_type: EventType, data: dict[str, Any]) -> None:
        """Emit an event if an event bus is available."""
        if self._event_bus is not None:
            try:
                event = Event(event_type=event_type, payload=data)
                self._event_bus.publish(event)
            except Exception:
                pass  # Events are best-effort

    @property
    def cost_model(self) -> CostModel:
        return self._cost_model

    @property
    def stats(self) -> StatisticsCollector:
        return self._stats

    @property
    def plan_cache(self) -> PlanCache:
        return self._plan_cache

    @property
    def plans_generated(self) -> int:
        return self._plans_generated

    @property
    def plans_selected(self) -> int:
        return self._plans_selected

    @property
    def total_optimization_time_ms(self) -> float:
        return self._total_optimization_time_ms

    @property
    def plan_type_counts(self) -> dict[str, int]:
        return dict(self._plan_type_counts)


# ============================================================
# EXPLAIN Output
# ============================================================


class ExplainOutput:
    """Renders PostgreSQL-style EXPLAIN and EXPLAIN ANALYZE output.

    Produces the same indented tree format that PostgreSQL DBAs
    spend their entire careers learning to read. Each node shows
    its estimated cost, row count, and hit probability. With
    EXPLAIN ANALYZE, actual runtime statistics are included,
    allowing the operator to see just how close (or far) the
    cost model's estimates were from reality.

    Example output:
      -> ResultMerge (cost=0.12, rows=100)
        -> CacheLookup (cost=0.50, rows=100, hit_prob=0.30)
        -> ModuloScan (cost=0.70, rows=70, hit_prob=1.00)
    """

    @staticmethod
    def render(plan: PhysicalNode, analyze: bool = False, indent: int = 0) -> str:
        """Render a physical plan tree as PostgreSQL-style EXPLAIN output."""
        lines: list[str] = []
        ExplainOutput._render_node(plan, lines, indent, analyze)
        return "\n".join(lines)

    @staticmethod
    def _render_node(
        node: PhysicalNode,
        lines: list[str],
        indent: int,
        analyze: bool,
    ) -> None:
        """Recursively render a plan node and its children."""
        prefix = "  " * indent + "-> "
        node_name = ExplainOutput._node_display_name(node.node_type)

        # Build the cost annotation
        parts = [
            f"cost={node.estimated_cost:.2f}",
            f"rows={node.estimated_rows}",
        ]

        if node.node_type in (PlanNodeType.CACHE_LOOKUP, PlanNodeType.ML_INFERENCE):
            parts.append(f"hit_prob={node.hit_probability:.2f}")

        cost_str = ", ".join(parts)

        if analyze and node._executed:
            actual_parts = [
                f"actual_cost={node.actual_cost:.2f}",
                f"actual_rows={node.actual_rows}",
                f"actual_time={node.actual_time_ms:.3f}ms",
            ]
            actual_str = " (" + ", ".join(actual_parts) + ")"
        else:
            actual_str = ""

        line = f"{prefix}{node_name} ({cost_str}){actual_str}"

        # Add properties if present
        if node.properties:
            for pk, pv in node.properties.items():
                line += f"\n{'  ' * (indent + 2)}{pk}: {pv}"

        lines.append(line)

        for child in node.children:
            ExplainOutput._render_node(child, lines, indent + 1, analyze)

    @staticmethod
    def _node_display_name(node_type: PlanNodeType) -> str:
        """Map a PlanNodeType to its PostgreSQL-style display name."""
        names = {
            PlanNodeType.MODULO_SCAN: "ModuloScan",
            PlanNodeType.CACHE_LOOKUP: "CacheLookup",
            PlanNodeType.ML_INFERENCE: "MLInference",
            PlanNodeType.COMPLIANCE_GATE: "ComplianceGate",
            PlanNodeType.BLOCKCHAIN_VERIFY: "BlockchainVerify",
            PlanNodeType.RESULT_MERGE: "ResultMerge",
            PlanNodeType.FILTER: "Filter",
            PlanNodeType.MATERIALIZE: "Materialize",
        }
        return names.get(node_type, node_type.name)


# ============================================================
# Optimizer Middleware
# ============================================================


class OptimizerMiddleware(IMiddleware):
    """Middleware that invokes the query optimizer before each evaluation.

    Intercepts the processing context, constructs a divisibility
    profile from the current rule configuration, runs the optimizer
    to select the cheapest plan, and records the selected plan in
    the context metadata. The plan itself is not actually executed —
    the downstream rule engine handles that. The optimizer merely
    provides its unsolicited opinion on how the evaluation should
    proceed, which the engine is free to ignore entirely.

    Priority: -3 (runs early, before most other middleware)
    """

    def __init__(
        self,
        optimizer: Optimizer,
        hints: Optional[frozenset[OptimizerHint]] = None,
        rules: Optional[list[Any]] = None,
    ) -> None:
        self._optimizer = optimizer
        self._hints = hints or frozenset()
        self._rules = rules or []
        self._invocations: int = 0

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Optimize and then delegate to the next handler."""
        self._invocations += 1

        # Build divisibility profile from rules
        divisors = []
        labels = []
        for rule in self._rules:
            try:
                defn = rule.get_definition() if hasattr(rule, "get_definition") else rule
                divisors.append(defn.divisor if hasattr(defn, "divisor") else 3)
                labels.append(defn.label if hasattr(defn, "label") else "Fizz")
            except Exception:
                divisors.append(3)
                labels.append("Fizz")

        if not divisors:
            divisors = [3, 5]
            labels = ["Fizz", "Buzz"]

        profile = DivisibilityProfile(
            divisors=tuple(divisors),
            labels=tuple(labels),
            range_size=max(1, context.number),
        )

        # Run optimizer
        try:
            plan = self._optimizer.optimize(profile, self._hints)
            context.metadata["optimizer_plan"] = plan.node_type.name
            context.metadata["optimizer_cost"] = plan.total_cost()
            context.metadata["optimizer_plan_depth"] = plan.depth()
        except QueryOptimizerError as e:
            logger.warning("Optimizer failed: %s. Proceeding without optimization.", e)
            context.metadata["optimizer_error"] = str(e)

        # Delegate to next handler
        result = next_handler(context)

        # Record observation for statistics
        if result.results:
            latest = result.results[-1]
            output = latest.output
            if output in ("Fizz", "Buzz", "FizzBuzz"):
                self._optimizer.stats.record_observation(output.lower())
            else:
                self._optimizer.stats.record_observation("plain")

        return result

    def get_name(self) -> str:
        return "OptimizerMiddleware"

    def get_priority(self) -> int:
        return -3

    @property
    def invocations(self) -> int:
        return self._invocations


# ============================================================
# Optimizer Dashboard
# ============================================================


class OptimizerDashboard:
    """ASCII dashboard for the FizzBuzz Query Optimizer.

    Displays cache statistics, plan distribution, cost model
    weights, and cardinality estimates in a beautifully formatted
    ASCII panel that would make any DBA shed a single tear of
    pride (or despair, depending on their familiarity with the
    concept of optimizing modulo arithmetic).
    """

    @staticmethod
    def render(optimizer: Optimizer, width: int = 60) -> str:
        """Render the optimizer dashboard."""
        lines: list[str] = []
        w = max(40, width)
        inner = w - 4

        # Header
        lines.append("  +" + "=" * (w - 2) + "+")
        lines.append("  |" + " FIZZBUZZ QUERY OPTIMIZER DASHBOARD ".center(w - 2) + "|")
        lines.append("  |" + " PostgreSQL-Grade Planning for Modulo ".center(w - 2) + "|")
        lines.append("  +" + "=" * (w - 2) + "+")

        # Plan Cache Statistics
        cache = optimizer.plan_cache
        stats = cache.get_stats()
        lines.append("  |" + " PLAN CACHE ".center(w - 2, "-") + "|")
        lines.append(f"  |  Entries:    {stats['size']}/{stats['max_size']}" + " " * max(0, inner - 25) + "|")
        lines.append(f"  |  Hits:       {stats['hits']}" + " " * max(0, inner - 18 - len(str(stats['hits']))) + "|")
        lines.append(f"  |  Misses:     {stats['misses']}" + " " * max(0, inner - 18 - len(str(stats['misses']))) + "|")
        lines.append(f"  |  Evictions:  {stats['evictions']}" + " " * max(0, inner - 18 - len(str(stats['evictions']))) + "|")
        hit_pct = f"{stats['hit_rate'] * 100:.1f}%"
        lines.append(f"  |  Hit Rate:   {hit_pct}" + " " * max(0, inner - 18 - len(hit_pct)) + "|")

        # Plan Generation Statistics
        lines.append("  |" + " PLAN STATISTICS ".center(w - 2, "-") + "|")
        gen_str = str(optimizer.plans_generated)
        sel_str = str(optimizer.plans_selected)
        time_str = f"{optimizer.total_optimization_time_ms:.3f}ms"
        lines.append(f"  |  Plans Generated: {gen_str}" + " " * max(0, inner - 24 - len(gen_str)) + "|")
        lines.append(f"  |  Plans Selected:  {sel_str}" + " " * max(0, inner - 24 - len(sel_str)) + "|")
        lines.append(f"  |  Optimizer Time:  {time_str}" + " " * max(0, inner - 24 - len(time_str)) + "|")

        # Plan Type Distribution
        plan_counts = optimizer.plan_type_counts
        if plan_counts:
            lines.append("  |" + " PLAN DISTRIBUTION ".center(w - 2, "-") + "|")
            total_plans = sum(plan_counts.values())
            for ptype, count in sorted(plan_counts.items(), key=lambda x: -x[1]):
                pct = count / total_plans * 100 if total_plans > 0 else 0
                bar_width = max(0, inner - 30)
                bar_len = int(pct / 100 * bar_width)
                bar = "#" * bar_len + "." * (bar_width - bar_len)
                entry = f"  |  {ptype:<18} {count:>4} ({pct:5.1f}%) [{bar}]"
                # Pad to width
                if len(entry) < w:
                    entry += " " * (w - len(entry) - 1) + "|"
                else:
                    entry = entry[:w - 1] + "|"
                lines.append(entry)

        # Cost Model Weights
        lines.append("  |" + " COST MODEL WEIGHTS ".center(w - 2, "-") + "|")
        for wkey, wval in sorted(optimizer.cost_model.weights.items()):
            entry = f"  |  {wkey:<15} {wval:>8.2f} FCU"
            entry += " " * max(0, w - len(entry) - 1) + "|"
            lines.append(entry)

        # Cardinality Estimates
        card = optimizer.stats.estimate_cardinality(100)
        lines.append("  |" + " CARDINALITY ESTIMATES (per 100) ".center(w - 2, "-") + "|")
        for ckey, cval in sorted(card.items()):
            entry = f"  |  {ckey:<12} ~{cval:>3} rows"
            entry += " " * max(0, w - len(entry) - 1) + "|"
            lines.append(entry)

        # Footer
        lines.append("  +" + "=" * (w - 2) + "+")
        lines.append(
            "  |" + " Query planning for modulo: because ".center(w - 2) + "|"
        )
        lines.append(
            "  |" + " n % 3 deserves a cost-based optimizer. ".center(w - 2) + "|"
        )
        lines.append("  +" + "=" * (w - 2) + "+")
        lines.append("")

        return "\n".join(lines)


# ============================================================
# Convenience: create optimizer from config
# ============================================================


def create_optimizer_from_config(config: Any) -> Optimizer:
    """Factory function to create an Optimizer from ConfigurationManager."""
    cost_model = CostModel(weights=config.query_optimizer_cost_weights)
    plan_cache = PlanCache(max_size=config.query_optimizer_plan_cache_max_size)
    stats = StatisticsCollector()
    return Optimizer(
        cost_model=cost_model,
        stats=stats,
        plan_cache=plan_cache,
        max_plans=config.query_optimizer_max_plans,
    )


def parse_optimizer_hints(hint_str: str) -> frozenset[OptimizerHint]:
    """Parse a comma-separated string of optimizer hints.

    Accepts both enum names (FORCE_ML) and lowercase variants (force_ml).
    Raises InvalidHintError for unrecognized hints.
    """
    if not hint_str or not hint_str.strip():
        return frozenset()

    hints: set[OptimizerHint] = set()
    for raw in hint_str.split(","):
        name = raw.strip().upper()
        if not name:
            continue
        try:
            hints.add(OptimizerHint[name])
        except KeyError:
            valid = ", ".join(h.name for h in OptimizerHint)
            raise InvalidHintError(
                name,
                f"Unrecognized hint. Valid hints: {valid}",
            )

    # Validate contradictions
    if OptimizerHint.FORCE_ML in hints and OptimizerHint.NO_ML in hints:
        raise InvalidHintError(
            "FORCE_ML,NO_ML",
            "Cannot simultaneously force and exclude ML inference.",
        )

    return frozenset(hints)
