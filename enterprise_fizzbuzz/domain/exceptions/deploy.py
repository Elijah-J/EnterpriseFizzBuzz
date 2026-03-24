"""
Enterprise FizzBuzz Platform - FizzDeploy Container-Native Deployment Pipeline Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class DeployError(FizzBuzzError):
    """Base exception for all FizzDeploy deployment pipeline errors."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-DPL00"
        self.context = {"reason": reason}


class DeployPipelineError(DeployError):
    """Raised when the deployment pipeline execution fails.

    Pipeline failures occur when a stage cannot complete within the
    configured timeout, when stage sequencing encounters an illegal
    state transition, or when the pipeline execution engine encounters
    an unrecoverable internal error.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-DPL01"
        self.context = {"reason": reason}


class DeployStageError(DeployError):
    """Raised when a pipeline stage execution fails.

    Stage failures propagate from individual step failures, stage-level
    timeouts, or illegal step configurations within the stage definition.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-DPL02"
        self.context = {"reason": reason}


class DeployStepError(DeployError):
    """Raised when a pipeline step fails after exhausting all retry attempts.

    The retry policy's exponential backoff has been fully consumed.  The
    step's action callable returned an error or raised an exception on
    every attempt, including the initial execution and all configured
    retries.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-DPL03"
        self.context = {"reason": reason}


class DeployStrategyError(DeployError):
    """Raised when an unknown or unsupported deployment strategy is requested.

    The strategy factory received a strategy identifier that does not
    map to any of the four supported deployment strategies: rolling
    update, blue-green, canary, or recreate.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-DPL04"
        self.context = {"reason": reason}


class RollingUpdateError(DeployError):
    """Raised when the rolling update strategy encounters a failure.

    Rolling update failures include pod readiness probe timeouts,
    batch replacement failures where new pods cannot achieve ready
    state, and surge limit violations during proportional scaling.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-DPL05"
        self.context = {"reason": reason}


class BlueGreenError(DeployError):
    """Raised when the blue-green deployment strategy fails.

    Blue-green failures occur when the inactive environment fails
    validation checks, preventing traffic switch, or when the
    environment provisioning cannot allocate the required resources.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-DPL06"
        self.context = {"reason": reason}


class CanaryError(DeployError):
    """Raised when the canary deployment detects a regression.

    Automated canary analysis has determined that the canary population
    exhibits statistically significant degradation in error rate, P99
    latency, or resource utilization compared to the baseline population.
    The canary has been rolled back to 0% traffic.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-DPL07"
        self.context = {"reason": reason}


class RecreateError(DeployError):
    """Raised when the recreate deployment strategy fails.

    Recreate failures occur when existing pods cannot be gracefully
    terminated within the shutdown timeout, or when new pods fail
    to achieve ready state within the startup timeout.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-DPL08"
        self.context = {"reason": reason}


class DeployManifestError(DeployError):
    """Raised for general deployment manifest errors."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-DPL09"
        self.context = {"reason": reason}


class ManifestParseError(DeployManifestError):
    """Raised when YAML syntax errors prevent manifest parsing.

    The provided manifest string contains malformed YAML that cannot
    be parsed into a valid document structure.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-DPL10"
        self.context = {"reason": reason}


class ManifestValidationError(DeployManifestError):
    """Raised when a manifest fails schema validation.

    The manifest was successfully parsed as YAML but does not conform
    to the deployment manifest schema.  Required fields may be missing,
    strategy parameters may be invalid, or resource constraint formats
    may not match the expected pattern.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-DPL11"
        self.context = {"reason": reason}


class GitOpsReconcileError(DeployError):
    """Raised when the GitOps reconciliation loop encounters a failure.

    The reconciler was unable to compare declared state against actual
    cluster state, or encountered an internal error during the
    reconciliation pass.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-DPL12"
        self.context = {"reason": reason}


class GitOpsDriftError(DeployError):
    """Raised when configuration drift is detected between declared and actual state.

    The GitOps reconciler has identified one or more fields where the
    actual cluster state diverges from the declared manifest state.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-DPL13"
        self.context = {"reason": reason}


class GitOpsSyncError(DeployError):
    """Raised when drift correction fails during synchronization.

    The reconciler detected drift and attempted to apply corrections,
    but the sync operation failed to bring the actual state into
    alignment with the declared state.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-DPL14"
        self.context = {"reason": reason}


class RollbackError(DeployError):
    """Raised for general rollback operation failures."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-DPL15"
        self.context = {"reason": reason}


class RollbackRevisionNotFoundError(RollbackError):
    """Raised when the target revision does not exist in the revision history.

    The rollback manager was asked to restore a revision number that
    is not present in the deployment's revision history.  The revision
    may have been pruned by the history depth limit or may never have
    existed.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-DPL16"
        self.context = {"reason": reason}


class RollbackStrategyError(RollbackError):
    """Raised when the strategy-aware rollback operation fails.

    The rollback attempted to restore the previous deployment state
    using the original strategy, but the traffic switch, pod
    restoration, or environment promotion failed.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-DPL17"
        self.context = {"reason": reason}


class DeployGateError(DeployError):
    """Raised for general deployment gate errors."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-DPL18"
        self.context = {"reason": reason}


class CognitiveLoadGateError(DeployGateError):
    """Raised when Bob McFizzington's cognitive load exceeds the deployment threshold.

    The NASA-TLX assessment has determined that the sole operator of the
    Enterprise FizzBuzz Platform is cognitively overloaded.  Proceeding
    with a deployment under these conditions risks incident response
    failure, as Bob would be unable to monitor the rollout, interpret
    health check results, or execute a rollback if the deployment
    introduces a regression.  The deployment has been queued until
    Bob's cognitive load decreases to safe operational levels.

    Emergency deployments may bypass this gate via the --fizzdeploy-emergency
    flag, which records the bypass in the audit log for post-incident review.
    """

    def __init__(self, deployment_name: str, current_score: float, threshold: float) -> None:
        super().__init__(
            f"Deployment '{deployment_name}' blocked: operator cognitive load "
            f"{current_score:.1f} exceeds threshold {threshold:.1f}"
        )
        self.error_code = "EFP-DPL19"
        self.context = {
            "deployment_name": deployment_name,
            "current_score": current_score,
            "threshold": threshold,
        }


class DeployDashboardError(DeployError):
    """Raised when the deployment dashboard fails to render.

    The dashboard renderer encountered an error while generating the
    ASCII representation of pipeline status, revision history, drift
    reports, or canary analysis results.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-DPL20"
        self.context = {"reason": reason}


class DeployMiddlewareError(DeployError):
    """Raised when the FizzDeploy middleware fails to process an evaluation.

    The middleware could not enrich the processing context with deployment
    revision metadata, or failed to delegate to the next handler in the
    middleware pipeline.
    """

    def __init__(self, evaluation_number: int, reason: str) -> None:
        super().__init__(
            f"FizzDeploy middleware error at evaluation {evaluation_number}: {reason}"
        )
        self.error_code = "EFP-DPL21"
        self.context = {"evaluation_number": evaluation_number, "reason": reason}
        self.evaluation_number = evaluation_number

