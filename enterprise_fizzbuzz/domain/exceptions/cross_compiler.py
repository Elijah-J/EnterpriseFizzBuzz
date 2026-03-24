"""
Enterprise FizzBuzz Platform - Cross-Compiler Exception Hierarchy
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class CrossCompilerError(FizzBuzzError):
    """Base exception for all FizzBuzz Cross-Compiler errors.

    Raised when the cross-compilation pipeline encounters a failure
    so fundamental that it questions whether transpiling divisibility
    checks into systems languages was ever a good idea. Spoiler: it wasn't,
    but enterprise architecture committees rarely consult common sense.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-CC00"),
            context=kwargs.pop("context", {}),
        )


class IRGenerationError(CrossCompilerError):
    """Raised when the Intermediate Representation builder fails.

    The IR builder attempted to lower FizzBuzz rules into basic blocks
    and instructions, but something went wrong — probably because the
    rules were too simple. Modern compiler infrastructure was not
    designed for programs this trivial, and the IR builder is offended.
    """

    def __init__(self, rule_name: str, reason: str) -> None:
        super().__init__(
            f"IR generation failed for rule '{rule_name}': {reason}. "
            f"Consider adding more rules to justify the compiler infrastructure.",
            error_code="EFP-CC01",
            context={"rule_name": rule_name},
        )


class CodeGenerationError(CrossCompilerError):
    """Raised when a target code generator fails to emit valid source code.

    The code generator tried its best to produce syntactically valid
    output in the target language, but even the most sophisticated
    string concatenation engine has its limits. The generated code
    may contain syntax errors, undefined behavior, or — worst of all —
    correct FizzBuzz logic.
    """

    def __init__(self, target_language: str, reason: str) -> None:
        super().__init__(
            f"Code generation for '{target_language}' failed: {reason}. "
            f"The target language may not be ready for enterprise FizzBuzz.",
            error_code="EFP-CC02",
            context={"target_language": target_language},
        )


class RoundTripVerificationError(CrossCompilerError):
    """Raised when generated code produces results that disagree with Python.

    The round-trip verifier compared the generated code's output against
    the canonical Python reference implementation, and they disagree.
    This is the compiler equivalent of two calculators giving different
    answers for 15 % 3, which should be impossible but here we are.
    """

    def __init__(self, target_language: str, number: int, expected: str, got: str) -> None:
        super().__init__(
            f"Round-trip verification failed for '{target_language}' at n={number}: "
            f"expected '{expected}', got '{got}'. The laws of arithmetic may vary "
            f"by programming language.",
            error_code="EFP-CC03",
            context={
                "target_language": target_language,
                "number": number,
                "expected": expected,
                "got": got,
            },
        )


class UnsupportedTargetError(CrossCompilerError):
    """Raised when an unsupported compilation target is requested.

    The cross-compiler supports C, Rust, and WebAssembly Text. Requesting
    compilation to COBOL, Brainfuck, or interpretive dance is not yet
    supported, though all three are on the roadmap for Q4.
    """

    def __init__(self, target: str) -> None:
        supported = ["c", "rust", "wat"]
        super().__init__(
            f"Unsupported compilation target '{target}'. "
            f"Supported targets: {supported}. "
            f"COBOL backend is planned for Q4 2027.",
            error_code="EFP-CC04",
            context={"target": target, "supported": supported},
        )

