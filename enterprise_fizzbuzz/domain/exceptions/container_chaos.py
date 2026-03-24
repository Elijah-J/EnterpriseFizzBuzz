"""
Enterprise FizzBuzz Platform - -- FizzContainerChaos: Container-Native Chaos Engineering ----
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class ContainerChaosError(FizzBuzzError):
    """Base exception for FizzContainerChaos chaos engineering errors.

    All exceptions originating from the container-native chaos
    engineering subsystem inherit from this class.  The subsystem
    provides fault injection at the namespace, cgroup, overlay,
    CNI, and container runtime layers.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH00"
        self.context = {"reason": reason}


class ChaosExperimentNotFoundError(ContainerChaosError):
    """Raised when a referenced chaos experiment does not exist.

    Experiment operations require the experiment to be registered
    in the chaos executor's experiment registry.  Referencing a
    nonexistent or previously deleted experiment triggers this
    exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH01"
        self.context = {"reason": reason}


class ChaosExperimentAlreadyRunningError(ContainerChaosError):
    """Raised when attempting to start an experiment that is already running.

    Each experiment can only execute once.  Attempting to start an
    experiment whose status is RUNNING, INJECTING, or OBSERVING
    triggers this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH02"
        self.context = {"reason": reason}


class ChaosExperimentAbortedError(ContainerChaosError):
    """Raised when a chaos experiment is aborted due to safety conditions.

    Abort conditions protect the platform from cascading failures
    during chaos injection.  When an abort condition is triggered,
    fault injection is immediately halted and this exception is raised.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH03"
        self.context = {"reason": reason}


class ChaosExperimentFailedStartError(ContainerChaosError):
    """Raised when a chaos experiment fails during the pre-check phase.

    Pre-checks verify that target containers exist and are healthy,
    that the operator's cognitive load permits chaos injection, and
    that blast radius limits would not be exceeded.  Failure at any
    pre-check stage triggers this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH04"
        self.context = {"reason": reason}


class ChaosFaultInjectionError(ContainerChaosError):
    """Raised when fault injection fails.

    Fault injection requires interaction with the container runtime
    layer (FizzContainerd, FizzCgroup, FizzCNI, FizzOverlay).
    Failures in any of these subsystems during fault injection
    trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH05"
        self.context = {"reason": reason}


class ChaosFaultRemovalError(ContainerChaosError):
    """Raised when fault removal fails.

    After experiment completion, injected faults must be removed
    to restore normal operation.  If fault removal fails, the
    system may remain in a degraded state.  This exception signals
    that manual intervention may be required.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH06"
        self.context = {"reason": reason}


class ChaosContainerKillError(ContainerChaosError):
    """Raised when the container kill fault fails to terminate a container.

    Container kill sends SIGKILL to the container's init process
    via FizzContainerd's task service.  If the signal delivery or
    process termination fails, this exception is raised.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH07"
        self.context = {"reason": reason}


class ChaosNetworkPartitionError(ContainerChaosError):
    """Raised when the network partition fault fails.

    Network partition isolates a container by dropping traffic on
    its veth interface via FizzCNI.  Failures in packet filter rule
    installation or veth endpoint access trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH08"
        self.context = {"reason": reason}


class ChaosCPUStressError(ContainerChaosError):
    """Raised when the CPU stress fault fails.

    CPU stress runs a busy-loop process inside the target container's
    cgroup to consume CPU quota.  Failures in process creation or
    cgroup attachment trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH09"
        self.context = {"reason": reason}


class ChaosMemoryPressureError(ContainerChaosError):
    """Raised when the memory pressure fault fails.

    Memory pressure allocates memory inside a container's cgroup
    until the memory.high threshold is reached.  Failures in
    allocation simulation or cgroup interaction trigger this
    exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH10"
        self.context = {"reason": reason}


