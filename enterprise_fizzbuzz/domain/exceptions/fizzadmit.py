"""
Enterprise FizzBuzz Platform - FizzAdmit: Admission Controllers & CRD Operator Framework
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class FizzAdmitError(FizzBuzzError):
    """Base exception for all FizzAdmit admission controller and CRD operator errors.

    FizzAdmit implements the complete Kubernetes admission control pipeline
    and Custom Resource Definition operator framework for the FizzKube
    container orchestrator.  All FizzAdmit-specific failures inherit from
    this class to enable categorical error handling in the middleware
    pipeline.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzAdmit error: {reason}",
            error_code="EFP-ADM00",
            context={"reason": reason},
        )


class AdmissionChainError(FizzAdmitError):
    """Raised when the admission chain encounters a configuration or execution failure.

    The admission chain orchestrates an ordered sequence of mutating and
    validating controllers.  Configuration errors (duplicate names, invalid
    priority ranges) and execution failures (patch application errors,
    pipeline corruption) trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-ADM01"
        self.context = {"reason": reason}


class AdmissionControllerError(FizzAdmitError):
    """Raised when an admission controller encounters an internal error.

    Individual admission controllers may fail due to internal state
    corruption, resource access failures, or logic errors.  This
    generic exception covers failures that do not fit a more specific
    controller error category.
    """

    def __init__(self, controller_name: str, reason: str) -> None:
        super().__init__(f"Controller '{controller_name}': {reason}")
        self.error_code = "EFP-ADM02"
        self.context = {"controller_name": controller_name, "reason": reason}


class AdmissionDeniedError(FizzAdmitError):
    """Raised when an admission controller explicitly denies a request.

    A denial indicates that the submitted resource violates a policy
    enforced by the admission chain.  The denial message identifies
    the denying controller and the specific policy violation.
    """

    def __init__(self, controller_name: str, resource_name: str, reason: str) -> None:
        super().__init__(
            f"Denied by '{controller_name}' for resource '{resource_name}': {reason}"
        )
        self.error_code = "EFP-ADM03"
        self.context = {
            "controller_name": controller_name,
            "resource_name": resource_name,
            "reason": reason,
        }


class AdmissionTimeoutError(FizzAdmitError):
    """Raised when an admission controller exceeds its configured timeout.

    Each admission controller has a configurable timeout.  Controllers
    that do not return a decision within the timeout are terminated
    and the failure policy determines whether the request is admitted
    or denied.
    """

    def __init__(self, controller_name: str, timeout_seconds: float) -> None:
        super().__init__(
            f"Controller '{controller_name}' exceeded timeout of {timeout_seconds}s"
        )
        self.error_code = "EFP-ADM04"
        self.context = {
            "controller_name": controller_name,
            "timeout_seconds": timeout_seconds,
        }


class AdmissionWebhookError(FizzAdmitError):
    """Raised when webhook dispatch or response parsing fails.

    Webhook-based admission controllers communicate via the
    AdmissionReview protocol.  Malformed responses, serialization
    failures, or handler exceptions trigger this exception.
    """

    def __init__(self, webhook_name: str, reason: str) -> None:
        super().__init__(f"Webhook '{webhook_name}': {reason}")
        self.error_code = "EFP-ADM05"
        self.context = {"webhook_name": webhook_name, "reason": reason}


class AdmissionWebhookUnreachableError(FizzAdmitError):
    """Raised when a webhook endpoint is unreachable.

    The webhook dispatcher attempts to call the registered handler
    for each matching webhook.  If the handler is not registered or
    the simulated endpoint is unavailable, this exception is raised.
    """

    def __init__(self, webhook_name: str, endpoint: str) -> None:
        super().__init__(f"Webhook '{webhook_name}' unreachable at '{endpoint}'")
        self.error_code = "EFP-ADM06"
        self.context = {"webhook_name": webhook_name, "endpoint": endpoint}


class ResourceQuotaExhaustedError(FizzAdmitError):
    """Raised when a namespace resource quota would be exceeded.

    The ResourceQuota admission controller tracks resource usage per
    namespace.  Requests that would cause any tracked metric to exceed
    the configured hard limit are denied with this exception.
    """

    def __init__(self, namespace: str, resource: str, requested: float, available: float) -> None:
        super().__init__(
            f"Namespace '{namespace}': {resource} quota exhausted "
            f"(requested={requested}, available={available})"
        )
        self.error_code = "EFP-ADM07"
        self.context = {
            "namespace": namespace,
            "resource": resource,
            "requested": requested,
            "available": available,
        }


class LimitRangeViolationError(FizzAdmitError):
    """Raised when a resource value falls outside configured LimitRange bounds.

    The LimitRanger admission controller enforces minimum and maximum
    resource values per container.  Values outside the configured range
    or limit/request ratios exceeding the maximum trigger this exception.
    """

    def __init__(self, namespace: str, container_name: str, resource: str, reason: str) -> None:
        super().__init__(
            f"Namespace '{namespace}', container '{container_name}': "
            f"{resource} limit range violation: {reason}"
        )
        self.error_code = "EFP-ADM08"
        self.context = {
            "namespace": namespace,
            "container_name": container_name,
            "resource": resource,
            "reason": reason,
        }


class PodSecurityViolationError(FizzAdmitError):
    """Raised when a pod spec violates the namespace security profile.

    The PodSecurityAdmission controller enforces security profiles
    (Privileged, Baseline, Restricted) per namespace.  Pod specs that
    violate the active profile's constraints are denied with this
    exception when the enforcement mode is ENFORCE.
    """

    def __init__(self, namespace: str, profile: str, violations: str) -> None:
        super().__init__(
            f"Namespace '{namespace}' ({profile} profile): {violations}"
        )
        self.error_code = "EFP-ADM09"
        self.context = {
            "namespace": namespace,
            "profile": profile,
            "violations": violations,
        }


class ImagePolicyViolationError(FizzAdmitError):
    """Raised when a container image fails organizational policy checks.

    The ImagePolicy admission controller evaluates container image
    references against configured policy rules.  Images that match
    a DENY rule or fail a REQUIRE_SIGNATURE check are denied with
    this exception.
    """

    def __init__(self, image: str, rule_name: str, reason: str) -> None:
        super().__init__(f"Image '{image}' denied by rule '{rule_name}': {reason}")
        self.error_code = "EFP-ADM10"
        self.context = {"image": image, "rule_name": rule_name, "reason": reason}


class CRDError(FizzAdmitError):
    """Base exception for all CRD framework errors.

    The CRD framework enables runtime extension of the FizzKube API
    with user-defined resource types.  CRD registration, schema
    validation, and instance management failures inherit from this
    base class.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-ADM11"
        self.context = {"reason": reason}


