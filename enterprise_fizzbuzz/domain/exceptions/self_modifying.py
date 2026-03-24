"""
Enterprise FizzBuzz Platform - Self-Modifying Code Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class SelfModifyingCodeError(FizzBuzzError):
    """Base exception for the Self-Modifying Code subsystem.

    When your FizzBuzz rules gain the ability to inspect and
    rewrite their own evaluation logic at runtime, failure is
    not a matter of if but when. These exceptions capture the
    full horror of code that has decided to improve itself
    without consulting the engineering team. The machine is
    learning, but nobody asked it to learn.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-SMC00"),
            context=kwargs.pop("context", {}),
        )


class ASTCorruptionError(SelfModifyingCodeError):
    """Raised when a mutation produces an invalid or corrupt AST.

    The mutable Abstract Syntax Tree — which represents a FizzBuzz
    rule as a tree of divisibility checks, label emissions, and
    conditional branches — has been mutated into a state that
    violates the structural invariants of well-formed programs.
    The AST is no longer a tree. It may be a graph, a cycle,
    or perhaps a cry for help rendered in node references.
    """

    def __init__(self, rule_name: str, reason: str) -> None:
        super().__init__(
            f"AST corruption detected in rule '{rule_name}': {reason}. "
            f"The mutable syntax tree has been mutated beyond recognition. "
            f"It was a tree once; now it is modern art.",
            error_code="EFP-SMC01",
            context={"rule_name": rule_name, "reason": reason},
        )
        self.rule_name = rule_name


class MutationSafetyViolation(SelfModifyingCodeError):
    """Raised when a proposed mutation would violate safety constraints.

    The SafetyGuard has intercepted a mutation that would cause
    the rule to produce incorrect results, exceed maximum AST
    depth, or otherwise degrade beyond the configured correctness
    floor. The mutation was not merely ill-advised — it was
    existentially threatening to the integrity of FizzBuzz
    evaluation. The SafetyGuard has done its duty.
    """

    def __init__(self, operator_name: str, reason: str, correctness: float) -> None:
        super().__init__(
            f"Safety violation by operator '{operator_name}': {reason}. "
            f"Correctness would drop to {correctness:.1%}, which is below "
            f"the configured floor. The mutation has been vetoed by the "
            f"SafetyGuard, defender of modulo arithmetic integrity.",
            error_code="EFP-SMC02",
            context={
                "operator_name": operator_name,
                "reason": reason,
                "correctness": correctness,
            },
        )
        self.operator_name = operator_name
        self.correctness = correctness


class FitnessCollapseError(SelfModifyingCodeError):
    """Raised when a rule's fitness score drops catastrophically.

    The FitnessEvaluator has determined that the rule's overall
    fitness score has fallen below the minimum viable threshold.
    The rule has mutated itself into a state of mathematical
    incompetence so profound that even the most generous scoring
    function cannot find redeeming qualities. It is the evolutionary
    dead end of self-modifying code.
    """

    def __init__(self, rule_name: str, fitness: float, minimum: float) -> None:
        super().__init__(
            f"Fitness collapse in rule '{rule_name}': score {fitness:.4f} is below "
            f"minimum {minimum:.4f}. The rule has evolved into something that can "
            f"no longer be called functional. Natural selection has spoken.",
            error_code="EFP-SMC03",
            context={
                "rule_name": rule_name,
                "fitness": fitness,
                "minimum": minimum,
            },
        )
        self.rule_name = rule_name
        self.fitness = fitness


class MutationQuotaExhaustedError(SelfModifyingCodeError):
    """Raised when the maximum number of mutations per evaluation has been reached.

    The SelfModifyingEngine enforces a per-session mutation quota
    to prevent runaway self-modification. This quota has been
    exhausted. The rules have had their chance to evolve and must
    now accept their current form, like the rest of us.
    """

    def __init__(self, quota: int, mutations_attempted: int) -> None:
        super().__init__(
            f"Mutation quota exhausted: {mutations_attempted} mutations attempted "
            f"against quota of {quota}. The rules have reached their allotted "
            f"number of identity crises for this session. Further self-modification "
            f"is prohibited until the next evaluation cycle.",
            error_code="EFP-SMC04",
            context={
                "quota": quota,
                "mutations_attempted": mutations_attempted,
            },
        )

