"""
Enterprise FizzBuzz Platform - CPU Pipeline Exceptions (EFP-CPU0 through EFP-CPU4)
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class CPUPipelineError(FizzBuzzError):
    """Base exception for all FizzCPU pipeline simulator errors.

    The 5-stage RISC pipeline simulator faithfully models instruction
    fetch, decode, execute, memory access, and write-back stages.
    When any stage encounters an unrecoverable condition, this
    exception hierarchy provides precise diagnostic information
    about the microarchitectural failure mode.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-CPU0"),
            context=kwargs.pop("context", {}),
        )


class PipelineHazardError(CPUPipelineError):
    """Raised when a pipeline hazard cannot be resolved.

    Data hazards (RAW, WAR, WAW) are normally resolved by the
    forwarding unit or by inserting pipeline bubbles. This exception
    indicates a hazard configuration that exceeds the pipeline's
    resolution capabilities — a condition that should be impossible
    in a correctly designed 5-stage pipeline, but enterprise software
    must account for the impossible.
    """

    def __init__(self, hazard_type: str, stage: str, register: int) -> None:
        super().__init__(
            f"Unresolvable {hazard_type} hazard at {stage} stage "
            f"on register R{register}",
            error_code="EFP-CPU1",
            context={
                "hazard_type": hazard_type,
                "stage": stage,
                "register": register,
            },
        )
        self.hazard_type = hazard_type
        self.stage = stage
        self.register = register


class PipelineStallError(CPUPipelineError):
    """Raised when the pipeline enters an infinite stall condition.

    A stall that persists beyond the maximum cycle count indicates
    either a deadlock in the hazard detection logic or a program
    that has entered an infinite loop. In either case, the pipeline
    must be forcibly drained to prevent resource exhaustion.
    """

    def __init__(self, cycle: int, stage: str) -> None:
        super().__init__(
            f"Pipeline stalled indefinitely at cycle {cycle} in {stage} stage. "
            f"Maximum cycle limit exceeded.",
            error_code="EFP-CPU2",
            context={"cycle": cycle, "stage": stage},
        )
        self.cycle = cycle
        self.stage = stage


class BranchMispredictionError(CPUPipelineError):
    """Raised when branch misprediction rate exceeds acceptable thresholds.

    While individual mispredictions are normal and handled by pipeline
    flushes, a sustained misprediction rate above the configured
    threshold indicates a pathological branch pattern that defeats
    the predictor. This may warrant switching to a more sophisticated
    prediction algorithm.
    """

    def __init__(self, predictor: str, accuracy: float, threshold: float) -> None:
        super().__init__(
            f"Branch predictor '{predictor}' accuracy {accuracy:.1%} "
            f"below threshold {threshold:.1%}. Pipeline throughput "
            f"severely degraded by control hazards.",
            error_code="EFP-CPU3",
            context={
                "predictor": predictor,
                "accuracy": accuracy,
                "threshold": threshold,
            },
        )
        self.predictor = predictor
        self.accuracy = accuracy
        self.threshold = threshold


class PipelineFlushError(CPUPipelineError):
    """Raised when a pipeline flush fails to restore consistent state.

    A pipeline flush discards all in-flight instructions and redirects
    the program counter to the correct target. If the flush leaves the
    pipeline in an inconsistent state, this exception signals a critical
    microarchitectural failure that requires immediate attention.
    """

    def __init__(self, cycle: int, reason: str) -> None:
        super().__init__(
            f"Pipeline flush at cycle {cycle} failed: {reason}. "
            f"Pipeline state may be inconsistent.",
            error_code="EFP-CPU4",
            context={"cycle": cycle, "reason": reason},
        )
        self.cycle = cycle
        self.reason = reason

