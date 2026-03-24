"""
Enterprise FizzBuzz Platform - Service Level Indicator Framework Exceptions (EFP-SLI*)
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class ModelCheckError(FizzBuzzError):
    """Base exception for all Formal Model Checking errors.

    Raised when the FizzCheck model checking subsystem encounters
    a condition that prevents it from verifying temporal properties
    of a Kripke structure. The model may be malformed, the property
    may be unsatisfiable, or the state space may exceed resource
    limits. In any case, the platform cannot certify the correctness
    of its own subsystems, which means every subsequent FizzBuzz
    evaluation is proceeding without formal verification — a state
    of affairs that would be unacceptable in any safety-critical
    modulo arithmetic application.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-MC00"),
            context=kwargs.pop("context", {}),
        )


class ModelCheckPropertyViolationError(ModelCheckError):
    """Raised when a temporal property is violated during model checking.

    The model checker has explored the state space of a Kripke structure
    and discovered a reachable state (or infinite path) that falsifies
    the specified temporal logic formula. A counterexample trace has
    been generated, providing a step-by-step demonstration of how the
    system can reach the violating state from its initial configuration.

    This is the formal methods equivalent of catching a bug, except
    instead of "it crashed in production," you get a mathematically
    rigorous proof that your MESI cache protocol can reach an invalid
    state. Whether this makes you feel better or worse about the bug
    depends on your relationship with formal verification.
    """

    def __init__(self, property_name: str, trace_length: int) -> None:
        self.property_name = property_name
        self.trace_length = trace_length
        super().__init__(
            f"Temporal property '{property_name}' violated: "
            f"counterexample trace of {trace_length} states found. "
            f"The system can reach a state that falsifies the specification.",
            error_code="EFP-MC01",
            context={
                "property_name": property_name,
                "trace_length": trace_length,
            },
        )


class ModelCheckStateSpaceError(ModelCheckError):
    """Raised when the state space exceeds exploration limits.

    The model checker has encountered more states than the configured
    maximum during BFS/DFS exploration. This typically indicates that
    the model has an unexpectedly large (or infinite) state space,
    which can occur when variable domains are unbounded, transitions
    create new states without converging, or the model simply
    represents a system more complex than your FizzBuzz platform
    has any business modeling.

    The state space explosion problem is the central challenge of
    model checking. For a FizzBuzz platform, the fact that we've
    hit this limit is simultaneously impressive and deeply concerning.
    """

    def __init__(self, states_explored: int, max_states: int) -> None:
        self.states_explored = states_explored
        self.max_states = max_states
        super().__init__(
            f"State space explosion: explored {states_explored} states, "
            f"exceeding the maximum of {max_states}. "
            f"Consider enabling symmetry reduction or partial order reduction.",
            error_code="EFP-MC02",
            context={
                "states_explored": states_explored,
                "max_states": max_states,
            },
        )


class ModelCheckInvalidSpecError(ModelCheckError):
    """Raised when a temporal logic specification is malformed.

    The temporal property provided to the model checker does not
    form a valid LTL formula. This could mean nested operators
    are applied to non-boolean predicates, atomic propositions
    reference variables not present in the model, or the formula
    structure violates the grammar of temporal logic.

    Writing correct temporal logic specifications is notoriously
    difficult. Surveys show that even experienced formal methods
    practitioners get LTL formulas wrong approximately 37% of the
    time. For a FizzBuzz platform, the bar should theoretically
    be lower, but the specification language remains unforgiving.
    """

    def __init__(self, spec: str, reason: str) -> None:
        self.spec = spec
        self.reason = reason
        super().__init__(
            f"Invalid temporal specification '{spec}': {reason}. "
            f"The property does not form a well-typed LTL formula.",
            error_code="EFP-MC03",
            context={"spec": spec, "reason": reason},
        )

