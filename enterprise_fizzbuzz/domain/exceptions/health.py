"""
Enterprise FizzBuzz Platform - Health Check Probe Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class HealthCheckError(FizzBuzzError):
    """Base exception for all Kubernetes-style health check errors.

    When the system designed to tell you whether FizzBuzz is healthy
    encounters its own failure, a recursive diagnostic fault has occurred
    that neither Kubernetes nor the modulo operator can resolve.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-HC00"),
            context=kwargs.pop("context", {}),
        )


class LivenessProbeFailedError(HealthCheckError):
    """Raised when the liveness probe determines the platform is dead.

    The canary evaluation of evaluate(15) did not return "FizzBuzz".
    This means the platform has lost the ability to perform basic
    modulo arithmetic, which is the computational equivalent of
    forgetting how to breathe. In Kubernetes, this would trigger
    a pod restart. In our case, it just means someone broke math.
    """

    def __init__(self, expected: str, actual: str) -> None:
        super().__init__(
            f"Liveness probe FAILED: evaluate(15) returned '{actual}', "
            f"expected '{expected}'. The platform has forgotten how to "
            f"FizzBuzz. This is not a drill.",
            error_code="EFP-HC01",
            context={"expected": expected, "actual": actual},
        )
        self.expected = expected
        self.actual = actual


class ReadinessProbeFailedError(HealthCheckError):
    """Raised when the readiness probe determines the platform is not ready.

    One or more subsystems have reported a status that precludes the
    platform from accepting traffic. Perhaps the cache is incoherent,
    the circuit breaker is tripped, or the ML engine is having an
    existential crisis. Whatever the cause, the platform is not ready
    to serve FizzBuzz requests, and honesty compels us to admit it.
    """

    def __init__(self, failing_subsystems: list[str]) -> None:
        subsystems_str = ", ".join(failing_subsystems)
        super().__init__(
            f"Readiness probe FAILED: subsystems not ready: [{subsystems_str}]. "
            f"The platform cannot accept FizzBuzz traffic until all subsystems "
            f"report UP or DEGRADED status.",
            error_code="EFP-HC02",
            context={"failing_subsystems": failing_subsystems},
        )
        self.failing_subsystems = failing_subsystems


class StartupProbeFailedError(HealthCheckError):
    """Raised when the startup probe determines boot sequence is incomplete.

    The platform has not completed all startup milestones within the
    expected timeframe. Perhaps the config wasn't loaded, the rule
    engine wasn't initialized, or the blockchain wasn't mined. Whatever
    milestone was missed, the platform is stuck in boot limbo — too
    alive to be declared dead, too unready to accept traffic.
    """

    def __init__(self, pending_milestones: list[str]) -> None:
        milestones_str = ", ".join(pending_milestones)
        super().__init__(
            f"Startup probe FAILED: pending milestones: [{milestones_str}]. "
            f"The platform boot sequence has not completed. "
            f"Some subsystems are still contemplating their existence.",
            error_code="EFP-HC03",
            context={"pending_milestones": pending_milestones},
        )
        self.pending_milestones = pending_milestones


class SelfHealingFailedError(HealthCheckError):
    """Raised when the self-healing manager fails to recover a subsystem.

    The self-healing manager attempted to restore a failing subsystem
    to health, but the recovery procedure itself failed. This is the
    medical equivalent of the ambulance breaking down en route to the
    hospital. The subsystem remains unhealthy, and now the healing
    infrastructure is also in question.
    """

    def __init__(self, subsystem_name: str, reason: str) -> None:
        super().__init__(
            f"Self-healing failed for subsystem '{subsystem_name}': {reason}. "
            f"The platform attempted to heal itself but the cure was worse "
            f"than the disease. Manual intervention is required.",
            error_code="EFP-HC04",
            context={"subsystem_name": subsystem_name, "reason": reason},
        )
        self.subsystem_name = subsystem_name


class HealthDashboardRenderError(HealthCheckError):
    """Raised when the health dashboard fails to render.

    The ASCII dashboard that displays the health status of all
    subsystems has itself become unhealthy. The irony of a health
    visualization tool that can't visualize its own health is not
    lost on us. It's dashboards all the way down.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Health dashboard render failed: {reason}. "
            f"The dashboard that monitors health cannot itself be displayed. "
            f"Please check the health of the health dashboard.",
            error_code="EFP-HC05",
            context={"reason": reason},
        )


class DownstreamFizzBuzzDegradationError(FizzBuzzError):
    """Raised when downstream FizzBuzz evaluation quality degrades.

    Monitors ML confidence scores and evaluation latency to detect
    when the FizzBuzz pipeline is producing results with insufficient
    conviction. Because a FizzBuzz result delivered without confidence
    is no FizzBuzz result at all.
    """

    def __init__(self, metric_name: str, current_value: float, threshold: float) -> None:
        super().__init__(
            f"Downstream FizzBuzz degradation detected: {metric_name} "
            f"at {current_value:.4f} (threshold: {threshold:.4f}). "
            f"The FizzBuzz pipeline may be experiencing existential doubt.",
            error_code="EFP-CB02",
            context={
                "metric_name": metric_name,
                "current_value": current_value,
                "threshold": threshold,
            },
        )

