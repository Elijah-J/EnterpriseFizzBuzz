"""
Enterprise FizzBuzz Platform - Custom Bytecode VM Exceptions (EFP-VM00 through EFP-VM04)
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class BytecodeVMError(FizzBuzzError):
    """Base exception for all Custom Bytecode VM errors.

    When the FizzBuzz Bytecode Virtual Machine encounters a condition
    that prevents it from continuing execution of compiled bytecode
    through the virtual machine's instruction pipeline,
    this exception (or one of its children) will be raised.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-VM00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class BytecodeCompilationError(BytecodeVMError):
    """Raised when the FBVM compiler fails to translate rules to bytecode.

    The compiler examined your rule definitions and decided that they
    cannot be expressed in the FBVM instruction set. This is
    remarkable, given that the instruction set was specifically designed
    for FizzBuzz and nothing else. Somehow, you have managed to confuse
    a compiler that only needs to emit MOD and CMP_ZERO instructions.
    """

    def __init__(self, rule_name: str, reason: str) -> None:
        super().__init__(
            f"Compilation failed for rule '{rule_name}': {reason}. "
            f"The FBVM compiler cannot translate this rule into bytecode. "
            f"Consider simplifying your divisibility check (it's literally one modulo).",
            error_code="EFP-VM01",
            context={"rule_name": rule_name, "reason": reason},
        )


class BytecodeExecutionError(BytecodeVMError):
    """Raised when the FBVM encounters a runtime error during execution.

    The virtual machine was happily executing bytecode when something
    went catastrophically wrong. Given that the bytecode only performs
    modulo arithmetic and string concatenation, this is an achievement
    in runtime failure that most VMs can only aspire to.
    """

    def __init__(self, pc: int, opcode: str, reason: str) -> None:
        super().__init__(
            f"VM execution error at PC={pc}, opcode={opcode}: {reason}. "
            f"The FBVM has encountered an unrecoverable state. "
            f"Please file a bug report with your .fzbc file attached.",
            error_code="EFP-VM02",
            context={"program_counter": pc, "opcode": opcode, "reason": reason},
        )


class BytecodeCycleLimitError(BytecodeVMError):
    """Raised when the FBVM exceeds its cycle limit.

    The virtual machine has executed more instructions than the
    configured cycle limit allows. For a program that computes
    n % d == 0 for two divisors, exceeding 10,000 cycles suggests
    either an infinite loop or a profoundly inefficient compilation
    strategy. Both are concerning.
    """

    def __init__(self, cycle_limit: int, pc: int) -> None:
        super().__init__(
            f"VM cycle limit exceeded: {cycle_limit} cycles at PC={pc}. "
            f"The bytecode program appears to be stuck in an infinite loop, "
            f"which is impressive for a program that only computes modulo.",
            error_code="EFP-VM03",
            context={"cycle_limit": cycle_limit, "program_counter": pc},
        )


class BytecodeSerializationError(BytecodeVMError):
    """Raised when .fzbc bytecode serialization or deserialization fails.

    The proprietary .fzbc file format — complete with magic header
    'FZBC' and base64 encoding — has encountered a corruption or
    format mismatch. Perhaps someone edited the bytecode by hand,
    which is the VM equivalent of performing surgery with a spoon.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Bytecode serialization error: {reason}. "
            f"The .fzbc file may be corrupted, truncated, or from an "
            f"incompatible version of the FBVM. Try recompiling from source rules.",
            error_code="EFP-VM04",
            context={"reason": reason},
        )

