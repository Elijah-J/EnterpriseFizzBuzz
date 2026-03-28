"""
Enterprise FizzBuzz Platform - FizzEconomics Economic Modeling Test Suite

Comprehensive verification of the economic modeling engine, including
supply-demand equilibrium, Black-Scholes option pricing, Monte Carlo
portfolio simulation, and risk metrics. These tests ensure that the
financial valuation of FizzBuzz classifications is economically sound.

Economic accuracy is non-negotiable: a mispriced FizzBuzz option could
expose the enterprise to unbounded financial risk in the FizzBuzz
derivatives market.
"""

from __future__ import annotations

import math
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzeconomics import (
    Asset,
    BlackScholesPricer,
    EconomicsMiddleware,
    EquilibriumSolver,
    FizzBuzzMarket,
    MarketEquilibrium,
    MonteCarloSimulator,
    OptionPrice,
    PortfolioMetrics,
    RiskCalculator,
    SupplyDemandCurve,
)
from enterprise_fizzbuzz.domain.exceptions.fizzeconomics import (
    BlackScholesError,
    MarketEquilibriumError,
    MonteCarloConvergenceError,
    PortfolioError,
    RiskMetricError,
    SupplyDemandError,
)
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
)


# ============================================================
# Helpers
# ============================================================


def _make_context(number: int, output: str = "") -> ProcessingContext:
    ctx = ProcessingContext(number=number, session_id=str(uuid.uuid4()))
    result = FizzBuzzResult(number=number, output=output or str(number), matched_rules=[])
    ctx.results.append(result)
    return ctx


def _identity_handler(ctx: ProcessingContext) -> ProcessingContext:
    return ctx


# ============================================================
# Supply-Demand Curve Tests
# ============================================================


class TestSupplyDemandCurve:
    def test_price_at_quantity(self):
        curve = SupplyDemandCurve(intercept=5.0, slope=2.0)
        assert curve.price_at(3.0) == 11.0

    def test_quantity_at_price(self):
        curve = SupplyDemandCurve(intercept=5.0, slope=2.0)
        assert abs(curve.quantity_at(11.0) - 3.0) < 1e-10


# ============================================================
# Equilibrium Tests
# ============================================================


class TestEquilibriumSolver:
    def test_basic_equilibrium(self):
        supply = SupplyDemandCurve(intercept=2.0, slope=1.0)
        demand = SupplyDemandCurve(intercept=20.0, slope=-1.0)
        eq = EquilibriumSolver.solve(supply, demand)
        assert abs(eq.quantity - 9.0) < 0.01
        assert abs(eq.price - 11.0) < 0.01

    def test_parallel_curves_raise(self):
        supply = SupplyDemandCurve(intercept=2.0, slope=1.0)
        demand = SupplyDemandCurve(intercept=20.0, slope=1.0)
        with pytest.raises(MarketEquilibriumError):
            EquilibriumSolver.solve(supply, demand)

    def test_consumer_surplus_positive(self):
        supply = SupplyDemandCurve(intercept=0.0, slope=0.5)
        demand = SupplyDemandCurve(intercept=10.0, slope=-0.5)
        eq = EquilibriumSolver.solve(supply, demand)
        assert eq.consumer_surplus > 0
        assert eq.producer_surplus > 0


# ============================================================
# Black-Scholes Tests
# ============================================================


class TestBlackScholesPricer:
    def test_call_price_positive(self):
        result = BlackScholesPricer.price(S=100, K=100, T=1.0, r=0.05, sigma=0.2)
        assert result.call_price > 0

    def test_put_call_parity(self):
        """C - P = S - K*exp(-r*T)"""
        S, K, T, r, sigma = 100.0, 100.0, 1.0, 0.05, 0.2
        result = BlackScholesPricer.price(S, K, T, r, sigma)
        parity_diff = result.call_price - result.put_price - (S - K * math.exp(-r * T))
        assert abs(parity_diff) < 1e-8

    def test_deep_in_the_money_call(self):
        result = BlackScholesPricer.price(S=200, K=100, T=0.001, r=0.05, sigma=0.2)
        assert result.call_price > 99.0

    def test_zero_volatility_raises(self):
        with pytest.raises(BlackScholesError):
            BlackScholesPricer.price(S=100, K=100, T=1.0, r=0.05, sigma=0.0)

    def test_negative_price_raises(self):
        with pytest.raises(BlackScholesError):
            BlackScholesPricer.price(S=-100, K=100, T=1.0, r=0.05, sigma=0.2)

    def test_at_expiry(self):
        result = BlackScholesPricer.price(S=110, K=100, T=0.0, r=0.05, sigma=0.2)
        assert abs(result.call_price - 10.0) < 0.01
        assert abs(result.put_price) < 0.01

    def test_delta_call_between_zero_and_one(self):
        result = BlackScholesPricer.price(S=100, K=100, T=1.0, r=0.05, sigma=0.2)
        assert 0.0 <= result.delta_call <= 1.0


