"""
Enterprise FizzBuzz Platform - FizzEpidemiology Exceptions (EFP-EP00 through EFP-EP07)
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzEpidemiologyError(FizzBuzzError):
    """Base exception for the FizzEpidemiology disease spread modeler.

    Epidemiological modeling of FizzBuzz classification cascades involves
    SIR/SEIR compartmental models, contact tracing graph traversal, and
    vaccination strategy optimization. Each model has parameter validity
    ranges and structural assumptions that may be violated.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-EP00",
        context: dict | None = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class ReproductionNumberError(FizzEpidemiologyError):
    """Raised when the basic reproduction number R0 is non-physical.

    R0 must be non-negative and finite. R0 = 0 indicates no transmission,
    while R0 < 0 is non-physical. Extremely large R0 values (> 100)
    indicate a modeling error rather than genuine hyper-transmissibility.
    """

    def __init__(self, r0: float, reason: str) -> None:
        super().__init__(
            f"Non-physical basic reproduction number R0={r0:.4f}: {reason}",
            error_code="EFP-EP01",
            context={"r0": r0, "reason": reason},
        )
        self.r0 = r0


class CompartmentError(FizzEpidemiologyError):
    """Raised when compartment populations violate conservation constraints.

    In SIR/SEIR models, the sum of all compartment populations must
    equal the total population at all times. Negative compartment
    populations are non-physical and indicate numerical instability
    in the ODE solver.
    """

    def __init__(self, compartment: str, population: float, total: float) -> None:
        super().__init__(
            f"Compartment '{compartment}' has non-physical population "
            f"{population:.4f} (total: {total:.4f})",
            error_code="EFP-EP02",
            context={
                "compartment": compartment,
                "population": population,
                "total": total,
            },
        )
        self.compartment = compartment
        self.population = population


class ContactTracingError(FizzEpidemiologyError):
    """Raised when the contact tracing graph contains cycles or disconnections.

    The contact tracing algorithm requires a directed acyclic graph of
    exposure events. Cycles in the graph indicate temporal inconsistency
    (a person cannot infect someone before being infected themselves).
    """

    def __init__(self, node_id: str, reason: str) -> None:
        super().__init__(
            f"Contact tracing error at node '{node_id}': {reason}",
            error_code="EFP-EP03",
            context={"node_id": node_id, "reason": reason},
        )
        self.node_id = node_id


class VaccinationStrategyError(FizzEpidemiologyError):
    """Raised when a vaccination strategy violates resource constraints.

    Vaccination rates cannot exceed the available supply, and the
    coverage fraction must lie in [0, 1]. Additionally, vaccine
    efficacy must be in (0, 1] — a vaccine with zero efficacy is
    not a vaccine.
    """

    def __init__(self, strategy: str, reason: str) -> None:
        super().__init__(
            f"Vaccination strategy '{strategy}' is invalid: {reason}",
            error_code="EFP-EP04",
            context={"strategy": strategy, "reason": reason},
        )
        self.strategy = strategy


class HerdImmunityError(FizzEpidemiologyError):
    """Raised when herd immunity threshold computation fails.

    The herd immunity threshold is 1 - 1/R0, which requires R0 > 1.
    When R0 <= 1, the disease does not spread endemically and the
    concept of a herd immunity threshold is not applicable.
    """

    def __init__(self, r0: float) -> None:
        super().__init__(
            f"Herd immunity threshold undefined for R0={r0:.4f} (requires R0 > 1)",
            error_code="EFP-EP05",
            context={"r0": r0},
        )
        self.r0 = r0


class SEIRParameterError(FizzEpidemiologyError):
    """Raised when SEIR model parameters are out of valid range.

    Transmission rate (beta), recovery rate (gamma), and incubation
    rate (sigma) must all be positive. The infectious period (1/gamma)
    and incubation period (1/sigma) must be physically reasonable.
    """

    def __init__(self, parameter: str, value: float, valid_range: str) -> None:
        super().__init__(
            f"SEIR parameter '{parameter}' = {value:.6f} is outside "
            f"valid range {valid_range}",
            error_code="EFP-EP06",
            context={"parameter": parameter, "value": value, "valid_range": valid_range},
        )
        self.parameter = parameter
        self.value = value


class EpidemiologyMiddlewareError(FizzEpidemiologyError):
    """Raised when the FizzEpidemiology middleware encounters a fault."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzEpidemiology middleware error: {reason}",
            error_code="EFP-EP07",
            context={"reason": reason},
        )
