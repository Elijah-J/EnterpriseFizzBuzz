"""
Enterprise FizzBuzz Platform - FizzIR SSA Intermediate Representation Exceptions (EFP-IR00 through EFP-IR03)
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class SSAIRError(FizzBuzzError):
    """Base exception for all FizzIR intermediate representation errors.

    The FizzIR subsystem compiles FizzBuzz evaluation rules to an
    LLVM-inspired SSA form, applies optimization passes, and interprets
    the result. Errors in any phase -- compilation, SSA construction,
    optimization, or interpretation -- are rooted in this hierarchy.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-IR00"),
            context=kwargs.pop("context", {}),
        )


class IRCompilationError(SSAIRError):
    """Raised when FizzBuzz rules cannot be compiled to IR.

    Compilation failure indicates that the rule set contains
    configurations that the IR compiler cannot represent in the
    FizzIR type system -- for example, a divisor of zero, which
    would generate a division-by-zero in the srem instruction.
    """

    def __init__(self, rule_name: str, reason: str) -> None:
        self.rule_name = rule_name
        self.reason = reason
        super().__init__(
            f"IR compilation failed for rule '{rule_name}': {reason}",
            error_code="EFP-IR01",
            context={"rule_name": rule_name, "reason": reason},
        )


class SSAConstructionError(SSAIRError):
    """Raised when SSA form construction encounters an invalid CFG.

    SSA construction requires a well-formed control flow graph with
    a unique entry block and no unreachable cycles. If the dominator
    tree computation fails or phi node placement encounters an
    inconsistency, this error provides the block label and the
    nature of the structural violation.
    """

    def __init__(self, block_label: str, detail: str) -> None:
        self.block_label = block_label
        self.detail = detail
        super().__init__(
            f"SSA construction failed at block '{block_label}': {detail}",
            error_code="EFP-IR02",
            context={"block_label": block_label, "detail": detail},
        )


class IROptimizationError(SSAIRError):
    """Raised when an optimization pass produces invalid IR.

    Each optimization pass must preserve the semantic equivalence
    of the program. If a pass produces IR that the verifier rejects
    -- for example, a use of an undefined value, or a basic block
    without a terminator -- this error identifies the responsible
    pass and the nature of the violation.
    """

    def __init__(self, pass_name: str, detail: str) -> None:
        self.pass_name = pass_name
        self.detail = detail
        super().__init__(
            f"Optimization pass '{pass_name}' produced invalid IR: {detail}",
            error_code="EFP-IR03",
            context={"pass_name": pass_name, "detail": detail},
        )