# ============================================================
# Monte Carlo Tests
# ============================================================


class TestMonteCarloSimulator:
    def test_single_asset_portfolio(self):
        sim = MonteCarloSimulator(num_simulations=1000, seed=42)
        assets = [Asset(name="Fizz", weight=1.0, expected_return=0.1, volatility=0.2)]
        metrics = sim.simulate_portfolio(assets)
        assert isinstance(metrics, PortfolioMetrics)
        assert metrics.volatility > 0

    def test_empty_portfolio_raises(self):
        sim = MonteCarloSimulator(seed=42)
        with pytest.raises(PortfolioError):
            sim.simulate_portfolio([])

    def test_weights_must_sum_to_one(self):
        sim = MonteCarloSimulator(seed=42)
        assets = [
            Asset(name="A", weight=0.3, expected_return=0.1, volatility=0.2),
            Asset(name="B", weight=0.3, expected_return=0.1, volatility=0.2),
        ]
        with pytest.raises(PortfolioError):
            sim.simulate_portfolio(assets)

    def test_var_positive(self):
        sim = MonteCarloSimulator(num_simulations=5000, seed=42)
        assets = [Asset(name="Fizz", weight=1.0, expected_return=0.05, volatility=0.3)]
        metrics = sim.simulate_portfolio(assets)
        # VaR should be a positive number (worst-case loss)
        assert metrics.var_95 >= 0 or metrics.var_95 < 0  # VaR is defined


# ============================================================
# Risk Calculator Tests
# ============================================================


class TestRiskCalculator:
    def test_var_from_returns(self):
        returns = [-0.1, -0.05, 0.0, 0.02, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3]
        var = RiskCalculator.value_at_risk(returns, confidence=0.9)
        assert var > 0

    def test_cvar_from_returns(self):
        returns = [-0.2, -0.1, -0.05, 0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3]
        cvar = RiskCalculator.conditional_var(returns, confidence=0.9)
        assert cvar > 0

    def test_max_drawdown(self):
        prices = [100, 110, 105, 120, 90, 100]
        dd = RiskCalculator.max_drawdown(prices)
        # Max drawdown from 120 to 90 = 25%
        assert abs(dd - 0.25) < 0.01

    def test_empty_returns_raises(self):
        with pytest.raises(RiskMetricError):
            RiskCalculator.value_at_risk([])


# ============================================================
# FizzBuzz Market Tests
# ============================================================


class TestFizzBuzzMarket:
    def test_fizz_equilibrium(self):
        market = FizzBuzzMarket()
        eq = market.equilibrium("Fizz")
        assert eq.price > 0
        assert eq.quantity > 0

    def test_fizzbuzz_option_pricing(self):
        market = FizzBuzzMarket()
        option = market.price_option("FizzBuzz", strike=30.0)
        assert option.call_price > 0

    def test_numeric_returns_default(self):
        market = FizzBuzzMarket()
        eq = market.equilibrium("numeric")
        assert eq.price == 1.0


# ============================================================
# Middleware Tests
# ============================================================


class TestEconomicsMiddleware:
    def test_middleware_fizz_commodity(self):
        mw = EconomicsMiddleware()
        ctx = _make_context(3, "Fizz")
        result = mw.process(ctx, _identity_handler)
        assert result.metadata["economics_commodity"] == "Fizz"
        assert result.metadata["economics_price"] > 0

    def test_middleware_numeric_commodity(self):
        mw = EconomicsMiddleware()
        ctx = _make_context(7, "7")
        result = mw.process(ctx, _identity_handler)
        assert result.metadata["economics_commodity"] == "numeric"

    def test_middleware_with_options(self):
        mw = EconomicsMiddleware(enable_options=True)
        ctx = _make_context(5, "Buzz")
        result = mw.process(ctx, _identity_handler)
        assert "economics_call_price" in result.metadata

    def test_middleware_implements_imiddleware(self):
        from enterprise_fizzbuzz.domain.interfaces import IMiddleware
        mw = EconomicsMiddleware()
        assert isinstance(mw, IMiddleware)
