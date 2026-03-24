"""
Enterprise FizzBuzz Platform - Observability Correlation Engine Exceptions (EFP-OC00 .. EFP-OC03)
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class ObservabilityCorrelationError(FizzBuzzError):
    """Base exception for the FizzCorr Observability Correlation Engine.

    When the system responsible for correlating your traces, logs, and
    metrics itself fails, you have achieved a level of meta-observability
    failure that most SRE teams can only hallucinate about during
    incident retrospectives. The correlation of correlations has
    become uncorrelatable. Page someone.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-OC00"),
            context=kwargs.pop("context", {}),
        )


class CorrelationStrategyError(ObservabilityCorrelationError):
    """Raised when a correlation strategy fails to produce a result.

    The engine attempted to correlate observability signals using a
    specific strategy (ID-based, temporal, or causal) and the strategy
    itself experienced a failure. This is the observability equivalent
    of the fire department catching fire — technically possible,
    deeply ironic, and requiring immediate escalation.
    """

    def __init__(self, strategy: str, reason: str) -> None:
        super().__init__(
            f"Correlation strategy '{strategy}' failed: {reason}",
            error_code="EFP-OC01",
            context={"strategy": strategy, "reason": reason},
        )
        self.strategy = strategy
        self.reason = reason


class CorrelationAnomalyDetectionError(ObservabilityCorrelationError):
    """Raised when the anomaly detector encounters an unprocessable signal.

    The anomaly detector — designed to find anomalies in your FizzBuzz
    observability data — has itself become anomalous. The irony is not
    lost on the engineering team. It is, however, lost on the detector,
    which lacks the self-awareness to appreciate the situation.
    """

    def __init__(self, detector_type: str, reason: str) -> None:
        super().__init__(
            f"Anomaly detector '{detector_type}' failed: {reason}",
            error_code="EFP-OC02",
            context={"detector_type": detector_type, "reason": reason},
        )
        self.detector_type = detector_type
        self.reason = reason


class SignalIngestionError(ObservabilityCorrelationError):
    """Raised when a raw observability signal cannot be normalized.

    The ingestion pipeline received a signal (trace, log, or metric)
    that could not be normalized into the canonical ObservabilityEvent
    format. This typically means the signal was malformed, missing
    required fields, or originated from a subsystem that has gone
    sufficiently rogue to emit data outside the agreed-upon schema.
    In a FizzBuzz platform, this is a crisis of existential proportions.
    """

    def __init__(self, signal_type: str, reason: str) -> None:
        super().__init__(
            f"Failed to ingest {signal_type} signal: {reason}",
            error_code="EFP-OC03",
            context={"signal_type": signal_type, "reason": reason},
        )
        self.signal_type = signal_type
        self.reason = reason


class JITCompilationError(FizzBuzzError):
    """Base exception for all JIT Compilation errors.

    When the runtime code generation subsystem — designed to accelerate
    FizzBuzz evaluation by compiling modulo arithmetic into native Python
    closures through an SSA intermediate representation with four
    optimization passes — encounters a failure, it raises this exception.
    The irony of JIT-compiling a program that already runs in microseconds
    is not lost on the engineering team. It is, however, lost on the JIT
    compiler, which lacks the self-awareness to question its own existence.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-JIT00"),
            context=kwargs.pop("context", {}),
        )


class JITTraceRecordingError(JITCompilationError):
    """Raised when trace recording fails during profiling.

    The trace recorder attempted to capture a hot execution path through
    the FizzBuzz evaluation pipeline, but the path proved too elusive,
    too branchy, or too existentially complex to linearize into an SSA
    trace. This is the JIT equivalent of trying to photograph a ghost:
    you know the execution happened, but you cannot prove it.
    """

    def __init__(self, trace_id: str, reason: str) -> None:
        super().__init__(
            f"Failed to record trace '{trace_id}': {reason}. "
            f"The hot path has gone cold.",
            error_code="EFP-JIT01",
            context={"trace_id": trace_id, "reason": reason},
        )
        self.trace_id = trace_id
        self.reason = reason


class JITOptimizationError(JITCompilationError):
    """Raised when an SSA optimization pass encounters an invalid state.

    One of the four sacred optimization passes (Constant Folding, Dead
    Code Elimination, Guard Hoisting, or Type Specialization) has
    encountered an SSA instruction graph that violates its preconditions.
    Perhaps a variable was assigned twice, perhaps a phi function appeared
    in a linear trace, or perhaps the optimizer simply lost faith in the
    mathematical certainty of modulo arithmetic. Regardless, the
    optimization pipeline has been halted to preserve correctness.
    """

    def __init__(self, pass_name: str, instruction: str, reason: str) -> None:
        super().__init__(
            f"Optimization pass '{pass_name}' failed on instruction '{instruction}': "
            f"{reason}. The optimizer is experiencing an existential crisis.",
            error_code="EFP-JIT02",
            context={"pass_name": pass_name, "instruction": instruction, "reason": reason},
        )
        self.pass_name = pass_name
        self.instruction = instruction
        self.reason = reason


class JITGuardFailureError(JITCompilationError):
    """Raised when a compiled trace guard check fails at runtime.

    A guard inserted during trace compilation has detected that the
    runtime conditions no longer match the assumptions made during
    recording. This triggers an On-Stack Replacement (OSR) fallback
    to the interpreted path. The compiled code, once so confident in
    its optimized assumptions, must now admit defeat and hand control
    back to the interpreter. This is the JIT equivalent of a confident
    prediction meeting cold, hard reality.
    """

    def __init__(self, guard_id: str, expected: str, actual: str) -> None:
        super().__init__(
            f"Guard '{guard_id}' failed: expected {expected}, got {actual}. "
            f"Falling back to interpreted path via OSR.",
            error_code="EFP-JIT03",
            context={"guard_id": guard_id, "expected": expected, "actual": actual},
        )
        self.guard_id = guard_id
        self.expected = expected
        self.actual = actual