class CRDSchemaValidationError(CRDError):
    """Raised when a CRD schema is not structural or contains invalid types.

    Every CRD must define a structural schema where every field has an
    explicit type.  Schemas that contain untyped fields, invalid type
    names, or structural violations are rejected with this exception.
    """

    def __init__(self, crd_name: str, reason: str) -> None:
        super().__init__(f"CRD '{crd_name}' schema invalid: {reason}")
        self.error_code = "EFP-ADM12"
        self.context = {"crd_name": crd_name, "reason": reason}


class CRDRegistrationError(CRDError):
    """Raised when CRD registration fails.

    CRD registration validates uniqueness of names, structural schema
    compliance, and version configuration (exactly one storage version).
    Failures in any of these checks trigger this exception.
    """

    def __init__(self, crd_name: str, reason: str) -> None:
        super().__init__(f"CRD '{crd_name}' registration failed: {reason}")
        self.error_code = "EFP-ADM13"
        self.context = {"crd_name": crd_name, "reason": reason}


class CRDInstanceValidationError(CRDError):
    """Raised when a custom resource instance fails schema validation.

    Custom resource instances are validated against the CRD's OpenAPI v3
    schema on creation and update.  Type mismatches, missing required
    fields, and constraint violations trigger this exception.
    """

    def __init__(self, crd_name: str, instance_name: str, errors: str) -> None:
        super().__init__(
            f"Instance '{instance_name}' of CRD '{crd_name}' "
            f"failed validation: {errors}"
        )
        self.error_code = "EFP-ADM14"
        self.context = {
            "crd_name": crd_name,
            "instance_name": instance_name,
            "errors": errors,
        }


class CRDNotFoundError(CRDError):
    """Raised when a referenced CRD does not exist in the registry.

    Operations targeting a CRD by name that has not been registered
    trigger this exception.
    """

    def __init__(self, crd_name: str) -> None:
        super().__init__(f"CRD '{crd_name}' not found")
        self.error_code = "EFP-ADM15"
        self.context = {"crd_name": crd_name}


class CRDDeletionError(CRDError):
    """Raised when CRD deletion fails.

    CRD deletion requires garbage collection of all instances and
    processing of any finalizers.  Stuck instances or finalizer
    failures prevent deletion and trigger this exception.
    """

    def __init__(self, crd_name: str, reason: str) -> None:
        super().__init__(f"CRD '{crd_name}' deletion failed: {reason}")
        self.error_code = "EFP-ADM16"
        self.context = {"crd_name": crd_name, "reason": reason}


class OperatorError(FizzAdmitError):
    """Base exception for all operator framework errors.

    The operator framework provides reconciliation loops, work queues,
    leader election, and metrics collection for custom controllers.
    Framework-level failures inherit from this base class.
    """

    def __init__(self, operator_name: str, reason: str) -> None:
        super().__init__(f"Operator '{operator_name}': {reason}")
        self.error_code = "EFP-ADM17"
        self.context = {"operator_name": operator_name, "reason": reason}


