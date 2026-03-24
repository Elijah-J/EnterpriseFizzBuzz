"""
Enterprise FizzBuzz Platform - Digital Logic Circuit Simulator (FizzGate) Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class CircuitSimulationError(FizzBuzzError):
    """Base exception for all FizzGate digital circuit simulation errors.

    Raised when the event-driven simulator encounters a condition that
    prevents correct evaluation of the combinational logic circuit.
    This includes unknown gate types, input range violations, and
    general simulation engine failures.
    """

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            error_code="EFP-CKT0",
            context={"subsystem": "fizzgate"},
        )


class CircuitTopologyError(CircuitSimulationError):
    """Raised when the circuit graph contains a structural defect.

    Structural defects include combinational loops (feedback paths
    in what should be an acyclic circuit), mismatched operand widths
    in adder chains, incorrect fan-in counts for gate types (e.g.,
    a NOT gate with two inputs), and invalid divisor values for
    modulo circuits. A topologically invalid circuit cannot be
    simulated and must be corrected at the synthesis stage.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.error_code = "EFP-CKT1"


class CircuitSteadyStateError(CircuitSimulationError):
    """Raised when the simulator fails to reach steady state.

    A well-formed combinational circuit must settle to stable output
    values within a finite number of events. If the event count
    exceeds the configured maximum, the circuit either contains an
    oscillation (which indicates a synthesis error) or the event
    budget is insufficient for the circuit's complexity.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.error_code = "EFP-CKT2"


class CircuitTimingViolationError(CircuitSimulationError):
    """Raised when circuit settle time exceeds the configured timing budget.

    The timing budget defines the maximum acceptable propagation delay
    from input assertion to output stability. A violation indicates
    that the critical path through the circuit is too long for the
    target operating frequency, and the circuit requires optimization
    (e.g., carry-lookahead adders, logic restructuring, or pipeline
    registers).
    """

    def __init__(self, settle_ns: float, budget_ns: float, number: int) -> None:
        self.settle_ns = settle_ns
        self.budget_ns = budget_ns
        self.number = number
        super().__init__(
            f"Circuit settle time {settle_ns:.1f} ns exceeds budget {budget_ns:.1f} ns "
            f"for input {number}. Critical path optimization required.",
        )
        self.error_code = "EFP-CKT3"

