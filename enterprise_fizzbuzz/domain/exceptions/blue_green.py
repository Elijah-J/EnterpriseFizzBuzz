"""
Enterprise FizzBuzz Platform - Blue/Green Deployment Simulation Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError
from .data_pipeline import DataPipelineError


class DeploymentError(FizzBuzzError):
    """Base exception for all Blue/Green Deployment Simulation errors.

    When your zero-downtime deployment system for a CLI tool that runs
    for less than a second encounters a failure, you must ask yourself:
    what downtime are we even trying to avoid? The answer, as always
    in enterprise software, is irrelevant. The ceremony must proceed.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-BG00"),
            context=kwargs.pop("context", {}),
        )


class SlotProvisioningError(DeploymentError):
    """Raised when a deployment slot fails to provision.

    A deployment slot is essentially a variable that holds a reference
    to a StandardRuleEngine. If assigning a variable has failed, the
    laws of computer science have been violated at a fundamental level.
    Consider restarting the universe.
    """

    def __init__(self, color: str, reason: str) -> None:
        super().__init__(
            f"Failed to provision {color} deployment slot: {reason}. "
            f"Assigning a variable has somehow failed. This is unprecedented.",
            error_code="EFP-BG01",
            context={"color": color, "reason": reason},
        )


class ShadowTrafficError(DeploymentError):
    """Raised when shadow traffic comparison detects a discrepancy.

    Both slots received the same input and produced different outputs.
    Since both slots contain identical FizzBuzz rule engines, this
    should be mathematically impossible. If 15 % 3 equals 0 on the
    blue slot but not on the green slot, either mathematics is broken
    or someone has been tampering with the deployment slots.
    """

    def __init__(self, number: int, blue_result: str, green_result: str) -> None:
        super().__init__(
            f"Shadow traffic mismatch for number {number}: "
            f"blue='{blue_result}', green='{green_result}'. "
            f"Mathematics appears to be non-deterministic. Page the on-call physicist.",
            error_code="EFP-BG02",
            context={"number": number, "blue_result": blue_result, "green_result": green_result},
        )


class SmokeTestFailureError(DeploymentError):
    """Raised when a deployment smoke test fails.

    The canary numbers [3, 5, 15, 42, 97] were evaluated against the
    green slot and at least one produced an unexpected result. The
    green slot is not ready for production traffic, which consists
    of exactly one user running a CLI tool.
    """

    def __init__(self, number: int, expected: str, actual: str) -> None:
        super().__init__(
            f"Smoke test failed for canary number {number}: "
            f"expected '{expected}', got '{actual}'. "
            f"The green slot is not yet worthy of production traffic.",
            error_code="EFP-BG03",
            context={"number": number, "expected": expected, "actual": actual},
        )


class BakePeriodError(DeploymentError):
    """Raised when the bake period monitoring detects instability.

    The green slot was placed under observation for a brief period
    of time (measured in milliseconds) and was found wanting. In
    real deployments, bake periods catch latent issues. Here, the
    bake period catches the existential dread of a FizzBuzz engine
    that has been given too much responsibility too soon.
    """

    def __init__(self, duration_ms: float, reason: str) -> None:
        super().__init__(
            f"Bake period failed after {duration_ms:.2f}ms: {reason}. "
            f"The green slot was not stable long enough to earn trust.",
            error_code="EFP-BG04",
            context={"duration_ms": duration_ms, "reason": reason},
        )


class CutoverError(DeploymentError):
    """Raised when the cutover from blue to green fails.

    The atomic swap — which is literally just `self.active = green` —
    has somehow failed. This is the deployment equivalent of failing
    to flip a light switch. If a single variable assignment can fail,
    all hope is lost.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Cutover failed: {reason}. The atomic variable assignment "
            f"has encountered a non-atomic problem. This should not be possible.",
            error_code="EFP-BG05",
            context={"reason": reason},
        )


class DeploymentRollbackError(DeploymentError):
    """Raised when a rollback to the blue slot fails.

    Rolling back means setting `self.active = blue`. If this fails,
    the deployment system has lost the ability to assign variables,
    which is a problem that transcends deployment strategy and enters
    the realm of fundamental computational theory.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Rollback failed: {reason}. The variable assignment that was "
            f"supposed to restore the blue slot has failed. "
            f"Zero users impacted. (There was one user.)",
            error_code="EFP-BG06",
            context={"reason": reason},
        )


class DeploymentPhaseError(DeploymentError):
    """Raised when a deployment phase transition is invalid.

    The deployment orchestrator maintains a strict phase lifecycle:
    Provision -> Shadow -> SmokeTest -> BakePeriod -> Cutover -> Monitor.
    Attempting to skip a phase or go backwards violates the
    deployment protocol, and the orchestrator will reject the
    transition as unsafe.
    """

    def __init__(self, current_phase: str, attempted_phase: str) -> None:
        super().__init__(
            f"Invalid deployment phase transition: '{current_phase}' -> "
            f"'{attempted_phase}'. The deployment ceremony must proceed "
            f"in the prescribed order. No shortcuts.",
            error_code="EFP-BG07",
            context={"current_phase": current_phase, "attempted_phase": attempted_phase},
        )


class PipelineDashboardRenderError(DataPipelineError):
    """Raised when the pipeline ASCII dashboard fails to render.

    The dashboard — a lovingly crafted ASCII art visualization of
    your five-stage linear pipeline — has failed to render. The
    data is flowing correctly through the pipeline, but the
    observation of that flow has broken. Heisenberg would have
    something to say about this, but his quote would also fail
    to render.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Pipeline dashboard render failed: {reason}. "
            f"The ASCII art remains undrawn. The DAG unvisualized. "
            f"The pipeline, however, continues to function — unobserved.",
            error_code="EFP-DP12",
            context={"reason": reason},
        )

