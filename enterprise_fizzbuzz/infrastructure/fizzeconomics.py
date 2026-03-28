"""
Enterprise FizzBuzz Platform - FizzEconomics Economic Modeling Engine

Models supply and demand dynamics, market equilibrium, portfolio risk,
and option pricing to quantify the economic implications of FizzBuzz
classification decisions. Every divisibility determination carries
financial weight in the FizzBuzz commodity exchange.

The FizzBuzz market operates under standard microeconomic assumptions:
"Fizz" and "Buzz" are substitute goods whose prices are determined by
supply-demand equilibrium. "FizzBuzz" is a composite commodity whose
price reflects the joint probability of divisibility by both 3 and 5.
Numbers that are neither Fizz nor Buzz are valued at par.

Portfolio simulation uses geometric Brownian motion for asset price
dynamics and the Black-Scholes model for European option pricing on
FizzBuzz futures. Value-at-Risk and Conditional VaR provide risk
metrics for portfolio exposure.

All financial computations use pure Python. No external finance
libraries are required.
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions.fizzeconomics import (
    BlackScholesError,
    EconomicsMiddlewareError,
    MarketEquilibriumError,
    MonteCarloConvergenceError,
    PortfolioError,
    RiskMetricError,
    SupplyDemandError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)


# ============================================================
# Data Classes
# ============================================================


@dataclass
class SupplyDemandCurve:
    """Linear supply or demand curve: P = intercept + slope * Q."""

    intercept: float  # price intercept
    slope: float  # dP/dQ

    def price_at(self, quantity: float) -> float:
        """Compute price at a given quantity."""
        return self.intercept + self.slope * quantity

    def quantity_at(self, price: float) -> float:
        """Compute quantity at a given price."""
        if abs(self.slope) < 1e-15:
            return 0.0
        return (price - self.intercept) / self.slope


@dataclass
class MarketEquilibrium:
    """Equilibrium point where supply equals demand."""

    price: float
    quantity: float
    consumer_surplus: float
    producer_surplus: float


@dataclass
class OptionPrice:
    """Result of Black-Scholes option pricing."""

    call_price: float
    put_price: float
    delta_call: float
    delta_put: float
    underlying: float
    strike: float
    time_to_expiry: float
    volatility: float
    risk_free_rate: float


@dataclass
class PortfolioMetrics:
    """Portfolio risk and return metrics."""

    expected_return: float
    volatility: float
    sharpe_ratio: float
    var_95: float
    cvar_95: float
    max_drawdown: float


@dataclass
class Asset:
    """A financial asset in the FizzBuzz portfolio."""

    name: str
    weight: float
    expected_return: float
    volatility: float


# ============================================================
# Supply-Demand Equilibrium
# ============================================================


class EquilibriumSolver:
    """Computes market equilibrium for the FizzBuzz commodity exchange.

    Finds the intersection of linear supply and demand curves. At
    equilibrium, the quantity supplied equals the quantity demanded,
    and the market clears at the equilibrium price.
    """

    @staticmethod
    def solve(supply: SupplyDemandCurve, demand: SupplyDemandCurve) -> MarketEquilibrium:
        """Find the equilibrium price and quantity.

        Supply: P = s_intercept + s_slope * Q  (s_slope > 0)
        Demand: P = d_intercept + d_slope * Q  (d_slope < 0)

        At equilibrium: s_intercept + s_slope * Q = d_intercept + d_slope * Q
        Q* = (d_intercept - s_intercept) / (s_slope - d_slope)
        """
        denom = supply.slope - demand.slope
        if abs(denom) < 1e-12:
            raise MarketEquilibriumError(supply.slope, demand.slope)

        q_star = (demand.intercept - supply.intercept) / denom
        p_star = supply.price_at(q_star)

        if q_star < 0 or p_star < 0:
            raise MarketEquilibriumError(supply.slope, demand.slope)

        # Consumer surplus: area between demand curve and equilibrium price
        cs = 0.5 * abs(demand.intercept - p_star) * q_star

        # Producer surplus: area between equilibrium price and supply curve
        ps = 0.5 * abs(p_star - supply.intercept) * q_star

        return MarketEquilibrium(
            price=p_star,
            quantity=q_star,
            consumer_surplus=cs,
            producer_surplus=ps,
        )


# ============================================================
# Black-Scholes Option Pricing
# ============================================================


class BlackScholesPricer:
    """European option pricing using the Black-Scholes model.

    The Black-Scholes formula prices European call and put options
    assuming geometric Brownian motion for the underlying asset,
    constant volatility, and no dividends. This model is applied
    to FizzBuzz futures to determine the fair value of the right
    to buy or sell a FizzBuzz classification at a specified price.
    """

    @staticmethod
    def _norm_cdf(x: float) -> float:
        """Standard normal cumulative distribution function."""
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

    @staticmethod
    def price(
        S: float,
        K: float,
        T: float,
        r: float,
        sigma: float,
    ) -> OptionPrice:
        """Compute Black-Scholes prices for European call and put options.

        Args:
            S: Current underlying price
            K: Strike price
            T: Time to expiry (years)
            r: Risk-free interest rate
            sigma: Volatility (annualized)
        """
        if S <= 0:
            raise BlackScholesError("S", S, "Underlying price must be positive")
        if K <= 0:
            raise BlackScholesError("K", K, "Strike price must be positive")
        if T < 0:
            raise BlackScholesError("T", T, "Time to expiry must be non-negative")
        if sigma <= 0:
            raise BlackScholesError("sigma", sigma, "Volatility must be positive")

        if T < 1e-10:
            # At expiry
            call = max(S - K, 0.0)
            put = max(K - S, 0.0)
            return OptionPrice(
                call_price=call, put_price=put,
                delta_call=1.0 if S > K else 0.0,
                delta_put=-1.0 if S < K else 0.0,
                underlying=S, strike=K, time_to_expiry=T,
                volatility=sigma, risk_free_rate=r,
            )

        sqrt_T = math.sqrt(T)
        d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqrt_T)
        d2 = d1 - sigma * sqrt_T

        cdf = BlackScholesPricer._norm_cdf

        call = S * cdf(d1) - K * math.exp(-r * T) * cdf(d2)
        put = K * math.exp(-r * T) * cdf(-d2) - S * cdf(-d1)

        delta_call = cdf(d1)
        delta_put = cdf(d1) - 1.0

        return OptionPrice(
            call_price=call,
            put_price=put,
            delta_call=delta_call,
            delta_put=delta_put,
            underlying=S,
            strike=K,
            time_to_expiry=T,
            volatility=sigma,
            risk_free_rate=r,
        )


# ============================================================
# Monte Carlo Portfolio Simulation
# ============================================================


class MonteCarloSimulator:
    """Monte Carlo simulation for FizzBuzz portfolio risk analysis.

    Generates random portfolio return scenarios using geometric
    Brownian motion to estimate expected returns, volatility,
    Value-at-Risk, and Conditional Value-at-Risk.
    """

    def __init__(
        self,
        num_simulations: int = 10000,
        time_horizon: float = 1.0,
        seed: Optional[int] = None,
    ) -> None:
        self.num_simulations = num_simulations
        self.time_horizon = time_horizon
        self._rng = random.Random(seed)

    def simulate_portfolio(self, assets: list[Asset]) -> PortfolioMetrics:
        """Run Monte Carlo simulation on a portfolio of assets."""
        if not assets:
            raise PortfolioError("Portfolio must contain at least one asset")

        total_weight = sum(a.weight for a in assets)
        if abs(total_weight - 1.0) > 0.01:
            raise PortfolioError(
                f"Portfolio weights sum to {total_weight:.4f}, expected 1.0"
            )

        # Generate portfolio returns
        returns: list[float] = []
        for _ in range(self.num_simulations):
            portfolio_return = 0.0
            for asset in assets:
                # Geometric Brownian motion: dS/S = mu*dt + sigma*dW
                z = self._rng.gauss(0, 1)
                asset_return = (
                    asset.expected_return * self.time_horizon +
                    asset.volatility * math.sqrt(self.time_horizon) * z
                )
                portfolio_return += asset.weight * asset_return
            returns.append(portfolio_return)

        returns.sort()

        # Compute metrics
        n = len(returns)
        mean_return = sum(returns) / n
        variance = sum((r - mean_return) ** 2 for r in returns) / n
        vol = math.sqrt(variance)

        # Sharpe ratio (assuming risk-free rate of 0.02)
        rf = 0.02
        sharpe = (mean_return - rf) / vol if vol > 1e-10 else 0.0

        # VaR at 95%
        idx_95 = int(0.05 * n)
        var_95 = -returns[idx_95]

        # CVaR (expected shortfall beyond VaR)
        tail = returns[:idx_95 + 1]
        cvar_95 = -sum(tail) / max(len(tail), 1)

        # Max drawdown (simplified from sorted returns)
        max_dd = max(0.0, -min(returns))

        return PortfolioMetrics(
            expected_return=mean_return,
            volatility=vol,
            sharpe_ratio=sharpe,
            var_95=var_95,
            cvar_95=cvar_95,
            max_drawdown=max_dd,
        )


# ============================================================
# Risk Metrics Calculator
# ============================================================


class RiskCalculator:
    """Computes risk metrics for FizzBuzz financial exposure.

    Provides standalone computation of Value-at-Risk and related
    metrics from a distribution of returns, independent of the
    Monte Carlo simulator.
    """

    @staticmethod
    def value_at_risk(returns: list[float], confidence: float = 0.95) -> float:
        """Compute historical Value-at-Risk at the given confidence level."""
        if not returns:
            raise RiskMetricError("VaR", "Empty return distribution")
        if not (0 < confidence < 1):
            raise RiskMetricError("VaR", f"Confidence level {confidence} not in (0, 1)")

        sorted_returns = sorted(returns)
        idx = int((1.0 - confidence) * len(sorted_returns))
        return -sorted_returns[idx]

    @staticmethod
    def conditional_var(returns: list[float], confidence: float = 0.95) -> float:
        """Compute Conditional VaR (Expected Shortfall) at the given level."""
        if not returns:
            raise RiskMetricError("CVaR", "Empty return distribution")
        if not (0 < confidence < 1):
            raise RiskMetricError("CVaR", f"Confidence level {confidence} not in (0, 1)")

        sorted_returns = sorted(returns)
        idx = int((1.0 - confidence) * len(sorted_returns))
        tail = sorted_returns[: max(idx + 1, 1)]
        return -sum(tail) / len(tail)

    @staticmethod
    def max_drawdown(prices: list[float]) -> float:
        """Compute maximum drawdown from a price series."""
        if not prices:
            raise RiskMetricError("MaxDrawdown", "Empty price series")

        peak = prices[0]
        max_dd = 0.0
        for price in prices:
            if price > peak:
                peak = price
            dd = (peak - price) / peak if peak > 0 else 0.0
            max_dd = max(max_dd, dd)
        return max_dd


# ============================================================
# FizzBuzz Market Model
# ============================================================


class FizzBuzzMarket:
    """Models the FizzBuzz commodity market.

    In the FizzBuzz economy, each classification type is a tradeable
    commodity. The supply of "Fizz" classifications is determined by
    the density of multiples of 3, while demand is driven by consumer
    preference for ternary divisibility. Market equilibrium establishes
    the fair price of each classification.
    """

    def __init__(self) -> None:
        # Default supply/demand curves for FizzBuzz commodities
        self._supply = {
            "Fizz": SupplyDemandCurve(intercept=2.0, slope=0.5),
            "Buzz": SupplyDemandCurve(intercept=3.0, slope=0.3),
            "FizzBuzz": SupplyDemandCurve(intercept=5.0, slope=0.8),
        }
        self._demand = {
            "Fizz": SupplyDemandCurve(intercept=20.0, slope=-0.4),
            "Buzz": SupplyDemandCurve(intercept=15.0, slope=-0.3),
            "FizzBuzz": SupplyDemandCurve(intercept=50.0, slope=-1.0),
        }

    def equilibrium(self, commodity: str) -> MarketEquilibrium:
        """Compute market equilibrium for a FizzBuzz commodity."""
        if commodity not in self._supply:
            return MarketEquilibrium(price=1.0, quantity=1.0,
                                     consumer_surplus=0.0, producer_surplus=0.0)

        return EquilibriumSolver.solve(
            self._supply[commodity], self._demand[commodity]
        )

    def price_option(
        self,
        commodity: str,
        strike: float,
        time_to_expiry: float = 1.0,
        volatility: float = 0.3,
    ) -> OptionPrice:
        """Price a European option on a FizzBuzz commodity."""
        eq = self.equilibrium(commodity)
        return BlackScholesPricer.price(
            S=eq.price,
            K=strike,
            T=time_to_expiry,
            r=0.05,
            sigma=volatility,
        )


# ============================================================
# FizzEconomics Middleware
# ============================================================


class EconomicsMiddleware(IMiddleware):
    """Injects economic modeling data into the FizzBuzz pipeline.

    For each number evaluated, the middleware determines the market
    value of its classification, computes option prices, and injects
    financial context into the processing metadata.
    """

    def __init__(
        self,
        market: Optional[FizzBuzzMarket] = None,
        enable_options: bool = True,
    ) -> None:
        self._market = market or FizzBuzzMarket()
        self._enable_options = enable_options

    def get_name(self) -> str:
        return "fizzeconomics"

    def get_priority(self) -> int:
        return 277

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Inject economic context and delegate to next handler."""
        try:
            output = ""
            if context.results:
                output = context.results[-1].output

            # Determine commodity type
            if output == "FizzBuzz":
                commodity = "FizzBuzz"
            elif output == "Fizz":
                commodity = "Fizz"
            elif output == "Buzz":
                commodity = "Buzz"
            else:
                commodity = "numeric"

            if commodity != "numeric":
                eq = self._market.equilibrium(commodity)
                context.metadata["economics_commodity"] = commodity
                context.metadata["economics_price"] = round(eq.price, 4)
                context.metadata["economics_quantity"] = round(eq.quantity, 4)
                context.metadata["economics_consumer_surplus"] = round(eq.consumer_surplus, 4)

                if self._enable_options:
                    option = self._market.price_option(commodity, eq.price)
                    context.metadata["economics_call_price"] = round(option.call_price, 4)
                    context.metadata["economics_put_price"] = round(option.put_price, 4)
            else:
                context.metadata["economics_commodity"] = "numeric"
                context.metadata["economics_price"] = 1.0

        except Exception as exc:
            logger.error("FizzEconomics middleware error: %s", exc)
            context.metadata["economics_error"] = str(exc)

        return next_handler(context)
