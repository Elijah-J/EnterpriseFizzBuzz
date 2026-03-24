"""
Enterprise FizzBuzz Platform - FizzKubeV2 Container-Aware Orchestrator Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class KubeV2Error(FizzBuzzError):
    """Base exception for all FizzKubeV2 errors.

    Every failure mode in the CRI-integrated orchestrator traces back
    to this class.  Error codes follow the EFP-KV2xx convention.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-KV200",
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.context = context or {}


class KubeletV2Error(KubeV2Error):
    """Raised when the CRI-integrated kubelet encounters a lifecycle failure.

    The kubelet coordinates image pulls, sandbox creation, init container
    execution, sidecar injection, probe registration, and volume provisioning.
    Failures at any stage of this pipeline trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"KubeletV2 error: {reason}",
            error_code="EFP-KV201",
            context={"reason": reason},
        )


class KV2ImagePullError(KubeV2Error):
    """Raised when an image pull operation fails.

    Image pulls can fail due to registry unavailability, authentication
    errors, network timeouts, or content integrity failures.
    """

    def __init__(self, image: str, policy: str, reason: str) -> None:
        super().__init__(
            f"Failed to pull image '{image}' with policy {policy}: {reason}",
            error_code="EFP-KV202",
            context={"image": image, "policy": policy, "reason": reason},
        )


class ImagePullBackOffError(KubeV2Error):
    """Raised when an image pull enters exponential backoff.

    After repeated pull failures, the kubelet enters a backoff state
    to prevent overwhelming the registry with retry requests.
    """

    def __init__(self, image: str, attempt: int, backoff_seconds: float) -> None:
        super().__init__(
            f"Image '{image}' in pull backoff (attempt {attempt}, "
            f"next retry in {backoff_seconds:.1f}s)",
            error_code="EFP-KV203",
            context={
                "image": image,
                "attempt": attempt,
                "backoff_seconds": backoff_seconds,
            },
        )


class ImageNotPresentError(KubeV2Error):
    """Raised when an image is not present locally and the pull policy is Never.

    Air-gapped deployments require all images to be pre-provisioned.
    This exception indicates an image was referenced that has not been
    loaded into the local content store.
    """

    def __init__(self, image: str) -> None:
        super().__init__(
            f"Image '{image}' not present locally and pull policy is Never",
            error_code="EFP-KV204",
            context={"image": image},
        )


class PullSecretError(KubeV2Error):
    """Raised when pull secret retrieval or authentication fails.

    Private registries require credentials to be provided via pull secrets.
    This exception covers missing secrets, invalid credentials, and
    registry authentication failures.
    """

    def __init__(self, secret_name: str, registry: str, reason: str) -> None:
        super().__init__(
            f"Pull secret '{secret_name}' failed for registry '{registry}': {reason}",
            error_code="EFP-KV205",
            context={
                "secret_name": secret_name,
                "registry": registry,
                "reason": reason,
            },
        )


class InitContainerFailedError(KubeV2Error):
    """Raised when an init container exits with a non-zero code.

    Init containers must complete successfully before application
    containers can start.  A non-zero exit code halts the pod
    startup sequence.
    """

    def __init__(self, init_name: str, exit_code: int, pod_name: str) -> None:
        super().__init__(
            f"Init container '{init_name}' in pod '{pod_name}' "
            f"failed with exit code {exit_code}",
            error_code="EFP-KV206",
            context={
                "init_name": init_name,
                "exit_code": exit_code,
                "pod_name": pod_name,
            },
        )


class InitContainerTimeoutError(KubeV2Error):
    """Raised when an init container exceeds its execution timeout.

    Init containers have a configurable timeout to prevent indefinite
    blocking of the pod startup sequence.
    """

    def __init__(self, init_name: str, timeout_seconds: float) -> None:
        super().__init__(
            f"Init container '{init_name}' timed out after {timeout_seconds:.1f}s",
            error_code="EFP-KV207",
            context={
                "init_name": init_name,
                "timeout_seconds": timeout_seconds,
            },
        )


class SidecarInjectionError(KubeV2Error):
    """Raised when sidecar injection fails for a pod.

    Sidecar injection involves modifying the pod spec to add additional
    containers, volumes, and init containers.  Failures can occur due
    to conflicting container names, resource quota violations, or
    invalid injection policy configurations.
    """

    def __init__(self, pod_name: str, sidecar_name: str, reason: str) -> None:
        super().__init__(
            f"Sidecar '{sidecar_name}' injection failed for pod '{pod_name}': {reason}",
            error_code="EFP-KV208",
            context={
                "pod_name": pod_name,
                "sidecar_name": sidecar_name,
                "reason": reason,
            },
        )


class SidecarLifecycleError(KubeV2Error):
    """Raised when a sidecar container lifecycle ordering is violated.

    Sidecars must reach their expected state before the main container
    can start.  This exception indicates a state machine violation.
    """

    def __init__(
        self, sidecar_name: str, expected_state: str, actual_state: str
    ) -> None:
        super().__init__(
            f"Sidecar '{sidecar_name}' expected state '{expected_state}' "
            f"but found '{actual_state}'",
            error_code="EFP-KV209",
            context={
                "sidecar_name": sidecar_name,
                "expected_state": expected_state,
                "actual_state": actual_state,
            },
        )


class ProbeFailedError(KubeV2Error):
    """Raised when a health probe fails.

    Generic probe failure covering HTTP, TCP, and exec probe types
    across readiness, liveness, and startup categories.
    """

    def __init__(
        self,
        container_id: str,
        probe_category: str,
        probe_type: str,
        reason: str,
    ) -> None:
        super().__init__(
            f"Probe {probe_category}/{probe_type} failed for container "
            f"'{container_id}': {reason}",
            error_code="EFP-KV210",
            context={
                "container_id": container_id,
                "probe_category": probe_category,
                "probe_type": probe_type,
                "reason": reason,
            },
        )


class ProbeTimeoutError(KubeV2Error):
    """Raised when a probe execution exceeds its timeout.

    Probes have a configurable timeout to prevent indefinite blocking
    of the health check cycle.
    """

    def __init__(
        self, container_id: str, probe_category: str, timeout_seconds: float
    ) -> None:
        super().__init__(
            f"Probe {probe_category} timed out for container '{container_id}' "
            f"after {timeout_seconds:.1f}s",
            error_code="EFP-KV211",
            context={
                "container_id": container_id,
                "probe_category": probe_category,
                "timeout_seconds": timeout_seconds,
            },
        )


class ReadinessProbeFailedError(ProbeFailedError):
    """Raised when the readiness probe threshold is breached.

    Readiness failures remove the container from service endpoints
    but do not trigger a restart.
    """

    def __init__(
        self, container_id: str, consecutive_failures: int, threshold: int
    ) -> None:
        super().__init__(
            container_id=container_id,
            probe_category="readiness",
            probe_type="threshold",
            reason=(
                f"Consecutive failures ({consecutive_failures}) "
                f"reached threshold ({threshold})"
            ),
        )
        self.error_code = "EFP-KV212"
        self.context["consecutive_failures"] = consecutive_failures
        self.context["threshold"] = threshold


class LivenessProbeFailedError(ProbeFailedError):
    """Raised when the liveness probe threshold is breached.

    Liveness failures cause the container to be killed and restarted
    according to the pod's restart policy.
    """

    def __init__(
        self, container_id: str, consecutive_failures: int, threshold: int
    ) -> None:
        super().__init__(
            container_id=container_id,
            probe_category="liveness",
            probe_type="threshold",
            reason=(
                f"Consecutive failures ({consecutive_failures}) "
                f"reached threshold ({threshold}), container will restart"
            ),
        )
        self.error_code = "EFP-KV213"
        self.context["consecutive_failures"] = consecutive_failures
        self.context["threshold"] = threshold


class StartupProbeFailedError(ProbeFailedError):
    """Raised when the startup probe never succeeds within the allowed time.

    Startup probe failure indicates the container did not become ready
    within its allotted startup period.
    """

    def __init__(self, container_id: str, elapsed_seconds: float) -> None:
        super().__init__(
            container_id=container_id,
            probe_category="startup",
            probe_type="timeout",
            reason=f"Startup probe never succeeded after {elapsed_seconds:.1f}s",
        )
        self.error_code = "EFP-KV214"
        self.context["elapsed_seconds"] = elapsed_seconds


class VolumeProvisionError(KubeV2Error):
    """Raised when volume provisioning fails.

    Volume provisioning allocates storage for emptyDir, PVC, configMap,
    and secret volume types.  Failures include storage exhaustion,
    invalid volume configurations, and backend errors.
    """

    def __init__(self, volume_name: str, volume_type: str, reason: str) -> None:
        super().__init__(
            f"Volume '{volume_name}' ({volume_type}) provisioning failed: {reason}",
            error_code="EFP-KV215",
            context={
                "volume_name": volume_name,
                "volume_type": volume_type,
                "reason": reason,
            },
        )


class VolumeMountError(KubeV2Error):
    """Raised when a volume mount into a container fails.

    Volume mounts can fail due to conflicting mount paths, read-only
    filesystem violations, or invalid sub-path references.
    """

    def __init__(
        self,
        volume_name: str,
        container_id: str,
        mount_path: str,
        reason: str,
    ) -> None:
        super().__init__(
            f"Volume '{volume_name}' mount at '{mount_path}' in container "
            f"'{container_id}' failed: {reason}",
            error_code="EFP-KV216",
            context={
                "volume_name": volume_name,
                "container_id": container_id,
                "mount_path": mount_path,
                "reason": reason,
            },
        )


class PVCNotFoundError(KubeV2Error):
    """Raised when a referenced PersistentVolumeClaim does not exist.

    Pods referencing PVCs that have not been created will fail to start
    because the volume cannot be provisioned without a bound claim.
    """

    def __init__(self, claim_name: str) -> None:
        super().__init__(
            f"PersistentVolumeClaim '{claim_name}' not found",
            error_code="EFP-KV217",
            context={"claim_name": claim_name},
        )


class ContainerRestartBackoffError(KubeV2Error):
    """Raised when a container is in restart backoff.

    After repeated failures, the kubelet applies exponential backoff
    before allowing the next restart attempt.
    """

    def __init__(
        self, container_id: str, restart_count: int, backoff_seconds: float
    ) -> None:
        super().__init__(
            f"Container '{container_id}' in restart backoff "
            f"(restarts={restart_count}, next in {backoff_seconds:.1f}s)",
            error_code="EFP-KV218",
            context={
                "container_id": container_id,
                "restart_count": restart_count,
                "backoff_seconds": backoff_seconds,
            },
        )


class PodTerminationError(KubeV2Error):
    """Raised when graceful pod termination fails.

    Pod termination involves sending SIGTERM to all containers, waiting
    the grace period, then sending SIGKILL.  This exception is raised
    when the termination sequence encounters errors that prevent clean
    shutdown.
    """

    def __init__(self, pod_name: str, reason: str) -> None:
        super().__init__(
            f"Pod '{pod_name}' termination failed: {reason}",
            error_code="EFP-KV219",
            context={"pod_name": pod_name, "reason": reason},
        )


class KubeV2MiddlewareError(KubeV2Error):
    """Raised when the FizzKubeV2 middleware fails to process an evaluation.

    The middleware wraps each evaluation in a full pod lifecycle.  Errors
    during any phase (image pull, init, sidecar, probe, volume, evaluation)
    are wrapped in this exception after best-effort cleanup.
    """

    def __init__(self, evaluation_number: int, reason: str) -> None:
        super().__init__(
            f"FizzKubeV2 middleware error at evaluation {evaluation_number}: {reason}",
            error_code="EFP-KV220",
            context={"evaluation_number": evaluation_number, "reason": reason},
        )
        self.evaluation_number = evaluation_number