class OperatorReconcileError(OperatorError):
    """Raised when a reconciliation loop encounters an unrecoverable error.

    Reconciliation failures that exceed the maximum retry count or
    that indicate a fundamental configuration problem trigger this
    exception.
    """

    def __init__(self, operator_name: str, resource_key: str, reason: str) -> None:
        super().__init__(operator_name, f"reconcile failed for '{resource_key}': {reason}")
        self.error_code = "EFP-ADM18"
        self.context = {
            "operator_name": operator_name,
            "resource_key": resource_key,
            "reason": reason,
        }


class OperatorLeaderElectionError(OperatorError):
    """Raised when leader election fails or the lease expires.

    Only the elected leader processes the work queue.  Election
    failures or lease expiration halt reconciliation and trigger
    this exception.
    """

    def __init__(self, operator_name: str, reason: str) -> None:
        super().__init__(operator_name, f"leader election: {reason}")
        self.error_code = "EFP-ADM19"
        self.context = {"operator_name": operator_name, "reason": reason}


class OperatorWorkQueueError(OperatorError):
    """Raised when the work queue overflows or becomes corrupted.

    The work queue has a configurable maximum depth.  Overflow or
    internal corruption trigger this exception.
    """

    def __init__(self, operator_name: str, reason: str) -> None:
        super().__init__(operator_name, f"work queue: {reason}")
        self.error_code = "EFP-ADM20"
        self.context = {"operator_name": operator_name, "reason": reason}


class FinalizerError(FizzAdmitError):
    """Base exception for all finalizer errors.

    Finalizers enable cleanup logic on resource deletion.  Registration,
    processing, and removal failures inherit from this base class.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Finalizer error: {reason}")
        self.error_code = "EFP-ADM21"
        self.context = {"reason": reason}


class FinalizerStuckError(FinalizerError):
    """Raised when a finalizer is not removed within the configured timeout.

    Resources with a deletion timestamp that retain finalizers beyond
    the stuck timeout are flagged with this exception.
    """

    def __init__(self, resource_name: str, finalizer_name: str, elapsed_seconds: float) -> None:
        super().__init__(
            f"Finalizer '{finalizer_name}' stuck on '{resource_name}' "
            f"for {elapsed_seconds:.1f}s"
        )
        self.error_code = "EFP-ADM22"
        self.context = {
            "resource_name": resource_name,
            "finalizer_name": finalizer_name,
            "elapsed_seconds": elapsed_seconds,
        }


class FinalizerRemovalError(FinalizerError):
    """Raised when a finalizer handler fails during removal.

    Finalizer handlers execute cleanup logic before the finalizer
    string is removed from the resource's metadata.  Handler failures
    leave the finalizer in place for retry on the next reconciliation.
    """

    def __init__(self, resource_name: str, finalizer_name: str, reason: str) -> None:
        super().__init__(
            f"Failed to remove '{finalizer_name}' from '{resource_name}': {reason}"
        )
        self.error_code = "EFP-ADM23"
        self.context = {
            "resource_name": resource_name,
            "finalizer_name": finalizer_name,
            "reason": reason,
        }


class OwnerReferenceError(FizzAdmitError):
    """Raised when an owner reference is invalid or creates a cycle.

    Owner references establish parent-child relationships between
    resources.  Invalid UIDs, self-references, or cyclic ownership
    chains trigger this exception.
    """

    def __init__(self, resource_name: str, reason: str) -> None:
        super().__init__(f"Owner reference error on '{resource_name}': {reason}")
        self.error_code = "EFP-ADM24"
        self.context = {"resource_name": resource_name, "reason": reason}


class GarbageCollectionError(FizzAdmitError):
    """Raised when garbage collection of orphaned resources fails.

    The garbage collector identifies resources whose owners have been
    deleted and removes them according to the propagation policy.
    Scan or deletion failures trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Garbage collection error: {reason}")
        self.error_code = "EFP-ADM25"
        self.context = {"reason": reason}


class CascadingDeletionError(FizzAdmitError):
    """Raised when cascading deletion fails during child resource cleanup.

    Cascading deletion (foreground or background) requires enumerating
    and deleting all child resources before the parent can be removed.
    Failures during child cleanup trigger this exception.
    """

    def __init__(self, parent_name: str, reason: str) -> None:
        super().__init__(f"Cascading deletion of '{parent_name}': {reason}")
        self.error_code = "EFP-ADM26"
        self.context = {"parent_name": parent_name, "reason": reason}


class FizzAdmitMiddlewareError(FizzAdmitError):
    """Raised when the FizzAdmit middleware fails to process an evaluation.

    The middleware intercepts each FizzBuzz evaluation to run admission
    control checks.  Initialization failures or admission processing
    errors during middleware execution trigger this exception.
    """

    def __init__(self, evaluation_number: int, reason: str) -> None:
        super().__init__(
            f"Middleware error at evaluation {evaluation_number}: {reason}"
        )
        self.error_code = "EFP-ADM27"
        self.context = {"evaluation_number": evaluation_number, "reason": reason}
        self.evaluation_number = evaluation_number
