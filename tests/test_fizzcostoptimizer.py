"""
Enterprise FizzBuzz Platform - FizzCostOptimizer FinOps Test Suite

Comprehensive test suite for the FizzCostOptimizer subsystem, validating
cost recording and aggregation, waste detection with savings recommendations,
budget management with overspend alerting, ASCII dashboard rendering,
middleware pipeline participation, and factory assembly.

FinOps cost optimization is indispensable for any enterprise FizzBuzz
deployment. Without continuous utilization analysis, operators risk
over-provisioning divisibility-check compute, accumulating orphaned
storage volumes for retired modulo tables, and paying license fees for
unused fizz-to-buzz translation modules. The FizzCostOptimizer subsystem
ensures every cycle spent on integer classification is accounted for and
justified against organizational budget thresholds.
"""

from __future__ import annotations

from unittest.mock import MagicMock, AsyncMock

import pytest

from enterprise_fizzbuzz.infrastructure.fizzcostoptimizer import (
    FIZZCOSTOPTIMIZER_VERSION,
    MIDDLEWARE_PRIORITY,
    WasteCategory,
    CostTier,
    FizzCostOptimizerConfig,
    CostEntry,
    SavingsRecommendation,
    CostAnalyzer,
    WasteDetector,
    BudgetManager,
    FizzCostOptimizerDashboard,
    FizzCostOptimizerMiddleware,
    create_fizzcostoptimizer_subsystem,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def analyzer():
    """Fresh CostAnalyzer for each test."""
    return CostAnalyzer()


@pytest.fixture
def detector():
    """Fresh WasteDetector for each test."""
    return WasteDetector()


@pytest.fixture
def budget_manager():
    """Fresh BudgetManager for each test."""
    return BudgetManager()


@pytest.fixture
def populated_analyzer(analyzer):
    """CostAnalyzer pre-loaded with representative cost entries."""
    analyzer.record_cost("fizz-compute", CostTier.COMPUTE, 150.0)
    analyzer.record_cost("fizz-compute", CostTier.COMPUTE, 200.0)
    analyzer.record_cost("buzz-storage", CostTier.STORAGE, 80.0)
    analyzer.record_cost("network-egress", CostTier.NETWORK, 45.0)
    analyzer.record_cost("license-pool", CostTier.LICENSE, 300.0)
    return analyzer


# ============================================================
# TestConstants
# ============================================================


class TestConstants:
    """Verify module-level constants are set to their documented values."""

    def test_version(self):
        assert FIZZCOSTOPTIMIZER_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 194


# ============================================================
# TestCostAnalyzer
# ============================================================


class TestCostAnalyzer:
    """Tests for cost recording, aggregation by service and tier,
    total computation, and entry listing."""

    def test_record_cost_returns_cost_entry(self, analyzer):
        entry = analyzer.record_cost("fizz-core", CostTier.COMPUTE, 99.50)
        assert isinstance(entry, CostEntry)
        assert entry.service == "fizz-core"
        assert entry.tier == CostTier.COMPUTE
        assert entry.amount == 99.50
        assert entry.entry_id  # non-empty unique identifier

    def test_get_total_cost_sums_all_entries(self, populated_analyzer):
        total = populated_analyzer.get_total_cost()
        assert total == pytest.approx(775.0)

    def test_get_cost_by_service_filters_correctly(self, populated_analyzer):
        compute_cost = populated_analyzer.get_cost_by_service("fizz-compute")
        assert compute_cost == pytest.approx(350.0)

    def test_get_cost_by_tier_filters_correctly(self, populated_analyzer):
        storage_cost = populated_analyzer.get_cost_by_tier(CostTier.STORAGE)
        assert storage_cost == pytest.approx(80.0)

    def test_list_costs_returns_all_entries(self, populated_analyzer):
        costs = populated_analyzer.list_costs()
        assert isinstance(costs, list)
        assert len(costs) == 5
        assert all(isinstance(c, CostEntry) for c in costs)


# ============================================================
# TestWasteDetector
# ============================================================


class TestWasteDetector:
    """Tests for waste analysis and savings recommendation generation."""

    def test_analyze_returns_recommendations(self, detector, populated_analyzer):
        costs = populated_analyzer.list_costs()
        recommendations = detector.analyze(costs)
        assert isinstance(recommendations, list)
        for rec in recommendations:
            assert isinstance(rec, SavingsRecommendation)
            assert rec.rec_id  # non-empty identifier
            assert isinstance(rec.category, WasteCategory)
            assert rec.savings >= 0

    def test_get_total_savings_after_analysis(self, detector, populated_analyzer):
        costs = populated_analyzer.list_costs()
        recommendations = detector.analyze(costs)
        total_savings = detector.get_total_savings()
        # Total savings must equal the sum of individual recommendation savings
        expected = sum(r.savings for r in recommendations)
        assert total_savings == pytest.approx(expected)

    def test_get_total_savings_zero_before_analysis(self, detector):
        assert detector.get_total_savings() == 0.0


# ============================================================
# TestBudgetManager
# ============================================================


class TestBudgetManager:
    """Tests for budget setting, checking, and listing."""

    def test_set_and_check_budget_within_limit(self, budget_manager, analyzer):
        budget_manager.set_budget("fizz-compute", 500.0)
        analyzer.record_cost("fizz-compute", CostTier.COMPUTE, 200.0)
        within, remaining = budget_manager.check_budget("fizz-compute")
        assert isinstance(within, bool)
        assert isinstance(remaining, float)

    def test_list_budgets_returns_all_set_budgets(self, budget_manager):
        budget_manager.set_budget("fizz-compute", 500.0)
        budget_manager.set_budget("buzz-storage", 200.0)
        budgets = budget_manager.list_budgets()
        assert isinstance(budgets, dict)
        assert "fizz-compute" in budgets
        assert "buzz-storage" in budgets
        assert budgets["fizz-compute"] == 500.0
        assert budgets["buzz-storage"] == 200.0

    def test_list_budgets_empty_initially(self, budget_manager):
        budgets = budget_manager.list_budgets()
        assert isinstance(budgets, dict)
        assert len(budgets) == 0


# ============================================================
# TestDashboard
# ============================================================


class TestDashboard:
    """Tests for the ASCII dashboard rendering."""

    def test_render_returns_string(self):
        dashboard = FizzCostOptimizerDashboard()
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_contains_header(self):
        dashboard = FizzCostOptimizerDashboard()
        output = dashboard.render()
        # Dashboard must contain recognizable section identifiers
        output_lower = output.lower()
        assert "cost" in output_lower or "finops" in output_lower or "optimizer" in output_lower


# ============================================================
# TestMiddleware
# ============================================================


class TestMiddleware:
    """Tests for FizzCostOptimizerMiddleware pipeline integration."""

    def test_get_name(self):
        mw = FizzCostOptimizerMiddleware()
        assert mw.get_name() == "fizzcostoptimizer"

    def test_get_priority(self):
        mw = FizzCostOptimizerMiddleware()
        assert mw.get_priority() == 194

    def test_process_calls_next(self):
        mw = FizzCostOptimizerMiddleware()
        ctx = MagicMock()
        next_handler = MagicMock()
        next_handler.return_value = ctx
        result = mw.process(ctx, next_handler)
        next_handler.assert_called_once()


# ============================================================
# TestCreateSubsystem
# ============================================================


class TestCreateSubsystem:
    """Tests for the factory function that assembles the subsystem."""

    def test_returns_tuple_of_three(self):
        result = create_fizzcostoptimizer_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_contains_correct_types(self):
        analyzer, dashboard, middleware = create_fizzcostoptimizer_subsystem()
        assert isinstance(analyzer, CostAnalyzer)
        assert isinstance(dashboard, FizzCostOptimizerDashboard)
        assert isinstance(middleware, FizzCostOptimizerMiddleware)

    def test_components_are_functional(self):
        analyzer, dashboard, middleware = create_fizzcostoptimizer_subsystem()
        # Analyzer can record costs
        entry = analyzer.record_cost("test-svc", CostTier.COMPUTE, 42.0)
        assert isinstance(entry, CostEntry)
        assert entry.amount == 42.0
        # Dashboard renders
        output = dashboard.render()
        assert isinstance(output, str)
        # Middleware has correct identity
        assert middleware.get_name() == "fizzcostoptimizer"
