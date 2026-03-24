"""
Enterprise FizzBuzz Platform - FizzAdmit Test Suite

Tests for the admission controller chain, CRD operator framework,
resource quota enforcement, limit range validation, pod security
admission, image policy, webhook dispatch, finalizer management,
garbage collection, and operator reconciliation.
"""

from __future__ import annotations

import copy
import threading
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from enterprise_fizzbuzz.infrastructure.fizzadmit import (
    FIZZADMIT_VERSION,
    ADMISSION_API_VERSION,
    CRD_API_VERSION,
    DEFAULT_ADMISSION_TIMEOUT,
    DEFAULT_FINALIZER_TIMEOUT,
    MIDDLEWARE_PRIORITY,
    AdmissionPhase,
    AdmissionOperation,
    FailurePolicy,
    SideEffects,
    SecurityProfile,
    EnforcementMode,
    ImagePolicyAction,
    PropagationPolicy,
    GroupVersionKind,
    GroupVersionResource,
    UserInfo,
    AdmissionStatus,
    JsonPatchOperation,
    AdmissionRequest,
    AdmissionResponse,
    AdmissionReview,
    AdmissionControllerRegistration,
    RuleWithOperations,
    WebhookClientConfig,
    MutatingWebhookConfiguration,
    ValidatingWebhookConfiguration,
    ResourceQuota,
    LimitRange,
    ImagePolicyRule,
    CRDNames,
    PrinterColumn,
    SubResources,
    CRDVersion,
    CustomResourceDefinition,
    OwnerReference,
    ReconcileRequest,
    ReconcileResult,
    OperatorMetrics,
    AdmissionAuditRecord,
    AdmissionController,
    AdmissionChain,
    ResourceQuotaAdmissionController,
    LimitRangerAdmissionController,
    PodSecurityAdmissionController,
    ImagePolicyAdmissionController,
    WebhookDispatcher,
    OpenAPISchemaValidator,
    CRDRegistry,
    FinalizerManager,
    GarbageCollector,
    Reconciler,
    ReconcileLoop,
    OperatorBuilder,
    Operator,
    FizzBuzzClusterOperator,
    FizzBuzzBackupOperator,
    FizzAdmitMiddleware,
    FizzAdmitSubsystem,
    apply_patches,
    create_fizzadmit_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions import (
    AdmissionChainError,
    CRDRegistrationError,
    CRDSchemaValidationError,
    CRDNotFoundError,
    CRDInstanceValidationError,
    OperatorError,
)


# ── Helpers ──────────────────────────────────────────────────────

def _make_request(
    operation: AdmissionOperation = AdmissionOperation.CREATE,
    namespace: str = "default",
    name: str = "test-pod",
    kind: str = "Pod",
    obj: dict = None,
    old_obj: dict = None,
    dry_run: bool = False,
) -> AdmissionRequest:
    """Build a test AdmissionRequest."""
    return AdmissionRequest(
        uid=str(uuid.uuid4()),
        kind=GroupVersionKind(group="", version="v1", kind=kind),
        resource=GroupVersionResource(group="", version="v1", resource=f"{kind.lower()}s"),
        operation=operation,
        namespace=namespace,
        name=name,
        object=obj or {
            "metadata": {"name": name, "namespace": namespace, "labels": {}},
            "spec": {"containers": []},
        },
        old_object=old_obj,
        dry_run=dry_run,
    )


def _make_pod_object(
    name: str = "test-pod",
    namespace: str = "default",
    containers: list = None,
    volumes: list = None,
    host_network: bool = False,
    host_pid: bool = False,
    host_ipc: bool = False,
    labels: dict = None,
) -> dict:
    """Build a test pod object."""
    return {
        "metadata": {
            "name": name,
            "namespace": namespace,
            "labels": labels or {},
        },
        "spec": {
            "containers": containers or [],
            "volumes": volumes or [],
            "hostNetwork": host_network,
            "hostPID": host_pid,
            "hostIPC": host_ipc,
        },
    }


class AllowAllController(AdmissionController):
    """Test controller that allows everything."""

    def admit(self, request: AdmissionRequest) -> AdmissionResponse:
        return AdmissionResponse(uid=request.uid, allowed=True)


class DenyAllController(AdmissionController):
    """Test controller that denies everything."""

    def admit(self, request: AdmissionRequest) -> AdmissionResponse:
        return AdmissionResponse(
            uid=request.uid,
            allowed=False,
            status=AdmissionStatus(code=403, message="denied", reason="Denied"),
        )


class MutatingController(AdmissionController):
    """Test controller that adds a label."""

    def admit(self, request: AdmissionRequest) -> AdmissionResponse:
        return AdmissionResponse(
            uid=request.uid,
            allowed=True,
            patch=[
                JsonPatchOperation(
                    op="add",
                    path="/metadata/labels/mutated",
                    value="true",
                ),
            ],
        )


class ErrorController(AdmissionController):
    """Test controller that raises an exception."""

    def admit(self, request: AdmissionRequest) -> AdmissionResponse:
        raise RuntimeError("controller error")


# ── 9.1 AdmissionReview Protocol ────────────────────────────────

class TestAdmissionReviewProtocol:

    def test_admission_request_defaults(self):
        req = _make_request()
        assert req.uid
        assert req.namespace == "default"
        assert req.dry_run is False

    def test_admission_response_allowed(self):
        resp = AdmissionResponse(uid="test-uid", allowed=True)
        assert resp.allowed is True
        assert resp.status is None
        assert resp.patch is None

    def test_admission_response_denied(self):
        resp = AdmissionResponse(
            uid="test-uid",
            allowed=False,
            status=AdmissionStatus(code=403, message="forbidden", reason="Forbidden"),
        )
        assert resp.allowed is False
        assert resp.status.code == 403

    def test_admission_review_envelope(self):
        req = _make_request()
        review = AdmissionReview(request=req)
        assert review.api_version == ADMISSION_API_VERSION
        assert review.kind == "AdmissionReview"
        assert review.request.uid == req.uid

    def test_json_patch_add(self):
        obj = {"a": 1}
        result = apply_patches(obj, [
            JsonPatchOperation(op="add", path="/b", value=2),
        ])
        assert result == {"a": 1, "b": 2}

    def test_json_patch_remove(self):
        obj = {"a": 1, "b": 2}
        result = apply_patches(obj, [
            JsonPatchOperation(op="remove", path="/b"),
        ])
        assert result == {"a": 1}

    def test_json_patch_replace(self):
        obj = {"a": 1}
        result = apply_patches(obj, [
            JsonPatchOperation(op="replace", path="/a", value=99),
        ])
        assert result == {"a": 99}

    def test_json_patch_move(self):
        obj = {"a": 1, "b": {}}
        result = apply_patches(obj, [
            JsonPatchOperation(op="move", path="/b/c", from_path="/a"),
        ])
        assert result == {"b": {"c": 1}}

    def test_json_patch_copy(self):
        obj = {"a": 1}
        result = apply_patches(obj, [
            JsonPatchOperation(op="copy", path="/b", from_path="/a"),
        ])
        assert result == {"a": 1, "b": 1}

    def test_json_patch_nested_path(self):
        obj = {"a": {"b": {"c": 1}}}
        result = apply_patches(obj, [
            JsonPatchOperation(op="replace", path="/a/b/c", value=42),
        ])
        assert result["a"]["b"]["c"] == 42

    def test_json_patch_escape_sequences(self):
        obj = {"a~b": 1, "c/d": 2}
        result = apply_patches(obj, [
            JsonPatchOperation(op="replace", path="/a~0b", value=10),
        ])
        assert result["a~b"] == 10
        result2 = apply_patches(obj, [
            JsonPatchOperation(op="replace", path="/c~1d", value=20),
        ])
        assert result2["c/d"] == 20

    def test_json_patch_invalid_path(self):
        obj = {"a": 1}
        with pytest.raises(AdmissionChainError):
            apply_patches(obj, [
                JsonPatchOperation(op="replace", path="/nonexistent", value=1),
            ])

    def test_json_patch_multiple_operations(self):
        obj = {"a": 1}
        result = apply_patches(obj, [
            JsonPatchOperation(op="add", path="/b", value=2),
            JsonPatchOperation(op="add", path="/c", value=3),
            JsonPatchOperation(op="replace", path="/a", value=10),
        ])
        assert result == {"a": 10, "b": 2, "c": 3}

    def test_user_info_serialization(self):
        user = UserInfo(username="admin", groups=["system:masters"], uid="uid-1")
        assert user.username == "admin"
        assert "system:masters" in user.groups

    def test_dry_run_flag_propagation(self):
        req = _make_request(dry_run=True)
        assert req.dry_run is True


# ── 9.2 Admission Chain ─────────────────────────────────────────

class TestAdmissionChain:

    def test_empty_chain_admits_all(self):
        chain = AdmissionChain()
        req = _make_request()
        resp = chain.admit(req)
        assert resp.allowed is True

    def test_mutating_before_validating(self):
        chain = AdmissionChain()
        order = []

        class OrderTracker(AdmissionController):
            def __init__(self, label):
                self.label = label
            def admit(self, request):
                order.append(self.label)
                return AdmissionResponse(uid=request.uid, allowed=True)

        chain.register(AdmissionControllerRegistration(
            name="val", phase=AdmissionPhase.VALIDATING, priority=100,
            controller=OrderTracker("validating"),
        ))
        chain.register(AdmissionControllerRegistration(
            name="mut", phase=AdmissionPhase.MUTATING, priority=100,
            controller=OrderTracker("mutating"),
        ))
        chain.admit(_make_request())
        assert order == ["mutating", "validating"]

    def test_priority_ordering_within_phase(self):
        chain = AdmissionChain()
        order = []

        class OrderTracker(AdmissionController):
            def __init__(self, label):
                self.label = label
            def admit(self, request):
                order.append(self.label)
                return AdmissionResponse(uid=request.uid, allowed=True)

        chain.register(AdmissionControllerRegistration(
            name="second", phase=AdmissionPhase.MUTATING, priority=200,
            controller=OrderTracker("second"),
        ))
        chain.register(AdmissionControllerRegistration(
            name="first", phase=AdmissionPhase.MUTATING, priority=100,
            controller=OrderTracker("first"),
        ))
        chain.admit(_make_request())
        assert order == ["first", "second"]

    def test_mutating_patches_applied(self):
        chain = AdmissionChain()
        chain.register(AdmissionControllerRegistration(
            name="mutator", phase=AdmissionPhase.MUTATING, priority=100,
            controller=MutatingController(),
        ))
        req = _make_request()
        resp = chain.admit(req)
        assert resp.allowed is True
        assert resp.patch is not None
        assert len(resp.patch) == 1

    def test_mutating_sequential_patches(self):
        chain = AdmissionChain()

        class AddLabel(AdmissionController):
            def __init__(self, key, value):
                self._key = key
                self._value = value
            def admit(self, request):
                return AdmissionResponse(
                    uid=request.uid,
                    allowed=True,
                    patch=[JsonPatchOperation(
                        op="add", path=f"/metadata/labels/{self._key}",
                        value=self._value,
                    )],
                )

        chain.register(AdmissionControllerRegistration(
            name="label-a", phase=AdmissionPhase.MUTATING, priority=100,
            controller=AddLabel("a", "1"),
        ))
        chain.register(AdmissionControllerRegistration(
            name="label-b", phase=AdmissionPhase.MUTATING, priority=200,
            controller=AddLabel("b", "2"),
        ))
        resp = chain.admit(_make_request())
        assert resp.allowed is True
        assert len(resp.patch) == 2

    def test_validating_reject_stops_chain(self):
        chain = AdmissionChain()
        chain.register(AdmissionControllerRegistration(
            name="denier", phase=AdmissionPhase.VALIDATING, priority=100,
            controller=DenyAllController(),
        ))
        chain.register(AdmissionControllerRegistration(
            name="never-reached", phase=AdmissionPhase.VALIDATING, priority=200,
            controller=AllowAllController(),
        ))
        resp = chain.admit(_make_request())
        assert resp.allowed is False

    def test_mutating_reject_short_circuits(self):
        chain = AdmissionChain()
        chain.register(AdmissionControllerRegistration(
            name="denier", phase=AdmissionPhase.MUTATING, priority=100,
            controller=DenyAllController(),
        ))
        resp = chain.admit(_make_request())
        assert resp.allowed is False

    def test_operation_filtering(self):
        chain = AdmissionChain()
        invoked = []

        class Tracker(AdmissionController):
            def admit(self, request):
                invoked.append(True)
                return AdmissionResponse(uid=request.uid, allowed=True)

        chain.register(AdmissionControllerRegistration(
            name="delete-only", phase=AdmissionPhase.VALIDATING, priority=100,
            controller=Tracker(),
            operations=[AdmissionOperation.DELETE],
        ))
        chain.admit(_make_request(operation=AdmissionOperation.CREATE))
        assert len(invoked) == 0

    def test_resource_filtering(self):
        chain = AdmissionChain()
        invoked = []

        class Tracker(AdmissionController):
            def admit(self, request):
                invoked.append(True)
                return AdmissionResponse(uid=request.uid, allowed=True)

        chain.register(AdmissionControllerRegistration(
            name="service-only", phase=AdmissionPhase.VALIDATING, priority=100,
            controller=Tracker(),
            resources=[GroupVersionResource(group="", version="v1", resource="services")],
        ))
        chain.admit(_make_request())
        assert len(invoked) == 0

    def test_namespace_filtering(self):
        chain = AdmissionChain()
        invoked = []

        class Tracker(AdmissionController):
            def admit(self, request):
                invoked.append(True)
                return AdmissionResponse(uid=request.uid, allowed=True)

        chain.register(AdmissionControllerRegistration(
            name="prod-only", phase=AdmissionPhase.VALIDATING, priority=100,
            controller=Tracker(),
            namespaces=["production"],
        ))
        chain.admit(_make_request(namespace="default"))
        assert len(invoked) == 0

    def test_wildcard_matching(self):
        chain = AdmissionChain()
        invoked = []

        class Tracker(AdmissionController):
            def admit(self, request):
                invoked.append(True)
                return AdmissionResponse(uid=request.uid, allowed=True)

        chain.register(AdmissionControllerRegistration(
            name="all", phase=AdmissionPhase.VALIDATING, priority=100,
            controller=Tracker(),
            namespaces=["*"],
        ))
        chain.admit(_make_request(namespace="anything"))
        assert len(invoked) == 1

    def test_dry_run_skips_side_effects(self):
        chain = AdmissionChain()
        invoked = []

        class Tracker(AdmissionController):
            def admit(self, request):
                invoked.append(True)
                return AdmissionResponse(uid=request.uid, allowed=True)

        chain.register(AdmissionControllerRegistration(
            name="side-effect", phase=AdmissionPhase.MUTATING, priority=100,
            controller=Tracker(),
            side_effects=SideEffects.SOME,
        ))
        resp = chain.admit(_make_request(dry_run=True))
        assert resp.allowed is True
        assert len(invoked) == 0

    def test_failure_policy_fail(self):
        chain = AdmissionChain()
        chain.register(AdmissionControllerRegistration(
            name="broken", phase=AdmissionPhase.VALIDATING, priority=100,
            controller=ErrorController(),
            failure_policy=FailurePolicy.FAIL,
        ))
        resp = chain.admit(_make_request())
        assert resp.allowed is False

    def test_failure_policy_ignore(self):
        chain = AdmissionChain()
        chain.register(AdmissionControllerRegistration(
            name="broken", phase=AdmissionPhase.VALIDATING, priority=100,
            controller=ErrorController(),
            failure_policy=FailurePolicy.IGNORE,
        ))
        resp = chain.admit(_make_request())
        assert resp.allowed is True
        assert any("IGNORE" in w for w in resp.warnings)

    def test_audit_log_recorded(self):
        chain = AdmissionChain()
        chain.register(AdmissionControllerRegistration(
            name="audited", phase=AdmissionPhase.VALIDATING, priority=100,
            controller=AllowAllController(),
        ))
        chain.admit(_make_request())
        log = chain.get_audit_log()
        assert len(log) == 1
        assert log[0].controller_name == "audited"

    def test_audit_log_bounded(self):
        chain = AdmissionChain(max_audit_records=5)
        chain.register(AdmissionControllerRegistration(
            name="audited", phase=AdmissionPhase.VALIDATING, priority=100,
            controller=AllowAllController(),
        ))
        for _ in range(10):
            chain.admit(_make_request())
        log = chain.get_audit_log(limit=100)
        assert len(log) == 5

    def test_chain_summary_rendering(self):
        chain = AdmissionChain()
        chain.register(AdmissionControllerRegistration(
            name="ctrl", phase=AdmissionPhase.MUTATING, priority=100,
            controller=AllowAllController(),
        ))
        summary = chain.get_chain_summary()
        assert len(summary) == 1
        assert summary[0]["name"] == "ctrl"
        assert summary[0]["phase"] == "MUTATING"

    def test_register_duplicate_name(self):
        chain = AdmissionChain()
        chain.register(AdmissionControllerRegistration(
            name="dup", phase=AdmissionPhase.MUTATING, priority=100,
            controller=AllowAllController(),
        ))
        with pytest.raises(AdmissionChainError, match="Duplicate"):
            chain.register(AdmissionControllerRegistration(
                name="dup", phase=AdmissionPhase.VALIDATING, priority=200,
                controller=AllowAllController(),
            ))

    def test_unregister_controller(self):
        chain = AdmissionChain()
        chain.register(AdmissionControllerRegistration(
            name="removable", phase=AdmissionPhase.MUTATING, priority=100,
            controller=AllowAllController(),
        ))
        chain.unregister("removable")
        assert len(chain.get_chain_summary()) == 0


# ── 9.3 ResourceQuota Controller ────────────────────────────────

class TestResourceQuotaController:

    def _make_quota_ctrl(self):
        ctrl = ResourceQuotaAdmissionController()
        ctrl.set_quota("default", ResourceQuota(
            namespace="default",
            hard={"requests.cpu": 4.0, "requests.memory": 4294967296, "pods": 10},
        ))
        return ctrl

    def test_quota_admits_within_limits(self):
        ctrl = self._make_quota_ctrl()
        obj = _make_pod_object(containers=[{
            "name": "c1",
            "resources": {"requests": {"cpu": "500m", "memory": "256Mi"}},
        }])
        req = _make_request(obj=obj)
        resp = ctrl.admit(req)
        assert resp.allowed is True

    def test_quota_denies_exceeding_cpu(self):
        ctrl = self._make_quota_ctrl()
        obj = _make_pod_object(containers=[{
            "name": "c1",
            "resources": {"requests": {"cpu": "5000m"}},
        }])
        req = _make_request(obj=obj)
        resp = ctrl.admit(req)
        assert resp.allowed is False

    def test_quota_denies_exceeding_memory(self):
        ctrl = self._make_quota_ctrl()
        obj = _make_pod_object(containers=[{
            "name": "c1",
            "resources": {"requests": {"memory": "8Gi"}},
        }])
        req = _make_request(obj=obj)
        resp = ctrl.admit(req)
        assert resp.allowed is False

    def test_quota_denies_exceeding_pod_count(self):
        ctrl = ResourceQuotaAdmissionController()
        ctrl.set_quota("default", ResourceQuota(
            namespace="default",
            hard={"pods": 2},
            used={"pods": 2},
        ))
        req = _make_request()
        resp = ctrl.admit(req)
        assert resp.allowed is False

    def test_quota_tracks_used_on_create(self):
        ctrl = self._make_quota_ctrl()
        obj = _make_pod_object(containers=[{
            "name": "c1",
            "resources": {"requests": {"cpu": "1"}},
        }])
        ctrl.admit(_make_request(obj=obj))
        quota = ctrl.get_quota("default")
        assert quota.used["requests.cpu"] == 1.0

    def test_quota_tracks_used_on_delete(self):
        ctrl = self._make_quota_ctrl()
        obj = _make_pod_object(containers=[{
            "name": "c1",
            "resources": {"requests": {"cpu": "1"}},
        }])
        ctrl.admit(_make_request(obj=obj))
        ctrl.admit(_make_request(
            operation=AdmissionOperation.DELETE,
            old_obj=obj,
        ))
        quota = ctrl.get_quota("default")
        assert quota.used["requests.cpu"] == 0.0

    def test_quota_delta_on_update(self):
        ctrl = self._make_quota_ctrl()
        old_obj = _make_pod_object(containers=[{
            "name": "c1",
            "resources": {"requests": {"cpu": "1"}},
        }])
        new_obj = _make_pod_object(containers=[{
            "name": "c1",
            "resources": {"requests": {"cpu": "2"}},
        }])
        ctrl.admit(_make_request(obj=old_obj))
        ctrl.admit(_make_request(
            operation=AdmissionOperation.UPDATE,
            obj=new_obj,
            old_obj=old_obj,
        ))
        quota = ctrl.get_quota("default")
        assert quota.used["requests.cpu"] == 2.0

    def test_quota_scope_selector(self):
        ctrl = ResourceQuotaAdmissionController()
        ctrl.set_quota("default", ResourceQuota(
            namespace="default",
            hard={"pods": 5},
            scope_selector={"tier": "frontend"},
        ))
        obj = _make_pod_object(labels={"tier": "backend"})
        resp = ctrl.admit(_make_request(obj=obj))
        assert resp.allowed is True

    def test_quota_status_rendering(self):
        ctrl = self._make_quota_ctrl()
        output = ctrl.render_quota_status("default")
        assert "Resource Quota" in output
        assert "requests.cpu" in output

    def test_parse_cpu_millicores(self):
        assert ResourceQuotaAdmissionController._parse_resource_value("500m") == 0.5

    def test_parse_memory_fizzbytes(self):
        assert ResourceQuotaAdmissionController._parse_resource_value("256FB") == 256.0

    def test_parse_memory_gi(self):
        assert ResourceQuotaAdmissionController._parse_resource_value("1Gi") == 1073741824.0

    def test_quota_zero_used_initial(self):
        ctrl = self._make_quota_ctrl()
        quota = ctrl.get_quota("default")
        assert all(v == 0.0 for v in quota.used.values())


# ── 9.4 LimitRanger Controller ──────────────────────────────────

class TestLimitRangerController:

    def _make_lr_ctrl(self):
        ctrl = LimitRangerAdmissionController()
        ctrl.set_limit_range("default", LimitRange(
            namespace="default",
            default={"cpu": "500m", "memory": "256Mi"},
            default_request={"cpu": "200m", "memory": "128Mi"},
            min={"cpu": "100m"},
            max={"cpu": "2"},
            max_limit_request_ratio={"cpu": 5.0},
        ))
        return ctrl

    def test_default_limits_injected(self):
        ctrl = self._make_lr_ctrl()
        obj = _make_pod_object(containers=[{"name": "c1", "resources": {}}])
        req = _make_request(obj=obj)
        resp = ctrl.admit(req)
        assert resp.allowed is True
        assert resp.patch is not None
        assert any(p.path.endswith("limits") for p in resp.patch)

    def test_default_requests_injected(self):
        ctrl = self._make_lr_ctrl()
        obj = _make_pod_object(containers=[{"name": "c1", "resources": {}}])
        resp = ctrl.admit(_make_request(obj=obj))
        assert resp.allowed is True
        assert any(p.path.endswith("requests") for p in resp.patch)

    def test_both_defaults_injected(self):
        ctrl = self._make_lr_ctrl()
        obj = _make_pod_object(containers=[{"name": "c1", "resources": {}}])
        resp = ctrl.admit(_make_request(obj=obj))
        assert len(resp.patch) == 2

    def test_existing_values_preserved(self):
        ctrl = self._make_lr_ctrl()
        obj = _make_pod_object(containers=[{
            "name": "c1",
            "resources": {
                "requests": {"cpu": "300m"},
                "limits": {"cpu": "1"},
            },
        }])
        resp = ctrl.admit(_make_request(obj=obj))
        assert resp.allowed is True
        assert resp.patch is None or len(resp.patch) == 0

    def test_min_violation_denied(self):
        ctrl = self._make_lr_ctrl()
        obj = _make_pod_object(containers=[{
            "name": "c1",
            "resources": {
                "requests": {"cpu": "50m"},
                "limits": {"cpu": "100m"},
            },
        }])
        resp = ctrl.admit(_make_request(obj=obj))
        assert resp.allowed is False
        assert "below minimum" in resp.status.message

    def test_max_violation_denied(self):
        ctrl = self._make_lr_ctrl()
        obj = _make_pod_object(containers=[{
            "name": "c1",
            "resources": {
                "requests": {"cpu": "500m"},
                "limits": {"cpu": "3"},
            },
        }])
        resp = ctrl.admit(_make_request(obj=obj))
        assert resp.allowed is False
        assert "exceeds maximum" in resp.status.message

    def test_ratio_violation_denied(self):
        ctrl = self._make_lr_ctrl()
        obj = _make_pod_object(containers=[{
            "name": "c1",
            "resources": {
                "requests": {"cpu": "100m"},
                "limits": {"cpu": "1"},
            },
        }])
        resp = ctrl.admit(_make_request(obj=obj))
        assert resp.allowed is False
        assert "ratio" in resp.status.message

    def test_multiple_containers(self):
        ctrl = self._make_lr_ctrl()
        obj = _make_pod_object(containers=[
            {"name": "c1", "resources": {}},
            {"name": "c2", "resources": {}},
        ])
        resp = ctrl.admit(_make_request(obj=obj))
        assert resp.allowed is True
        assert len(resp.patch) == 4  # requests + limits for each container

    def test_no_limit_range_passthrough(self):
        ctrl = LimitRangerAdmissionController()
        resp = ctrl.admit(_make_request())
        assert resp.allowed is True

    def test_limit_range_rendering(self):
        ctrl = self._make_lr_ctrl()
        output = ctrl.render_limit_range("default")
        assert "LimitRange" in output
        assert "default" in output


# ── 9.5 PodSecurityAdmission Controller ─────────────────────────

class TestPodSecurityAdmissionController:

    def _make_psa_ctrl(self, profile=SecurityProfile.BASELINE, mode=EnforcementMode.ENFORCE):
        ctrl = PodSecurityAdmissionController()
        ctrl.set_namespace_policy("default", profile, mode)
        return ctrl

    def test_privileged_profile_allows_all(self):
        ctrl = self._make_psa_ctrl(SecurityProfile.PRIVILEGED)
        obj = _make_pod_object(host_network=True, containers=[{
            "name": "c1",
            "securityContext": {"privileged": True},
        }])
        resp = ctrl.admit(_make_request(obj=obj))
        assert resp.allowed is True

    def test_baseline_denies_privileged_container(self):
        ctrl = self._make_psa_ctrl()
        obj = _make_pod_object(containers=[{
            "name": "c1",
            "securityContext": {"privileged": True},
        }])
        resp = ctrl.admit(_make_request(obj=obj))
        assert resp.allowed is False

    def test_baseline_denies_host_network(self):
        ctrl = self._make_psa_ctrl()
        obj = _make_pod_object(host_network=True)
        resp = ctrl.admit(_make_request(obj=obj))
        assert resp.allowed is False

    def test_baseline_denies_dangerous_caps(self):
        ctrl = self._make_psa_ctrl()
        obj = _make_pod_object(containers=[{
            "name": "c1",
            "securityContext": {"capabilities": {"add": ["SYS_ADMIN"]}},
        }])
        resp = ctrl.admit(_make_request(obj=obj))
        assert resp.allowed is False

    def test_baseline_allows_safe_pod(self):
        ctrl = self._make_psa_ctrl()
        obj = _make_pod_object(containers=[{
            "name": "c1",
            "securityContext": {},
        }])
        resp = ctrl.admit(_make_request(obj=obj))
        assert resp.allowed is True

    def test_restricted_denies_root(self):
        ctrl = self._make_psa_ctrl(SecurityProfile.RESTRICTED)
        obj = _make_pod_object(containers=[{
            "name": "c1",
            "securityContext": {
                "runAsNonRoot": False,
                "readOnlyRootFilesystem": True,
                "capabilities": {"drop": ["ALL"]},
                "seccompProfile": {"type": "RuntimeDefault"},
            },
        }])
        resp = ctrl.admit(_make_request(obj=obj))
        assert resp.allowed is False

    def test_restricted_denies_writable_rootfs(self):
        ctrl = self._make_psa_ctrl(SecurityProfile.RESTRICTED)
        obj = _make_pod_object(containers=[{
            "name": "c1",
            "securityContext": {
                "runAsNonRoot": True,
                "readOnlyRootFilesystem": False,
                "capabilities": {"drop": ["ALL"]},
                "seccompProfile": {"type": "RuntimeDefault"},
            },
        }])
        resp = ctrl.admit(_make_request(obj=obj))
        assert resp.allowed is False

    def test_restricted_denies_extra_caps(self):
        ctrl = self._make_psa_ctrl(SecurityProfile.RESTRICTED)
        obj = _make_pod_object(containers=[{
            "name": "c1",
            "securityContext": {
                "runAsNonRoot": True,
                "readOnlyRootFilesystem": True,
                "capabilities": {"add": ["NET_RAW"], "drop": ["ALL"]},
                "seccompProfile": {"type": "RuntimeDefault"},
            },
        }])
        resp = ctrl.admit(_make_request(obj=obj))
        assert resp.allowed is False

    def test_restricted_requires_seccomp(self):
        ctrl = self._make_psa_ctrl(SecurityProfile.RESTRICTED)
        obj = _make_pod_object(containers=[{
            "name": "c1",
            "securityContext": {
                "runAsNonRoot": True,
                "readOnlyRootFilesystem": True,
                "capabilities": {"drop": ["ALL"]},
            },
        }])
        resp = ctrl.admit(_make_request(obj=obj))
        assert resp.allowed is False

    def test_warn_mode_admits_with_warning(self):
        ctrl = self._make_psa_ctrl(mode=EnforcementMode.WARN)
        obj = _make_pod_object(host_network=True)
        resp = ctrl.admit(_make_request(obj=obj))
        assert resp.allowed is True
        assert len(resp.warnings) > 0

    def test_audit_mode_admits_silently(self):
        ctrl = self._make_psa_ctrl(mode=EnforcementMode.AUDIT)
        obj = _make_pod_object(host_network=True)
        resp = ctrl.admit(_make_request(obj=obj))
        assert resp.allowed is True
        assert "pod-security-audit" in resp.audit_annotations

    def test_security_profile_rendering(self):
        ctrl = self._make_psa_ctrl()
        output = ctrl.render_security_profile("default")
        assert "BASELINE" in output


# ── 9.6 ImagePolicy Controller ──────────────────────────────────

class TestImagePolicyController:

    def _make_ip_ctrl(self):
        ctrl = ImagePolicyAdmissionController()
        ctrl.set_default_rules()
        return ctrl

    def test_deny_latest_tag(self):
        ctrl = self._make_ip_ctrl()
        obj = _make_pod_object(containers=[{
            "name": "c1", "image": "fizzbuzz-registry.local/app:latest",
        }])
        resp = ctrl.admit(_make_request(obj=obj))
        assert resp.allowed is False

    def test_deny_untrusted_registry(self):
        ctrl = self._make_ip_ctrl()
        obj = _make_pod_object(containers=[{
            "name": "c1", "image": "docker.io/app:v1.0",
        }])
        resp = ctrl.admit(_make_request(obj=obj))
        assert resp.allowed is False

    def test_allow_trusted_image(self):
        ctrl = ImagePolicyAdmissionController()
        ctrl.add_rule(ImagePolicyRule(
            name="allow-all", pattern=".*", action=ImagePolicyAction.ALLOW,
        ))
        obj = _make_pod_object(containers=[{
            "name": "c1", "image": "fizzbuzz-registry.local/app:v1.0",
        }])
        resp = ctrl.admit(_make_request(obj=obj))
        assert resp.allowed is True

    def test_require_signature_signed(self):
        ctrl = ImagePolicyAdmissionController()
        ctrl.add_rule(ImagePolicyRule(
            name="sig-req", pattern=".*", action=ImagePolicyAction.REQUIRE_SIGNATURE,
        ))
        ctrl.register_image_digest("myapp:v1", "sha256:abc")
        ctrl.register_signed_image("sha256:abc")
        obj = _make_pod_object(containers=[{"name": "c1", "image": "myapp:v1"}])
        resp = ctrl.admit(_make_request(namespace="production", obj=obj))
        assert resp.allowed is True

    def test_require_signature_unsigned(self):
        ctrl = ImagePolicyAdmissionController()
        ctrl.add_rule(ImagePolicyRule(
            name="sig-req", pattern=".*", action=ImagePolicyAction.REQUIRE_SIGNATURE,
        ))
        obj = _make_pod_object(containers=[{"name": "c1", "image": "myapp:v1"}])
        resp = ctrl.admit(_make_request(namespace="production", obj=obj))
        assert resp.allowed is False

    def test_tag_to_digest_resolution(self):
        ctrl = ImagePolicyAdmissionController()
        ctrl.register_image_digest("app:v1", "sha256:abc123")
        assert ctrl._image_digests["app:v1"] == "sha256:abc123"

    def test_custom_policy_rules(self):
        ctrl = ImagePolicyAdmissionController()
        ctrl.add_rule(ImagePolicyRule(
            name="deny-all", pattern=".*", action=ImagePolicyAction.DENY,
            message="no images allowed",
        ))
        obj = _make_pod_object(containers=[{"name": "c1", "image": "anything"}])
        resp = ctrl.admit(_make_request(obj=obj))
        assert resp.allowed is False

    def test_image_policy_rendering(self):
        ctrl = self._make_ip_ctrl()
        output = ctrl.render_image_policy()
        assert "Image Policy Rules" in output
        assert "deny-latest" in output


# ── 9.7 Webhook Dispatch ────────────────────────────────────────

class TestWebhookDispatch:

    def test_mutating_webhook_called(self):
        dispatcher = WebhookDispatcher()
        called = []

        def handler(review):
            called.append(True)
            return AdmissionResponse(uid=review.request.uid, allowed=True)

        dispatcher.register_mutating_webhook(MutatingWebhookConfiguration(
            name="test-webhook",
            client_config=WebhookClientConfig(),
            rules=[RuleWithOperations(
                operations=[AdmissionOperation.CREATE],
                api_groups=[""], api_versions=["v1"], resources=["pods"],
            )],
        ))
        dispatcher.register_webhook_handler("test-webhook", handler)
        responses = dispatcher.dispatch_mutating(_make_request())
        assert len(responses) == 1
        assert len(called) == 1

    def test_mutating_webhook_patches_applied(self):
        dispatcher = WebhookDispatcher()

        def handler(review):
            return AdmissionResponse(
                uid=review.request.uid,
                allowed=True,
                patch=[JsonPatchOperation(op="add", path="/metadata/labels/wh", value="true")],
            )

        dispatcher.register_mutating_webhook(MutatingWebhookConfiguration(
            name="patch-wh", client_config=WebhookClientConfig(),
            rules=[RuleWithOperations(
                operations=[AdmissionOperation.CREATE],
                api_groups=[""], api_versions=["v1"], resources=["pods"],
            )],
        ))
        dispatcher.register_webhook_handler("patch-wh", handler)
        responses = dispatcher.dispatch_mutating(_make_request())
        assert responses[0].patch is not None

    def test_validating_webhook_denies(self):
        dispatcher = WebhookDispatcher()

        def handler(review):
            return AdmissionResponse(
                uid=review.request.uid,
                allowed=False,
                status=AdmissionStatus(code=403, message="denied", reason="Denied"),
            )

        dispatcher.register_validating_webhook(ValidatingWebhookConfiguration(
            name="deny-wh", client_config=WebhookClientConfig(),
            rules=[RuleWithOperations(
                operations=[AdmissionOperation.CREATE],
                api_groups=[""], api_versions=["v1"], resources=["pods"],
            )],
        ))
        dispatcher.register_webhook_handler("deny-wh", handler)
        responses = dispatcher.dispatch_validating(_make_request())
        assert responses[0].allowed is False

    def test_webhook_timeout_fail_policy(self):
        dispatcher = WebhookDispatcher()

        def handler(review):
            time.sleep(2)
            return AdmissionResponse(uid=review.request.uid, allowed=True)

        dispatcher.register_mutating_webhook(MutatingWebhookConfiguration(
            name="slow-wh", client_config=WebhookClientConfig(),
            failure_policy=FailurePolicy.FAIL,
            timeout_seconds=0.1,
            rules=[RuleWithOperations(
                operations=[AdmissionOperation.CREATE],
                api_groups=[""], api_versions=["v1"], resources=["pods"],
            )],
        ))
        dispatcher.register_webhook_handler("slow-wh", handler)
        responses = dispatcher.dispatch_mutating(_make_request())
        assert responses[0].allowed is False

    def test_webhook_timeout_ignore_policy(self):
        dispatcher = WebhookDispatcher()

        def handler(review):
            time.sleep(2)
            return AdmissionResponse(uid=review.request.uid, allowed=True)

        dispatcher.register_mutating_webhook(MutatingWebhookConfiguration(
            name="slow-wh", client_config=WebhookClientConfig(),
            failure_policy=FailurePolicy.IGNORE,
            timeout_seconds=0.1,
            rules=[RuleWithOperations(
                operations=[AdmissionOperation.CREATE],
                api_groups=[""], api_versions=["v1"], resources=["pods"],
            )],
        ))
        dispatcher.register_webhook_handler("slow-wh", handler)
        responses = dispatcher.dispatch_mutating(_make_request())
        assert responses[0].allowed is True

    def test_namespace_selector_filtering(self):
        dispatcher = WebhookDispatcher()
        called = []

        def handler(review):
            called.append(True)
            return AdmissionResponse(uid=review.request.uid, allowed=True)

        dispatcher.register_mutating_webhook(MutatingWebhookConfiguration(
            name="filtered-wh", client_config=WebhookClientConfig(),
            namespace_selector={"env": "prod"},
            rules=[RuleWithOperations(
                operations=[AdmissionOperation.CREATE],
                api_groups=[""], api_versions=["v1"], resources=["pods"],
            )],
        ))
        dispatcher.register_webhook_handler("filtered-wh", handler)
        dispatcher.dispatch_mutating(_make_request())
        assert len(called) == 0

    def test_webhook_summary_rendering(self):
        dispatcher = WebhookDispatcher()
        dispatcher.register_mutating_webhook(MutatingWebhookConfiguration(
            name="wh1", client_config=WebhookClientConfig(),
        ))
        summary = dispatcher.get_webhook_summary()
        assert len(summary) == 1
        assert summary[0]["name"] == "wh1"


# ── 9.8 CRD Framework ───────────────────────────────────────────

class TestCRDFramework:

    def _make_crd(self, name="tests", group="test.io", kind="Test"):
        return CustomResourceDefinition(
            group=group,
            names=CRDNames(kind=kind, singular=name[:-1], plural=name),
            versions=[CRDVersion(
                name="v1", served=True, storage=True,
                schema={
                    "type": "object",
                    "properties": {
                        "metadata": {"type": "object", "properties": {
                            "name": {"type": "string"},
                            "namespace": {"type": "string"},
                        }},
                        "spec": {"type": "object", "properties": {
                            "field1": {"type": "string"},
                            "field2": {"type": "integer", "default": 42},
                        }},
                        "status": {"type": "object", "properties": {}},
                    },
                },
            )],
        )

    def test_register_crd(self):
        registry = CRDRegistry()
        crd = self._make_crd()
        registry.register_crd(crd)
        assert registry.get_crd("tests.test.io") is not None

    def test_register_crd_invalid_schema(self):
        registry = CRDRegistry()
        crd = self._make_crd()
        crd.versions[0].schema = {"properties": {"x": {}}}  # no type
        with pytest.raises(CRDSchemaValidationError):
            registry.register_crd(crd)

    def test_register_crd_multiple_storage_versions(self):
        registry = CRDRegistry()
        crd = self._make_crd()
        crd.versions.append(CRDVersion(name="v2", served=True, storage=True))
        with pytest.raises(CRDRegistrationError):
            registry.register_crd(crd)

    def test_create_instance_validates_schema(self):
        registry = CRDRegistry()
        crd = self._make_crd()
        registry.register_crd(crd)
        instance = {
            "metadata": {"name": "inst1"},
            "spec": {"field1": 123},  # should be string
        }
        with pytest.raises(CRDInstanceValidationError):
            registry.create_instance("tests.test.io", "default", instance)

    def test_create_instance_applies_defaults(self):
        registry = CRDRegistry()
        crd = self._make_crd()
        registry.register_crd(crd)
        instance = {
            "metadata": {"name": "inst1"},
            "spec": {"field1": "hello"},
        }
        result = registry.create_instance("tests.test.io", "default", instance)
        assert result["spec"]["field2"] == 42

    def test_create_instance_prunes_unknown(self):
        registry = CRDRegistry()
        crd = self._make_crd()
        registry.register_crd(crd)
        instance = {
            "metadata": {"name": "inst1"},
            "spec": {"field1": "hello", "unknown_field": "gone"},
        }
        result = registry.create_instance("tests.test.io", "default", instance)
        assert "unknown_field" not in result["spec"]

    def test_update_instance_increments_generation(self):
        registry = CRDRegistry()
        crd = self._make_crd()
        registry.register_crd(crd)
        instance = {"metadata": {"name": "inst1"}, "spec": {"field1": "v1"}}
        registry.create_instance("tests.test.io", "default", instance)
        updated = registry.update_instance(
            "tests.test.io", "default", "inst1", {"field1": "v2"},
        )
        assert updated["metadata"]["generation"] == 2

    def test_update_status_subresource(self):
        registry = CRDRegistry()
        crd = self._make_crd()
        registry.register_crd(crd)
        instance = {"metadata": {"name": "inst1"}, "spec": {"field1": "v1"}}
        registry.create_instance("tests.test.io", "default", instance)
        updated = registry.update_instance_status(
            "tests.test.io", "default", "inst1", {"phase": "Running"},
        )
        assert updated["status"]["phase"] == "Running"

    def test_delete_crd_cascades_instances(self):
        registry = CRDRegistry()
        crd = self._make_crd()
        registry.register_crd(crd)
        instance = {"metadata": {"name": "inst1"}, "spec": {"field1": "v1"}}
        registry.create_instance("tests.test.io", "default", instance)
        registry.unregister_crd("tests.test.io")
        assert registry.get_crd("tests.test.io") is None

    def test_list_instances_by_namespace(self):
        registry = CRDRegistry()
        crd = self._make_crd()
        registry.register_crd(crd)
        registry.create_instance("tests.test.io", "ns1", {
            "metadata": {"name": "a"}, "spec": {"field1": "x"},
        })
        registry.create_instance("tests.test.io", "ns2", {
            "metadata": {"name": "b"}, "spec": {"field1": "y"},
        })
        ns1_items = registry.list_instances("tests.test.io", "ns1")
        assert len(ns1_items) == 1

    def test_crd_list_rendering(self):
        registry = CRDRegistry()
        registry.register_crd(self._make_crd())
        output = registry.render_crd_list()
        assert "Custom Resource Definitions" in output
        assert "tests.test.io" in output

    def test_crd_describe_rendering(self):
        registry = CRDRegistry()
        registry.register_crd(self._make_crd())
        output = registry.render_crd_describe("tests.test.io")
        assert "test.io" in output

    def test_crd_instances_rendering(self):
        registry = CRDRegistry()
        crd = self._make_crd()
        registry.register_crd(crd)
        registry.create_instance("tests.test.io", "default", {
            "metadata": {"name": "inst1"}, "spec": {"field1": "x"},
        })
        output = registry.render_crd_instances("Test")
        assert "inst1" in output

    def test_crd_watch_notifications(self):
        registry = CRDRegistry()
        crd = self._make_crd()
        registry.register_crd(crd)
        events = []
        registry.add_watch("tests.test.io", lambda et, obj: events.append(et))
        registry.create_instance("tests.test.io", "default", {
            "metadata": {"name": "inst1"}, "spec": {"field1": "x"},
        })
        assert "ADDED" in events

    def test_openapi_validation_types(self):
        validator = OpenAPISchemaValidator()
        schema = {
            "type": "object",
            "properties": {
                "s": {"type": "string"},
                "i": {"type": "integer"},
                "n": {"type": "number"},
                "b": {"type": "boolean"},
                "a": {"type": "array", "items": {"type": "string"}},
            },
        }
        errors = validator.validate({
            "s": "hello", "i": 42, "n": 3.14, "b": True, "a": ["x"],
        }, schema)
        assert len(errors) == 0


# ── 9.9 Operator Framework ──────────────────────────────────────

class TestOperatorFramework:

    def test_operator_builder_basic(self):
        registry = CRDRegistry()

        class NoopReconciler(Reconciler):
            def reconcile(self, request):
                return ReconcileResult()

        op = (
            OperatorBuilder("test-op")
            .for_resource("test.io", "v1", "Test")
            .with_reconciler(NoopReconciler())
            .with_crd_registry(registry)
            .build()
        )
        assert op.get_status()["name"] == "test-op"

    def test_operator_builder_validates(self):
        with pytest.raises(OperatorError):
            OperatorBuilder("test-op").for_resource("g", "v", "k").build()

    def test_reconcile_success(self):
        class OkReconciler(Reconciler):
            def reconcile(self, request):
                return ReconcileResult()

        loop = ReconcileLoop(OkReconciler(), "test/v1/Test")
        loop.acquire_leadership()
        loop.enqueue("default/my-resource")
        loop.run()
        metrics = loop.get_metrics()
        assert metrics.reconcile_success == 1

    def test_reconcile_requeue(self):
        class RequeueReconciler(Reconciler):
            def __init__(self):
                self.count = 0
            def reconcile(self, request):
                self.count += 1
                if self.count < 3:
                    return ReconcileResult(requeue=True)
                return ReconcileResult()

        r = RequeueReconciler()
        loop = ReconcileLoop(r, "test/v1/Test")
        loop.acquire_leadership()
        loop.enqueue("default/my-resource")
        loop.run()
        assert r.count >= 2

    def test_reconcile_error_backoff(self):
        class ErrorReconciler(Reconciler):
            def reconcile(self, request):
                return ReconcileResult(error="test error")

        loop = ReconcileLoop(ErrorReconciler(), "test/v1/Test")
        loop.acquire_leadership()
        loop.enqueue("default/my-resource")
        loop.run()
        metrics = loop.get_metrics()
        assert metrics.reconcile_error >= 1

    def test_work_queue_deduplication(self):
        class OkReconciler(Reconciler):
            def reconcile(self, request):
                return ReconcileResult()

        loop = ReconcileLoop(OkReconciler(), "test/v1/Test")
        loop.enqueue("default/same-key")
        loop.enqueue("default/same-key")
        assert loop.get_metrics().work_queue_depth == 1

    def test_leader_election(self):
        class OkReconciler(Reconciler):
            def __init__(self):
                self.count = 0
            def reconcile(self, request):
                self.count += 1
                return ReconcileResult()

        r = OkReconciler()
        loop = ReconcileLoop(r, "test/v1/Test")
        loop.enqueue("default/key")
        loop.run()
        assert r.count == 0  # not leader

        loop.acquire_leadership()
        loop.enqueue("default/key")
        loop.run()
        assert r.count == 1

    def test_operator_metrics(self):
        class OkReconciler(Reconciler):
            def reconcile(self, request):
                return ReconcileResult()

        loop = ReconcileLoop(OkReconciler(), "test/v1/Test")
        loop.acquire_leadership()
        loop.enqueue("default/a")
        loop.enqueue("default/b")
        loop.run()
        metrics = loop.get_metrics()
        assert metrics.reconcile_total == 2
        assert len(metrics.reconcile_latency_samples) == 2

    def test_cluster_operator_reconcile(self):
        registry = CRDRegistry()
        fm = FinalizerManager()
        subsystem, _ = create_fizzadmit_subsystem()
        crd_name = "fizzbuzzclusters.fizzbuzz.io"
        instance = subsystem.crd_registry.create_instance(crd_name, "default", {
            "metadata": {"name": "test-cluster"},
            "spec": {"replicas": 3},
        })
        reconciler = FizzBuzzClusterOperator(subsystem.crd_registry, subsystem.finalizer_manager)
        result = reconciler.reconcile(ReconcileRequest(name="test-cluster", namespace="default"))
        assert result.error is None
        updated = subsystem.crd_registry.get_instance(crd_name, "default", "test-cluster")
        assert updated["status"]["phase"] == "Running"

    def test_backup_operator_reconcile(self):
        subsystem, _ = create_fizzadmit_subsystem()
        crd_name = "fizzbuzzbackups.fizzbuzz.io"
        instance = subsystem.crd_registry.create_instance(crd_name, "default", {
            "metadata": {"name": "test-backup"},
            "spec": {"schedule": "0 * * * *", "retention_count": 3},
        })
        reconciler = FizzBuzzBackupOperator(subsystem.crd_registry, subsystem.finalizer_manager)
        result = reconciler.reconcile(ReconcileRequest(name="test-backup", namespace="default"))
        assert result.error is None


# ── 9.10 Finalizers & GC ────────────────────────────────────────

class TestFinalizersAndGC:

    def test_add_finalizer(self):
        fm = FinalizerManager()
        resource = {"metadata": {}}
        fm.add_finalizer(resource, "test-finalizer")
        assert "test-finalizer" in resource["metadata"]["finalizers"]

    def test_process_finalizer_success(self):
        fm = FinalizerManager()
        handler_called = []
        fm.register_finalizer("cleanup", lambda r: handler_called.append(True))
        resource = {
            "metadata": {
                "finalizers": ["cleanup"],
                "deletion_timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }
        updated, all_cleared = fm.process_finalizers(resource)
        assert all_cleared is True
        assert len(handler_called) == 1

    def test_process_finalizer_error(self):
        fm = FinalizerManager()
        fm.register_finalizer("broken", lambda r: (_ for _ in ()).throw(RuntimeError("fail")))
        resource = {
            "metadata": {
                "finalizers": ["broken"],
                "deletion_timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }
        updated, all_cleared = fm.process_finalizers(resource)
        assert all_cleared is False
        assert "broken" in updated["metadata"]["finalizers"]

    def test_stuck_finalizer_detection(self):
        fm = FinalizerManager(stuck_timeout=0.0)
        resource = {
            "metadata": {
                "finalizers": ["stuck"],
                "deletion_timestamp": (
                    datetime.now(timezone.utc) - timedelta(seconds=10)
                ).isoformat(),
            },
        }
        assert fm.check_stuck(resource) is True

    def test_force_remove_finalizers(self):
        fm = FinalizerManager()
        resource = {"metadata": {"finalizers": ["a", "b", "c"]}}
        fm.force_remove_all(resource)
        assert resource["metadata"]["finalizers"] == []

    def test_background_cascading_deletion(self):
        registry = CRDRegistry()
        gc = GarbageCollector(registry)
        parent = {"metadata": {"uid": "parent-uid", "name": "parent"}}
        child = {"metadata": {"uid": "child-uid", "owner_references": [
            {"uid": "parent-uid", "kind": "Test", "name": "parent",
             "api_version": "v1", "controller": True, "block_owner_deletion": False},
        ]}}
        gc.delete_with_propagation(parent, PropagationPolicy.BACKGROUND)

    def test_foreground_cascading_deletion(self):
        registry = CRDRegistry()
        gc = GarbageCollector(registry)
        parent = {"metadata": {"uid": "parent-uid", "name": "parent"}}
        gc.delete_with_propagation(parent, PropagationPolicy.FOREGROUND)

    def test_orphan_deletion_policy(self):
        registry = CRDRegistry()
        gc = GarbageCollector(registry)
        parent = {"metadata": {"uid": "parent-uid", "name": "parent"}}
        gc.delete_with_propagation(parent, PropagationPolicy.ORPHAN)

    def test_multi_owner_survival(self):
        registry = CRDRegistry()
        gc = GarbageCollector(registry)
        crd = CustomResourceDefinition(
            group="test.io",
            names=CRDNames(kind="Child", singular="child", plural="children"),
            versions=[CRDVersion(name="v1", served=True, storage=True, schema={
                "type": "object",
                "properties": {
                    "metadata": {"type": "object", "properties": {
                        "name": {"type": "string"},
                        "namespace": {"type": "string"},
                    }},
                    "spec": {"type": "object", "properties": {}},
                    "status": {"type": "object", "properties": {}},
                },
            })],
        )
        registry.register_crd(crd)
        child = registry.create_instance("children.test.io", "default", {
            "metadata": {"name": "child1"},
            "spec": {},
        })
        gc.add_owner_reference(child, OwnerReference(
            api_version="v1", kind="Parent", name="p1", uid="alive-uid",
        ))
        gc.add_owner_reference(child, OwnerReference(
            api_version="v1", kind="Parent", name="p2", uid="dead-uid",
        ))
        assert not gc._is_orphaned(child)

    def test_orphan_collection(self):
        registry = CRDRegistry()
        gc = GarbageCollector(registry)
        crd = CustomResourceDefinition(
            group="test.io",
            names=CRDNames(kind="Orphan", singular="orphan", plural="orphans"),
            versions=[CRDVersion(name="v1", served=True, storage=True, schema={
                "type": "object",
                "properties": {
                    "metadata": {"type": "object", "properties": {
                        "name": {"type": "string"},
                        "namespace": {"type": "string"},
                    }},
                    "spec": {"type": "object", "properties": {}},
                    "status": {"type": "object", "properties": {}},
                },
            })],
        )
        registry.register_crd(crd)
        instance = registry.create_instance("orphans.test.io", "default", {
            "metadata": {"name": "orphan1"},
            "spec": {},
        })
        gc.add_owner_reference(instance, OwnerReference(
            api_version="v1", kind="Parent", name="gone", uid="gone-uid",
        ))
        collected = gc.collect_orphans()
        assert collected == 1


# ── Integration: Factory & Middleware ────────────────────────────

class TestFizzAdmitIntegration:

    def test_create_subsystem(self):
        subsystem, middleware = create_fizzadmit_subsystem()
        assert subsystem is not None
        assert middleware is not None
        assert len(subsystem.admission_chain.get_chain_summary()) == 4
        assert len(subsystem.crd_registry.list_crds()) == 2
        assert len(subsystem.operators) == 2

    def test_middleware_priority(self):
        _, middleware = create_fizzadmit_subsystem()
        assert middleware.priority == MIDDLEWARE_PRIORITY

    def test_middleware_dashboard_rendering(self):
        _, middleware = create_fizzadmit_subsystem()
        output = middleware.render_dashboard()
        assert "FizzAdmit Dashboard" in output
        assert FIZZADMIT_VERSION in output

    def test_middleware_admission_chain_rendering(self):
        _, middleware = create_fizzadmit_subsystem()
        output = middleware.render_admission_chain()
        assert "ResourceQuota" in output
        assert "LimitRanger" in output

    def test_middleware_operators_rendering(self):
        _, middleware = create_fizzadmit_subsystem()
        output = middleware.render_operators()
        assert "fizzbuzz-cluster-operator" in output
        assert "fizzbuzz-backup-operator" in output

    def test_middleware_webhooks_rendering(self):
        _, middleware = create_fizzadmit_subsystem()
        output = middleware.render_webhooks()
        assert "Webhook Configurations" in output

    def test_version_constant(self):
        assert FIZZADMIT_VERSION == "1.0.0"

    def test_api_versions(self):
        assert ADMISSION_API_VERSION == "admission.fizzkube.io/v1"
        assert CRD_API_VERSION == "apiextensions.fizzkube.io/v1"

    def test_enums_defined(self):
        assert AdmissionPhase.MUTATING.value == "MUTATING"
        assert FailurePolicy.FAIL.value == "FAIL"
        assert SecurityProfile.RESTRICTED.value == "RESTRICTED"
        assert PropagationPolicy.ORPHAN.value == "ORPHAN"
