"""
Enterprise FizzBuzz Platform - FizzEconomics Exceptions (EFP-ECN00 through EFP-ECN09)
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzEconomicsError(FizzBuzzError):
    """Base exception for all FizzEconomics modeling errors.

    The FizzEconomics engine models market dynamics, option pricing,
    and portfolio risk to quantify the financial implications of each
    FizzBuzz classification. Economic context is essential for
    enterprise-grade divisibility evaluation.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-ECN00",
        context: dict | None = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class MarketEquilibriumError(FizzEconomicsError):
    """Raised when supply and demand curves do not intersect.

    Market equilibrium requires that the supply curve (upward-sloping)
    and demand curve (downward-sloping) cross at a positive price and
    quantity. Parallel or divergent curves indicate a market failure
    in the FizzBuzz commodity exchange.
    """

    def __init__(self, supply_slope: float, demand_slope: float) -> None:
        super().__init__(
            f"No market equilibrium: supply slope={supply_slope:.4f}, "
            f"demand slope={demand_slope:.4f}. Curves do not intersect.",
            error_code="EFP-ECN01",
            context={"supply_slope": supply_slope, "demand_slope": demand_slope},
        )


class BlackScholesError(FizzEconomicsError):
    """Raised when Black-Scholes option pricing yields invalid results.

    The Black-Scholes formula requires positive underlying price,
    positive strike price, non-negative time to expiry, positive
    volatility, and a defined risk-free rate. Violating any of these
    preconditions produces a meaningless option value for the FizzBuzz
    derivatives market.
    """

    def __init__(self, parameter: str, value: float, reason: str) -> None:
        super().__init__(
            f"Black-Scholes pricing error: {parameter}={value:.6f} — {reason}",
            error_code="EFP-ECN02",
            context={"parameter": parameter, "value": value, "reason": reason},
        )


class MonteCarloConvergenceError(FizzEconomicsError):
    """Raised when Monte Carlo simulation fails to converge.

    Portfolio Monte Carlo simulation estimates expected returns and
    Value-at-Risk through random sampling. Insufficient iterations
    or extreme variance can prevent convergence to a stable estimate,
    leaving the FizzBuzz portfolio risk profile undetermined.
    """

    def __init__(self, iterations: int, std_error: float, tolerance: float) -> None:
        super().__init__(
            f"Monte Carlo simulation did not converge after {iterations} iterations: "
            f"standard error {std_error:.6f} exceeds tolerance {tolerance:.6f}",
            error_code="EFP-ECN03",
            context={
                "iterations": iterations,
                "std_error": std_error,
                "tolerance": tolerance,
            },
        )


class RiskMetricError(FizzEconomicsError):
    """Raised when a risk metric computation is invalid.

    Value-at-Risk (VaR) and Conditional VaR require a valid
    confidence level in (0, 1) and a non-empty return distribution.
    Invalid risk metrics would misrepresent the financial exposure
    of the FizzBuzz portfolio.
    """

    def __init__(self, metric_name: str, reason: str) -> None:
        super().__init__(
            f"Risk metric '{metric_name}' computation failed: {reason}",
            error_code="EFP-ECN04",
            context={"metric_name": metric_name, "reason": reason},
        )


class SupplyDemandError(FizzEconomicsError):
    """Raised when supply or demand curve parameters are invalid.

    Supply and demand curves must have finite, non-negative intercepts
    and slopes that produce meaningful economic behavior. A negative
    quantity or price intercept violates basic microeconomic axioms.
    """

    def __init__(self, curve_type: str, parameter: str, value: float) -> None:
        super().__init__(
            f"Invalid {curve_type} curve parameter '{parameter}'={value:.4f}",
            error_code="EFP-ECN05",
            context={"curve_type": curve_type, "parameter": parameter, "value": value},
        )


class PortfolioError(FizzEconomicsError):
    """Raised when portfolio construction violates constraints.

    A valid portfolio requires weights that sum to 1.0 (or 100%) and
    non-negative weights for long-only strategies. Weight violations
    produce inconsistent return and risk calculations.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Portfolio construction error: {reason}",
            error_code="EFP-ECN06",
            context={"reason": reason},
        )


class EconomicsMiddlewareError(FizzEconomicsError):
    """Raised when the FizzEconomics middleware pipeline encounters a fault."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzEconomics middleware error: {reason}",
            error_code="EFP-ECN07",
            context={"reason": reason},
        )