class ChaosDiskFillError(ContainerChaosError):
    """Raised when the disk fill fault fails.

    Disk fill writes data to the container's overlay writable layer.
    Failures in overlay filesystem interaction or write operations
    trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH11"
        self.context = {"reason": reason}


class ChaosImagePullFailureError(ContainerChaosError):
    """Raised when the image pull failure fault fails to intercept pulls.

    Image pull failure intercepts requests from FizzContainerd to
    FizzRegistry.  Failures in request interception or error
    response injection trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH12"
        self.context = {"reason": reason}


class ChaosDNSFailureError(ContainerChaosError):
    """Raised when the DNS failure fault fails to disrupt resolution.

    DNS failure intercepts queries from FizzCNI's ContainerDNS.
    Failures in query interception or failure mode injection
    trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH13"
        self.context = {"reason": reason}


class ChaosNetworkLatencyError(ContainerChaosError):
    """Raised when the network latency fault fails to inject delay.

    Network latency adds delay to packets on a container's veth
    interface.  Failures in packet queue configuration or delay
    injection trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH14"
        self.context = {"reason": reason}


class ChaosGameDayError(ContainerChaosError):
    """Raised when a game day orchestration encounters an error.

    Game day errors include experiment scheduling failures,
    blast radius calculation errors, and report generation
    failures.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH15"
        self.context = {"reason": reason}


class ChaosGameDayAbortError(ContainerChaosError):
    """Raised when a game day is aborted due to system-level conditions.

    System-level abort conditions apply across all experiments
    in a game day.  When triggered, all running experiments are
    halted and faults are removed.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH16"
        self.context = {"reason": reason}


class ChaosBlastRadiusExceededError(ContainerChaosError):
    """Raised when a fault injection would exceed the blast radius limit.

    Blast radius limits prevent chaos experiments from affecting
    too many containers simultaneously, protecting the platform
    from total service disruption during testing.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH17"
        self.context = {"reason": reason}


class ChaosSteadyStateViolationError(ContainerChaosError):
    """Raised when steady-state metrics deviate beyond tolerance during injection.

    Steady-state violations indicate that the system is not
    behaving as hypothesized during fault injection.  The experiment
    may continue or abort depending on abort condition configuration.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH18"
        self.context = {"reason": reason}


class ChaosCognitiveLoadGateError(ContainerChaosError):
    """Raised when the operator's cognitive load exceeds the chaos threshold.

    FizzBob's NASA-TLX cognitive load model prevents chaos
    experiments from running when the operator lacks sufficient
    cognitive capacity to monitor and respond to injected faults.
    Emergency experiments bypass this gate.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH19"
        self.context = {"reason": reason}


class ChaosScheduleError(ContainerChaosError):
    """Raised when a chaos schedule encounters a configuration error.

    Schedule errors include invalid cron expressions, conflicting
    schedules, and scheduling conflicts with maintenance windows.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH20"
        self.context = {"reason": reason}


class ChaosReportGenerationError(ContainerChaosError):
    """Raised when experiment or game day report generation fails.

    Report generation requires steady-state metric data from
    before, during, and after fault injection.  Missing data or
    metric collection errors trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH21"
        self.context = {"reason": reason}


class ChaosTargetResolutionError(ContainerChaosError):
    """Raised when target container resolution fails.

    Target resolution uses label selectors or container IDs to
    identify containers for fault injection.  If no containers
    match or the selector is invalid, this exception is raised.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH22"
        self.context = {"reason": reason}


class ChaosContainerChaosMiddlewareError(ContainerChaosError):
    """Raised when the FizzContainerChaos middleware fails during evaluation.

    The middleware annotates FizzBuzz evaluation responses with
    active chaos experiment information.  If experiment registry
    access or context enrichment fails, this exception is raised.
    """

    def __init__(self, evaluation_number: int, reason: str) -> None:
        super().__init__(
            f"Container chaos middleware error at evaluation {evaluation_number}: {reason}"
        )
        self.error_code = "EFP-CCH23"
        self.context = {"evaluation_number": evaluation_number, "reason": reason}
        self.evaluation_number = evaluation_number

