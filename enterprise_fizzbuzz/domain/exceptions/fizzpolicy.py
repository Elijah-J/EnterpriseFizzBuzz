"""
Enterprise FizzBuzz Platform - FizzPolicy Declarative Policy Engine Exceptions (EFP-POL00 through EFP-POL28)
"""

from __future__ import annotations

from typing import Any

from ._base import FizzBuzzError


class PolicyEngineError(FizzBuzzError):
    """Base exception for FizzPolicy declarative policy engine errors."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL00"
        self.context = {"reason": reason}


class PolicyLexerError(PolicyEngineError):
    """Raised when the FizzRego lexer encounters invalid source text.

    Unterminated strings, invalid escape sequences, malformed number
    literals, and unrecognized characters trigger this exception.
    The error includes the source file, line, and column.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL01"
        self.context = {"reason": reason}


class PolicyParserError(PolicyEngineError):
    """Raised when the FizzRego parser encounters a syntax error.

    Unexpected tokens, missing delimiters, malformed rule definitions,
    and unsafe variable references trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL02"
        self.context = {"reason": reason}


class PolicyTypeCheckError(PolicyEngineError):
    """Raised when the type checker detects a type incompatibility.

    Comparing incompatible types, arithmetic on non-numeric values,
    and function argument type mismatches trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL03"
        self.context = {"reason": reason}


class PolicyPartialEvalError(PolicyEngineError):
    """Raised when the partial evaluator encounters an error during optimization.

    Static data resolution failures, constant folding errors, and
    rule inlining cycles trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL04"
        self.context = {"reason": reason}


class PolicyPlanGeneratorError(PolicyEngineError):
    """Raised when the plan generator fails to compile a rule into instructions.

    Unsupported AST node types, circular rule references, and join
    ordering failures trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL05"
        self.context = {"reason": reason}


class PolicyEvaluationError(PolicyEngineError):
    """Raised when policy evaluation encounters a runtime error.

    Division by zero, undefined variable access, type mismatches during
    evaluation, and conflicting complete rule values trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL06"
        self.context = {"reason": reason}


class PolicyEvaluationTimeoutError(PolicyEngineError):
    """Raised when a policy evaluation exceeds its wall-clock timeout.

    The default timeout is 100ms.  Complex policies with unbounded
    iteration or deeply nested evaluations may exceed this limit.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL07"
        self.context = {"reason": reason}


class PolicyEvaluationLimitError(PolicyEngineError):
    """Raised when a policy evaluation exceeds its iteration or output size limit.

    The default limits are 100,000 plan instructions and 1MB output.
    Policies that generate excessively large result sets or create
    unbounded iteration trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL08"
        self.context = {"reason": reason}


class PolicyBundleError(PolicyEngineError):
    """Raised when a policy bundle operation fails.

    General bundle lifecycle errors not covered by more specific
    bundle exception subclasses trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL09"
        self.context = {"reason": reason}


class PolicyBundleBuildError(PolicyEngineError):
    """Raised when a bundle build fails during compilation or testing.

    Compilation errors in any .rego file, import resolution failures,
    and test failures during the build process trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL10"
        self.context = {"reason": reason}


class PolicyBundleIntegrityError(PolicyEngineError):
    """Raised when a bundle fails signature verification.

    File hash mismatches, invalid HMAC signatures, missing signature
    blocks, and tampered manifest entries trigger this exception.
    This indicates unauthorized policy modification.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL11"
        self.context = {"reason": reason}


class PolicyBundleVersionError(PolicyEngineError):
    """Raised when a bundle version operation fails.

    Activating a non-existent revision, rolling back beyond history
    limits, and revision counter corruption trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL12"
        self.context = {"reason": reason}


class PolicyBundleStoreError(PolicyEngineError):
    """Raised when the bundle store encounters a persistence error.

    Save failures, load failures, content-addressable deduplication
    errors, and storage corruption trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL13"
        self.context = {"reason": reason}


class PolicyBundleSigningError(PolicyEngineError):
    """Raised when bundle signing fails.

    Missing signing key, HMAC computation errors, and key ID
    mismatches trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL14"
        self.context = {"reason": reason}


class PolicyDecisionLogError(PolicyEngineError):
    """Raised when the decision logger encounters a recording error.

    Log entry serialization failures, storage capacity exhaustion,
    and input masking errors trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL15"
        self.context = {"reason": reason}


class PolicyDecisionQueryError(PolicyEngineError):
    """Raised when a decision log query fails.

    Invalid filter parameters, time range parsing errors, and
    pagination boundary errors trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL16"
        self.context = {"reason": reason}


class PolicyDecisionExportError(PolicyEngineError):
    """Raised when decision log export fails.

    Unsupported export format, serialization errors, and filesystem
    write failures trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL17"
        self.context = {"reason": reason}


class PolicyDataAdapterError(PolicyEngineError):
    """Raised when a data adapter fails to fetch external data.

    Subsystem unavailability, data format changes, and adapter
    initialization failures trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL18"
        self.context = {"reason": reason}


class PolicyDataRefreshError(PolicyEngineError):
    """Raised when the data refresh scheduler encounters an error.

    Adapter timeout, concurrent refresh conflicts, and atomic
    data swap failures trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL19"
        self.context = {"reason": reason}


class PolicyTestError(PolicyEngineError):
    """Raised when the policy test runner encounters an infrastructure error.

    Test discovery failures, test environment setup errors, and
    coverage instrumentation failures trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL20"
        self.context = {"reason": reason}


class PolicyTestFailedError(PolicyEngineError):
    """Raised when one or more policy tests fail.

    Contains the test run result with per-test failure details
    including expected vs actual values and explanation traces.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL21"
        self.context = {"reason": reason}


class PolicyCoverageError(PolicyEngineError):
    """Raised when policy test coverage falls below the configured threshold.

    The default minimum coverage is 80%.  Bundles with insufficient
    coverage are rejected during the build process.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL22"
        self.context = {"reason": reason}


class PolicyBenchmarkError(PolicyEngineError):
    """Raised when policy benchmarking encounters an error.

    Benchmark setup failures, evaluation errors during benchmarking,
    and statistical computation errors trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL23"
        self.context = {"reason": reason}


class PolicyWatcherError(PolicyEngineError):
    """Raised when the policy watcher fails to detect or process activations.

    Store polling failures, bundle load errors after activation,
    and test failures on new bundles trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL24"
        self.context = {"reason": reason}


class PolicyHotReloadError(PolicyEngineError):
    """Raised when policy hot-reload via Raft consensus fails.

    Raft log deserialization errors, follower-leader version mismatch,
    and plan swap failures during hot-reload trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL25"
        self.context = {"reason": reason}


class PolicyBuiltinError(PolicyEngineError):
    """Raised when a built-in function encounters a runtime error.

    Argument type mismatches, invalid inputs (e.g., invalid regex
    pattern, malformed JWT token), and domain errors (division by
    zero in format_int) trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL26"
        self.context = {"reason": reason}


class PolicyAdmissionDeniedError(PolicyEngineError):
    """Raised when the admission controller denies a resource mutation.

    The admission controller evaluates ``data.fizzbuzz.admission.allowed``
    and raises this exception when the result is false or undefined.
    Contains the denial reason and the explanation trace.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL27"
        self.context = {"reason": reason}


class PolicyMiddlewareError(PolicyEngineError):
    """Raised when the FizzPolicy middleware encounters a processing error.

    Input document construction failures, engine invocation errors,
    and denial response building errors trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL28"
        self.context = {"reason": reason}
