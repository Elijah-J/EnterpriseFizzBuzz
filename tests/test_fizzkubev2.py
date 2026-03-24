"""
Enterprise FizzBuzz Platform - FizzKubeV2 Test Suite

Comprehensive tests for the Container-Aware Orchestrator Upgrade.
Validates image pull policies, CRI-integrated pod lifecycle, init container
sequential execution, sidecar injection policies, readiness/liveness/startup
probes, volume provisioning (emptyDir/PVC/configMap/secret), restart backoff,
graceful termination, dashboard rendering, middleware integration, factory
wiring, and all 21 exception classes.

FizzKubeV2 connects FizzKube's control plane to FizzContainerd's CRI service.
These tests ensure every phase of the CRI-backed pod lifecycle is faithfully
executed.
"""

from __future__ import annotations

import hashlib
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from fizzkubev2 import (
    KUBEV2_VERSION,
    DEFAULT_IMAGE_PULL_POLICY,
    DEFAULT_TERMINATION_GRACE_PERIOD,
    DEFAULT_RESTART_BACKOFF_BASE,
    DEFAULT_RESTART_BACKOFF_CAP,
    DEFAULT_RESTART_BACKOFF_MULTIPLIER,
    DEFAULT_PROBE_INITIAL_DELAY,
    DEFAULT_PROBE_PERIOD,
    DEFAULT_PROBE_TIMEOUT,
    DEFAULT_PROBE_SUCCESS_THRESHOLD,
    DEFAULT_PROBE_FAILURE_THRESHOLD,
    DEFAULT_MAX_INIT_CONTAINER_RETRIES,
    DEFAULT_DASHBOARD_WIDTH,
    MIDDLEWARE_PRIORITY,
    KUBEV2_POD_CREATED,
    KUBEV2_POD_SCHEDULED,
    KUBEV2_POD_RUNNING,
    KUBEV2_POD_SUCCEEDED,
    KUBEV2_POD_FAILED,
    KUBEV2_POD_TERMINATING,
    KUBEV2_IMAGE_PULL_STARTED,
    KUBEV2_IMAGE_PULLED,
    KUBEV2_IMAGE_PULL_FAILED,
    KUBEV2_IMAGE_PULL_STALLED,
    KUBEV2_INIT_STARTED,
    KUBEV2_INIT_COMPLETED,
    KUBEV2_INIT_FAILED,
    KUBEV2_SIDECAR_INJECTED,
    KUBEV2_SIDECAR_SKIPPED,
    KUBEV2_PROBE_EXECUTED,
    KUBEV2_PROBE_SUCCEEDED,
    KUBEV2_PROBE_FAILED,
    KUBEV2_READINESS_CHANGED,
    KUBEV2_LIVENESS_FAILED,
    KUBEV2_VOLUME_PROVISIONED,
    KUBEV2_VOLUME_MOUNTED,
    KUBEV2_VOLUME_CLEANED,
    KUBEV2_PVC_BOUND,
    KUBEV2_CONTAINER_STARTED,
    KUBEV2_CONTAINER_RESTARTED,
    KUBEV2_DASHBOARD_RENDERED,
    ContainerRestartPolicy,
    DEFAULT_SIDECARS,
    FizzKubeV2Middleware,
    ImagePullPolicy,
    ImagePuller,
    InjectionPolicy,
    InitContainerResult,
    InitContainerRunner,
    InitContainerSpec,
    KubeV2Dashboard,
    KubeV2Error,
    KubeV2MiddlewareError,
    KubeletV2,
    KubeletV2Error,
    KV2ImagePullError,
    ImagePullBackOffError,
    ImageNotPresentError,
    PullSecretError,
    InitContainerFailedError,
    InitContainerTimeoutError,
    SidecarInjectionError,
    SidecarLifecycleError,
    ProbeFailedError,
    ProbeTimeoutError,
    ReadinessProbeFailedError,
    LivenessProbeFailedError,
    StartupProbeFailedError,
    VolumeProvisionError,
    VolumeMountError,
    PVCNotFoundError,
    ContainerRestartBackoffError,
    PodTerminationError,
    PodPhaseV2,
    PodV2,
    PodV2Spec,
    ProbeCategory,
    ProbeConfig,
    ProbeResult,
    ProbeRunner,
    ProbeStatus,
    ProbeType,
    PullProgress,
    PullSecret,
    PVClaim,
    SidecarContainerSpec,
    SidecarInjector,
    SidecarPolicy,
    VolumeManager,
    VolumeMount,
    VolumeSpec,
    VolumeType,
    _CRIStub,
    create_fizzkubev2_subsystem,
)

from config import _SingletonMeta
from models import FizzBuzzResult, ProcessingContext


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


@pytest.fixture
def cri_stub():
    """Create a fresh CRI stub."""
    return _CRIStub()


@pytest.fixture
def image_puller(cri_stub):
    """Create an ImagePuller with a CRI stub."""
    return ImagePuller(cri_service=cri_stub)


@pytest.fixture
def init_runner(cri_stub):
    """Create an InitContainerRunner with a CRI stub."""
    return InitContainerRunner(cri_service=cri_stub)


@pytest.fixture
def sidecar_injector():
    """Create a SidecarInjector with default sidecars."""
    return SidecarInjector(default_sidecars=list(DEFAULT_SIDECARS))


@pytest.fixture
def probe_runner(cri_stub):
    """Create a ProbeRunner with a CRI stub."""
    return ProbeRunner(cri_service=cri_stub)


@pytest.fixture
def volume_manager():
    """Create a VolumeManager with default settings."""
    return VolumeManager()


@pytest.fixture
def kubelet(cri_stub, image_puller, init_runner, sidecar_injector, probe_runner, volume_manager):
    """Create a fully wired KubeletV2."""
    return KubeletV2(
        cri_service=cri_stub,
        image_puller=image_puller,
        init_runner=init_runner,
        sidecar_injector=sidecar_injector,
        probe_runner=probe_runner,
        volume_manager=volume_manager,
    )


# ============================================================
# Constants Tests
# ============================================================


class TestConstants:
    """Validate module-level constants."""

    def test_kubev2_version(self):
        assert KUBEV2_VERSION == "2.0.0"

    def test_default_image_pull_policy(self):
        assert DEFAULT_IMAGE_PULL_POLICY == "IfNotPresent"

    def test_default_termination_grace_period(self):
        assert DEFAULT_TERMINATION_GRACE_PERIOD == 30.0

    def test_default_restart_backoff_base(self):
        assert DEFAULT_RESTART_BACKOFF_BASE == 10.0

    def test_default_restart_backoff_cap(self):
        assert DEFAULT_RESTART_BACKOFF_CAP == 300.0

    def test_default_restart_backoff_multiplier(self):
        assert DEFAULT_RESTART_BACKOFF_MULTIPLIER == 2.0

    def test_default_probe_initial_delay(self):
        assert DEFAULT_PROBE_INITIAL_DELAY == 0.0

    def test_default_probe_period(self):
        assert DEFAULT_PROBE_PERIOD == 10.0

    def test_default_probe_timeout(self):
        assert DEFAULT_PROBE_TIMEOUT == 1.0

    def test_default_probe_success_threshold(self):
        assert DEFAULT_PROBE_SUCCESS_THRESHOLD == 1

    def test_default_probe_failure_threshold(self):
        assert DEFAULT_PROBE_FAILURE_THRESHOLD == 3

    def test_default_max_init_container_retries(self):
        assert DEFAULT_MAX_INIT_CONTAINER_RETRIES == 3

    def test_default_dashboard_width(self):
        assert DEFAULT_DASHBOARD_WIDTH == 72

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 116


# ============================================================
# Event Type Constants Tests
# ============================================================


class TestEventTypeConstants:
    """Validate event type string constants."""

    def test_pod_created(self):
        assert KUBEV2_POD_CREATED == "kubev2.pod.created"

    def test_pod_scheduled(self):
        assert KUBEV2_POD_SCHEDULED == "kubev2.pod.scheduled"

    def test_pod_running(self):
        assert KUBEV2_POD_RUNNING == "kubev2.pod.running"

    def test_pod_succeeded(self):
        assert KUBEV2_POD_SUCCEEDED == "kubev2.pod.succeeded"

    def test_pod_failed(self):
        assert KUBEV2_POD_FAILED == "kubev2.pod.failed"

    def test_pod_terminating(self):
        assert KUBEV2_POD_TERMINATING == "kubev2.pod.terminating"

    def test_image_pull_started(self):
        assert KUBEV2_IMAGE_PULL_STARTED == "kubev2.image.pull.started"

    def test_image_pulled(self):
        assert KUBEV2_IMAGE_PULLED == "kubev2.image.pulled"

    def test_image_pull_failed(self):
        assert KUBEV2_IMAGE_PULL_FAILED == "kubev2.image.pull.failed"

    def test_image_pull_stalled(self):
        assert KUBEV2_IMAGE_PULL_STALLED == "kubev2.image.pull.stalled"

    def test_init_started(self):
        assert KUBEV2_INIT_STARTED == "kubev2.init.started"

    def test_init_completed(self):
        assert KUBEV2_INIT_COMPLETED == "kubev2.init.completed"

    def test_init_failed(self):
        assert KUBEV2_INIT_FAILED == "kubev2.init.failed"

    def test_sidecar_injected(self):
        assert KUBEV2_SIDECAR_INJECTED == "kubev2.sidecar.injected"

    def test_sidecar_skipped(self):
        assert KUBEV2_SIDECAR_SKIPPED == "kubev2.sidecar.skipped"

    def test_probe_executed(self):
        assert KUBEV2_PROBE_EXECUTED == "kubev2.probe.executed"

    def test_probe_succeeded(self):
        assert KUBEV2_PROBE_SUCCEEDED == "kubev2.probe.succeeded"

    def test_probe_failed(self):
        assert KUBEV2_PROBE_FAILED == "kubev2.probe.failed"

    def test_readiness_changed(self):
        assert KUBEV2_READINESS_CHANGED == "kubev2.readiness.changed"

    def test_liveness_failed(self):
        assert KUBEV2_LIVENESS_FAILED == "kubev2.liveness.failed"

    def test_volume_provisioned(self):
        assert KUBEV2_VOLUME_PROVISIONED == "kubev2.volume.provisioned"

    def test_volume_mounted(self):
        assert KUBEV2_VOLUME_MOUNTED == "kubev2.volume.mounted"

    def test_volume_cleaned(self):
        assert KUBEV2_VOLUME_CLEANED == "kubev2.volume.cleaned"

    def test_pvc_bound(self):
        assert KUBEV2_PVC_BOUND == "kubev2.pvc.bound"

    def test_container_started(self):
        assert KUBEV2_CONTAINER_STARTED == "kubev2.container.started"

    def test_container_restarted(self):
        assert KUBEV2_CONTAINER_RESTARTED == "kubev2.container.restarted"

    def test_dashboard_rendered(self):
        assert KUBEV2_DASHBOARD_RENDERED == "kubev2.dashboard.rendered"


# ============================================================
# Enum Tests
# ============================================================


class TestImagePullPolicy:
    """Validate ImagePullPolicy enum."""

    def test_always(self):
        assert ImagePullPolicy.ALWAYS.value == "Always"

    def test_if_not_present(self):
        assert ImagePullPolicy.IF_NOT_PRESENT.value == "IfNotPresent"

    def test_never(self):
        assert ImagePullPolicy.NEVER.value == "Never"

    def test_from_string_always(self):
        assert ImagePullPolicy("Always") == ImagePullPolicy.ALWAYS

    def test_from_string_if_not_present(self):
        assert ImagePullPolicy("IfNotPresent") == ImagePullPolicy.IF_NOT_PRESENT

    def test_from_string_never(self):
        assert ImagePullPolicy("Never") == ImagePullPolicy.NEVER

    def test_invalid_value(self):
        with pytest.raises(ValueError):
            ImagePullPolicy("invalid")

    def test_member_count(self):
        assert len(ImagePullPolicy) == 3

    def test_all_unique(self):
        values = [p.value for p in ImagePullPolicy]
        assert len(values) == len(set(values))

    def test_is_enum(self):
        assert isinstance(ImagePullPolicy.ALWAYS, ImagePullPolicy)

    def test_name_always(self):
        assert ImagePullPolicy.ALWAYS.name == "ALWAYS"

    def test_name_if_not_present(self):
        assert ImagePullPolicy.IF_NOT_PRESENT.name == "IF_NOT_PRESENT"

    def test_name_never(self):
        assert ImagePullPolicy.NEVER.name == "NEVER"

    def test_equality(self):
        assert ImagePullPolicy.ALWAYS == ImagePullPolicy.ALWAYS

    def test_inequality(self):
        assert ImagePullPolicy.ALWAYS != ImagePullPolicy.NEVER


class TestProbeType:
    """Validate ProbeType enum."""

    def test_http_get(self):
        assert ProbeType.HTTP_GET.value == "httpGet"

    def test_tcp_socket(self):
        assert ProbeType.TCP_SOCKET.value == "tcpSocket"

    def test_exec(self):
        assert ProbeType.EXEC.value == "exec"

    def test_member_count(self):
        assert len(ProbeType) == 3

    def test_from_string(self):
        assert ProbeType("httpGet") == ProbeType.HTTP_GET

    def test_all_unique(self):
        values = [p.value for p in ProbeType]
        assert len(values) == len(set(values))

    def test_name_http_get(self):
        assert ProbeType.HTTP_GET.name == "HTTP_GET"

    def test_name_exec(self):
        assert ProbeType.EXEC.name == "EXEC"


class TestProbeResult:
    """Validate ProbeResult enum."""

    def test_success(self):
        assert ProbeResult.SUCCESS.value == "success"

    def test_failure(self):
        assert ProbeResult.FAILURE.value == "failure"

    def test_timeout(self):
        assert ProbeResult.TIMEOUT.value == "timeout"

    def test_unknown(self):
        assert ProbeResult.UNKNOWN.value == "unknown"

    def test_member_count(self):
        assert len(ProbeResult) == 4

    def test_from_string(self):
        assert ProbeResult("success") == ProbeResult.SUCCESS

    def test_all_unique(self):
        values = [p.value for p in ProbeResult]
        assert len(values) == len(set(values))

    def test_name_success(self):
        assert ProbeResult.SUCCESS.name == "SUCCESS"


class TestVolumeType:
    """Validate VolumeType enum."""

    def test_empty_dir(self):
        assert VolumeType.EMPTY_DIR.value == "emptyDir"

    def test_pvc(self):
        assert VolumeType.PERSISTENT_VOLUME_CLAIM.value == "persistentVolumeClaim"

    def test_config_map(self):
        assert VolumeType.CONFIG_MAP.value == "configMap"

    def test_secret(self):
        assert VolumeType.SECRET.value == "secret"

    def test_member_count(self):
        assert len(VolumeType) == 4

    def test_from_string(self):
        assert VolumeType("emptyDir") == VolumeType.EMPTY_DIR

    def test_all_unique(self):
        values = [v.value for v in VolumeType]
        assert len(values) == len(set(values))

    def test_name_pvc(self):
        assert VolumeType.PERSISTENT_VOLUME_CLAIM.name == "PERSISTENT_VOLUME_CLAIM"


class TestContainerRestartPolicy:
    """Validate ContainerRestartPolicy enum."""

    def test_always(self):
        assert ContainerRestartPolicy.ALWAYS.value == "Always"

    def test_on_failure(self):
        assert ContainerRestartPolicy.ON_FAILURE.value == "OnFailure"

    def test_never(self):
        assert ContainerRestartPolicy.NEVER.value == "Never"

    def test_member_count(self):
        assert len(ContainerRestartPolicy) == 3

    def test_from_string(self):
        assert ContainerRestartPolicy("Always") == ContainerRestartPolicy.ALWAYS

    def test_all_unique(self):
        values = [p.value for p in ContainerRestartPolicy]
        assert len(values) == len(set(values))

    def test_name_on_failure(self):
        assert ContainerRestartPolicy.ON_FAILURE.name == "ON_FAILURE"

    def test_equality(self):
        assert ContainerRestartPolicy.ALWAYS == ContainerRestartPolicy.ALWAYS


class TestPodPhaseV2:
    """Validate PodPhaseV2 enum."""

    def test_pending(self):
        assert PodPhaseV2.PENDING.name == "PENDING"

    def test_image_pulling(self):
        assert PodPhaseV2.IMAGE_PULLING.name == "IMAGE_PULLING"

    def test_init_running(self):
        assert PodPhaseV2.INIT_RUNNING.name == "INIT_RUNNING"

    def test_container_creating(self):
        assert PodPhaseV2.CONTAINER_CREATING.name == "CONTAINER_CREATING"

    def test_running(self):
        assert PodPhaseV2.RUNNING.name == "RUNNING"

    def test_succeeded(self):
        assert PodPhaseV2.SUCCEEDED.name == "SUCCEEDED"

    def test_failed(self):
        assert PodPhaseV2.FAILED.name == "FAILED"

    def test_terminating(self):
        assert PodPhaseV2.TERMINATING.name == "TERMINATING"

    def test_init_failure(self):
        assert PodPhaseV2.INIT_FAILURE.name == "INIT_FAILURE"

    def test_image_pull_backoff(self):
        assert PodPhaseV2.IMAGE_PULL_BACKOFF.name == "IMAGE_PULL_BACKOFF"

    def test_member_count(self):
        assert len(PodPhaseV2) == 10

    def test_all_unique(self):
        values = [p.value for p in PodPhaseV2]
        assert len(values) == len(set(values))


class TestSidecarPolicy:
    """Validate SidecarPolicy enum."""

    def test_inject(self):
        assert SidecarPolicy.INJECT.value == "inject"

    def test_skip(self):
        assert SidecarPolicy.SKIP.value == "skip"

    def test_required(self):
        assert SidecarPolicy.REQUIRED.value == "required"

    def test_member_count(self):
        assert len(SidecarPolicy) == 3

    def test_from_string(self):
        assert SidecarPolicy("inject") == SidecarPolicy.INJECT

    def test_all_unique(self):
        values = [p.value for p in SidecarPolicy]
        assert len(values) == len(set(values))


class TestProbeCategory:
    """Validate ProbeCategory enum."""

    def test_readiness(self):
        assert ProbeCategory.READINESS.value == "readiness"

    def test_liveness(self):
        assert ProbeCategory.LIVENESS.value == "liveness"

    def test_startup(self):
        assert ProbeCategory.STARTUP.value == "startup"

    def test_member_count(self):
        assert len(ProbeCategory) == 3

    def test_from_string(self):
        assert ProbeCategory("readiness") == ProbeCategory.READINESS

    def test_all_unique(self):
        values = [p.value for p in ProbeCategory]
        assert len(values) == len(set(values))


# ============================================================
# Data Class Tests
# ============================================================


class TestPullProgress:
    """Validate PullProgress data class."""

    def test_creation(self):
        p = PullProgress(image="fizzbuzz:latest")
        assert p.image == "fizzbuzz:latest"
        assert p.bytes_downloaded == 0
        assert p.bytes_total == 0

    def test_percent_zero(self):
        p = PullProgress(image="test")
        assert p.percent == 0.0

    def test_percent_full(self):
        p = PullProgress(image="test", bytes_downloaded=100, bytes_total=100)
        assert p.percent == 100.0

    def test_percent_half(self):
        p = PullProgress(image="test", bytes_downloaded=50, bytes_total=100)
        assert p.percent == 50.0

    def test_started_at_auto(self):
        p = PullProgress(image="test")
        assert p.started_at is not None
        assert isinstance(p.started_at, datetime)

    def test_completed_at_none(self):
        p = PullProgress(image="test")
        assert p.completed_at is None

    def test_stalled_default(self):
        p = PullProgress(image="test")
        assert p.stalled is False

    def test_error_default(self):
        p = PullProgress(image="test")
        assert p.error == ""

    def test_error_message(self):
        p = PullProgress(image="test", error="connection refused")
        assert p.error == "connection refused"

    def test_completed(self):
        now = datetime.now(timezone.utc)
        p = PullProgress(image="test", completed_at=now)
        assert p.completed_at == now


class TestPullSecret:
    """Validate PullSecret data class."""

    def test_creation(self):
        s = PullSecret(name="registry-creds")
        assert s.name == "registry-creds"

    def test_registry_default(self):
        s = PullSecret(name="test")
        assert s.registry == ""

    def test_username_default(self):
        s = PullSecret(name="test")
        assert s.username == ""

    def test_token_default(self):
        s = PullSecret(name="test")
        assert s.token == ""

    def test_full_creation(self):
        s = PullSecret(name="creds", registry="reg.io", username="user", token="tok")
        assert s.registry == "reg.io"
        assert s.username == "user"
        assert s.token == "tok"

    def test_name_required(self):
        s = PullSecret(name="required")
        assert s.name == "required"


class TestInitContainerSpec:
    """Validate InitContainerSpec data class."""

    def test_creation(self):
        s = InitContainerSpec(name="init-db")
        assert s.name == "init-db"

    def test_default_image(self):
        s = InitContainerSpec(name="test")
        assert s.image == "fizzbuzz-base:latest"

    def test_default_command(self):
        s = InitContainerSpec(name="test")
        assert s.command == []

    def test_default_args(self):
        s = InitContainerSpec(name="test")
        assert s.args == []

    def test_default_env(self):
        s = InitContainerSpec(name="test")
        assert s.env == {}

    def test_default_volume_mounts(self):
        s = InitContainerSpec(name="test")
        assert s.volume_mounts == []

    def test_default_timeout(self):
        s = InitContainerSpec(name="test")
        assert s.timeout_seconds == 60.0

    def test_custom_image(self):
        s = InitContainerSpec(name="test", image="custom:v1")
        assert s.image == "custom:v1"


class TestInitContainerResult:
    """Validate InitContainerResult data class."""

    def test_creation(self):
        r = InitContainerResult(name="init-db")
        assert r.name == "init-db"

    def test_default_exit_code(self):
        r = InitContainerResult(name="test")
        assert r.exit_code == -1

    def test_succeeded_true(self):
        r = InitContainerResult(name="test", exit_code=0)
        assert r.succeeded is True

    def test_succeeded_false(self):
        r = InitContainerResult(name="test", exit_code=1)
        assert r.succeeded is False

    def test_succeeded_default(self):
        r = InitContainerResult(name="test")
        assert r.succeeded is False

    def test_default_container_id(self):
        r = InitContainerResult(name="test")
        assert r.container_id == ""

    def test_default_logs(self):
        r = InitContainerResult(name="test")
        assert r.logs == ""

    def test_default_error(self):
        r = InitContainerResult(name="test")
        assert r.error == ""

    def test_duration_ms(self):
        r = InitContainerResult(name="test", duration_ms=42.5)
        assert r.duration_ms == 42.5

    def test_started_at_none(self):
        r = InitContainerResult(name="test")
        assert r.started_at is None


class TestSidecarContainerSpec:
    """Validate SidecarContainerSpec data class."""

    def test_creation(self):
        s = SidecarContainerSpec(name="proxy", image="proxy:latest")
        assert s.name == "proxy"
        assert s.image == "proxy:latest"

    def test_default_args(self):
        s = SidecarContainerSpec(name="test", image="test:v1")
        assert s.args == []

    def test_default_env(self):
        s = SidecarContainerSpec(name="test", image="test:v1")
        assert s.env == {}

    def test_default_cpu(self):
        s = SidecarContainerSpec(name="test", image="test:v1")
        assert s.resource_cpu_millifizz == 50

    def test_default_memory(self):
        s = SidecarContainerSpec(name="test", image="test:v1")
        assert s.resource_memory_fizzbytes == 64

    def test_readiness_probe_default(self):
        s = SidecarContainerSpec(name="test", image="test:v1")
        assert s.readiness_probe is None


class TestInjectionPolicy:
    """Validate InjectionPolicy data class."""

    def test_creation(self):
        p = InjectionPolicy(name="istio")
        assert p.name == "istio"

    def test_default_labels(self):
        p = InjectionPolicy(name="test")
        assert p.selector_labels == {}

    def test_default_namespaces(self):
        p = InjectionPolicy(name="test")
        assert p.selector_namespaces == []

    def test_default_containers(self):
        p = InjectionPolicy(name="test")
        assert p.containers == []

    def test_default_enabled(self):
        p = InjectionPolicy(name="test")
        assert p.enabled is True

    def test_disabled(self):
        p = InjectionPolicy(name="test", enabled=False)
        assert p.enabled is False

    def test_with_labels(self):
        p = InjectionPolicy(name="test", selector_labels={"app": "fizz"})
        assert p.selector_labels["app"] == "fizz"

    def test_with_namespaces(self):
        p = InjectionPolicy(name="test", selector_namespaces=["prod"])
        assert "prod" in p.selector_namespaces


class TestProbeConfig:
    """Validate ProbeConfig data class."""

    def test_creation(self):
        c = ProbeConfig()
        assert c.probe_type == ProbeType.EXEC

    def test_default_category(self):
        c = ProbeConfig()
        assert c.category == ProbeCategory.READINESS

    def test_default_path(self):
        c = ProbeConfig()
        assert c.path == "/healthz"

    def test_default_port(self):
        c = ProbeConfig()
        assert c.port == 8080

    def test_default_command(self):
        c = ProbeConfig()
        assert c.command == ["fizzbuzz-health"]

    def test_default_initial_delay(self):
        c = ProbeConfig()
        assert c.initial_delay_seconds == DEFAULT_PROBE_INITIAL_DELAY

    def test_default_period(self):
        c = ProbeConfig()
        assert c.period_seconds == DEFAULT_PROBE_PERIOD

    def test_default_timeout(self):
        c = ProbeConfig()
        assert c.timeout_seconds == DEFAULT_PROBE_TIMEOUT

    def test_default_success_threshold(self):
        c = ProbeConfig()
        assert c.success_threshold == DEFAULT_PROBE_SUCCESS_THRESHOLD

    def test_default_failure_threshold(self):
        c = ProbeConfig()
        assert c.failure_threshold == DEFAULT_PROBE_FAILURE_THRESHOLD


class TestProbeStatus:
    """Validate ProbeStatus data class."""

    def test_creation(self):
        s = ProbeStatus(container_id="ctr-1", category=ProbeCategory.READINESS)
        assert s.container_id == "ctr-1"

    def test_default_successes(self):
        s = ProbeStatus(container_id="ctr-1", category=ProbeCategory.READINESS)
        assert s.consecutive_successes == 0

    def test_default_failures(self):
        s = ProbeStatus(container_id="ctr-1", category=ProbeCategory.READINESS)
        assert s.consecutive_failures == 0

    def test_default_result(self):
        s = ProbeStatus(container_id="ctr-1", category=ProbeCategory.READINESS)
        assert s.last_result == ProbeResult.UNKNOWN

    def test_default_passed(self):
        s = ProbeStatus(container_id="ctr-1", category=ProbeCategory.READINESS)
        assert s.passed is False

    def test_default_message(self):
        s = ProbeStatus(container_id="ctr-1", category=ProbeCategory.READINESS)
        assert "not yet" in s.message

    def test_total_probes(self):
        s = ProbeStatus(container_id="ctr-1", category=ProbeCategory.READINESS, total_probes=5)
        assert s.total_probes == 5

    def test_last_probe_time_none(self):
        s = ProbeStatus(container_id="ctr-1", category=ProbeCategory.READINESS)
        assert s.last_probe_time is None


class TestVolumeMount:
    """Validate VolumeMount data class."""

    def test_creation(self):
        m = VolumeMount(name="data")
        assert m.name == "data"

    def test_default_mount_path(self):
        m = VolumeMount(name="data")
        assert m.mount_path == "/data"

    def test_default_read_only(self):
        m = VolumeMount(name="data")
        assert m.read_only is False

    def test_default_sub_path(self):
        m = VolumeMount(name="data")
        assert m.sub_path == ""

    def test_custom_path(self):
        m = VolumeMount(name="config", mount_path="/etc/config")
        assert m.mount_path == "/etc/config"

    def test_read_only(self):
        m = VolumeMount(name="secret", read_only=True)
        assert m.read_only is True


class TestVolumeSpec:
    """Validate VolumeSpec data class."""

    def test_creation(self):
        v = VolumeSpec(name="data")
        assert v.name == "data"

    def test_default_type(self):
        v = VolumeSpec(name="data")
        assert v.volume_type == VolumeType.EMPTY_DIR

    def test_default_size(self):
        v = VolumeSpec(name="data")
        assert v.size_bytes == 1048576

    def test_pvc_type(self):
        v = VolumeSpec(name="db", volume_type=VolumeType.PERSISTENT_VOLUME_CLAIM, claim_name="db-pvc")
        assert v.claim_name == "db-pvc"

    def test_config_map_type(self):
        v = VolumeSpec(name="cfg", volume_type=VolumeType.CONFIG_MAP, config_map_name="app-config")
        assert v.config_map_name == "app-config"

    def test_secret_type(self):
        v = VolumeSpec(name="sec", volume_type=VolumeType.SECRET, secret_name="tls-cert")
        assert v.secret_name == "tls-cert"

    def test_data_field(self):
        v = VolumeSpec(name="cfg", data={"key": "value"})
        assert v.data["key"] == "value"

    def test_medium_default(self):
        v = VolumeSpec(name="data")
        assert v.medium == ""


class TestPVClaim:
    """Validate PVClaim data class."""

    def test_creation(self):
        c = PVClaim(name="db-data")
        assert c.name == "db-data"

    def test_default_storage_class(self):
        c = PVClaim(name="test")
        assert c.storage_class == "fizz-standard"

    def test_default_requested_bytes(self):
        c = PVClaim(name="test")
        assert c.requested_bytes == 1048576

    def test_default_bound(self):
        c = PVClaim(name="test")
        assert c.bound is False

    def test_default_volume_id(self):
        c = PVClaim(name="test")
        assert c.volume_id == ""

    def test_created_at(self):
        c = PVClaim(name="test")
        assert isinstance(c.created_at, datetime)

    def test_custom_size(self):
        c = PVClaim(name="test", requested_bytes=5242880)
        assert c.requested_bytes == 5242880

    def test_custom_storage_class(self):
        c = PVClaim(name="test", storage_class="fizz-premium")
        assert c.storage_class == "fizz-premium"


class TestPodV2Spec:
    """Validate PodV2Spec data class."""

    def test_creation(self):
        s = PodV2Spec()
        assert s.image == "fizzbuzz-eval:latest"

    def test_default_pull_policy(self):
        s = PodV2Spec()
        assert s.image_pull_policy == ImagePullPolicy.IF_NOT_PRESENT

    def test_default_restart_policy(self):
        s = PodV2Spec()
        assert s.restart_policy == ContainerRestartPolicy.ALWAYS

    def test_default_namespace(self):
        s = PodV2Spec()
        assert s.namespace == "fizzbuzz-production"

    def test_default_cpu_request(self):
        s = PodV2Spec()
        assert s.cpu_request == 100

    def test_default_memory_request(self):
        s = PodV2Spec()
        assert s.memory_request == 128

    def test_custom_image(self):
        s = PodV2Spec(image="custom:v2")
        assert s.image == "custom:v2"

    def test_custom_number(self):
        s = PodV2Spec(number=42)
        assert s.number == 42

    def test_init_containers(self):
        init = InitContainerSpec(name="init-db")
        s = PodV2Spec(init_containers=[init])
        assert len(s.init_containers) == 1

    def test_default_probes_none(self):
        s = PodV2Spec()
        assert s.readiness_probe is None
        assert s.liveness_probe is None
        assert s.startup_probe is None

    def test_custom_labels(self):
        s = PodV2Spec(labels={"app": "fizz", "env": "prod"})
        assert s.labels["app"] == "fizz"

    def test_default_annotations(self):
        s = PodV2Spec()
        assert s.annotations == {}


class TestPodV2:
    """Validate PodV2 data class."""

    def test_creation(self):
        p = PodV2()
        assert p.name.startswith("fizzbuzz-v2-")

    def test_auto_name(self):
        p = PodV2()
        assert len(p.name) > 0

    def test_custom_name(self):
        p = PodV2(name="my-pod")
        assert p.name == "my-pod"

    def test_default_phase(self):
        p = PodV2()
        assert p.phase == PodPhaseV2.PENDING

    def test_default_sandbox_id(self):
        p = PodV2()
        assert p.sandbox_id == ""

    def test_default_main_container_id(self):
        p = PodV2()
        assert p.main_container_id == ""

    def test_default_sidecar_ids(self):
        p = PodV2()
        assert p.sidecar_container_ids == []

    def test_default_init_results(self):
        p = PodV2()
        assert p.init_results == []

    def test_default_volume_ids(self):
        p = PodV2()
        assert p.volume_ids == []

    def test_default_restart_counts(self):
        p = PodV2()
        assert p.restart_counts == {}

    def test_created_at(self):
        p = PodV2()
        assert isinstance(p.created_at, datetime)

    def test_default_started_at(self):
        p = PodV2()
        assert p.started_at is None

    def test_default_result(self):
        p = PodV2()
        assert p.result is None

    def test_unique_names(self):
        names = {PodV2().name for _ in range(10)}
        assert len(names) == 10

    def test_events_default(self):
        p = PodV2()
        assert p.events == []


# ============================================================
# ImagePuller Tests
# ============================================================


class TestImagePuller:
    """Validate ImagePuller image acquisition."""

    def test_creation(self, image_puller):
        assert image_puller.total_pulls == 0

    def test_pull_always(self, cri_stub):
        puller = ImagePuller(cri_service=cri_stub, default_policy=ImagePullPolicy.ALWAYS)
        progress = puller.pull("fizzbuzz:latest")
        assert progress.image == "fizzbuzz:latest"
        assert progress.completed_at is not None

    def test_pull_if_not_present_not_cached(self, image_puller):
        progress = image_puller.pull("fizzbuzz:v1")
        assert progress.completed_at is not None
        assert progress.bytes_total > 0

    def test_pull_if_not_present_cached(self, image_puller):
        image_puller.pull("fizzbuzz:v1")
        progress = image_puller.pull("fizzbuzz:v1")
        assert progress.bytes_total == 0  # cached, no download

    def test_pull_never_present(self, cri_stub):
        cri_stub.pull_image("fizzbuzz:v1")
        puller = ImagePuller(cri_service=cri_stub, default_policy=ImagePullPolicy.NEVER)
        progress = puller.pull("fizzbuzz:v1")
        assert progress.completed_at is not None

    def test_pull_never_not_present(self, cri_stub):
        puller = ImagePuller(cri_service=cri_stub, default_policy=ImagePullPolicy.NEVER)
        with pytest.raises(ImageNotPresentError):
            puller.pull("missing:latest")

    def test_pull_with_secret(self, cri_stub):
        puller = ImagePuller(cri_service=cri_stub, default_policy=ImagePullPolicy.ALWAYS)
        secret = PullSecret(name="creds", registry="docker.io")
        progress = puller.pull("docker.io/fizzbuzz:v1", pull_secrets=[secret])
        assert progress.completed_at is not None

    def test_pull_with_wrong_secret(self, cri_stub):
        puller = ImagePuller(cri_service=cri_stub, default_policy=ImagePullPolicy.ALWAYS)
        secret = PullSecret(name="creds", registry="other.io")
        with pytest.raises(PullSecretError):
            puller.pull("docker.io/fizzbuzz:v1", pull_secrets=[secret])

    def test_is_present_false(self, image_puller):
        assert image_puller.is_present("nonexistent:latest") is False

    def test_is_present_true(self, image_puller):
        image_puller.pull("fizzbuzz:v1")
        assert image_puller.is_present("fizzbuzz:v1") is True

    def test_total_pulls(self, image_puller):
        image_puller.pull("img1:v1")
        image_puller.pull("img2:v1")
        assert image_puller.total_pulls == 2

    def test_failed_pulls_initial(self, image_puller):
        assert image_puller.failed_pulls == 0

    def test_failed_pulls_after_error(self, cri_stub):
        puller = ImagePuller(cri_service=cri_stub, default_policy=ImagePullPolicy.NEVER)
        try:
            puller.pull("missing:latest")
        except ImageNotPresentError:
            pass
        assert puller.failed_pulls == 1

    def test_pull_history(self, image_puller):
        image_puller.pull("fizzbuzz:v1")
        assert len(image_puller.pull_history) == 1

    def test_pull_history_multiple(self, image_puller):
        image_puller.pull("a:v1")
        image_puller.pull("b:v1")
        image_puller.pull("c:v1")
        assert len(image_puller.pull_history) == 3

    def test_pull_override_policy(self, image_puller):
        progress = image_puller.pull("fizzbuzz:v1", policy=ImagePullPolicy.ALWAYS)
        assert progress.bytes_total > 0

    def test_pull_secret_no_registry(self, cri_stub):
        puller = ImagePuller(cri_service=cri_stub, default_policy=ImagePullPolicy.ALWAYS)
        secret = PullSecret(name="wildcard")
        progress = puller.pull("fizzbuzz:v1", pull_secrets=[secret])
        assert progress.completed_at is not None

    def test_pull_always_re_pulls(self, cri_stub):
        puller = ImagePuller(cri_service=cri_stub, default_policy=ImagePullPolicy.ALWAYS)
        p1 = puller.pull("fizzbuzz:v1")
        p2 = puller.pull("fizzbuzz:v1")
        assert puller.total_pulls == 2

    def test_pull_with_event_bus(self, cri_stub):
        bus = MagicMock()
        puller = ImagePuller(cri_service=cri_stub, event_bus=bus)
        puller.pull("fizzbuzz:v1")
        assert bus.publish.called

    def test_percent_in_progress(self):
        p = PullProgress(image="test", bytes_downloaded=250, bytes_total=1000)
        assert p.percent == 25.0

    def test_detect_stall_completed(self, image_puller):
        p = PullProgress(image="test", completed_at=datetime.now(timezone.utc))
        assert image_puller._detect_stall(p) is False

    def test_pull_multiple_unique(self, image_puller):
        for i in range(5):
            image_puller.pull(f"img-{i}:v1")
        assert image_puller.total_pulls == 5

    def test_pull_progress_no_error(self, image_puller):
        progress = image_puller.pull("fizzbuzz:v1")
        assert progress.error == ""

    def test_pull_progress_percent_100(self, image_puller):
        progress = image_puller.pull("fizzbuzz:v1")
        assert progress.percent == 100.0

    def test_pull_history_immutable(self, image_puller):
        image_puller.pull("fizzbuzz:v1")
        h1 = image_puller.pull_history
        h2 = image_puller.pull_history
        assert h1 is not h2

    def test_stall_threshold_param(self, cri_stub):
        puller = ImagePuller(cri_service=cri_stub, stall_threshold=0.001)
        assert puller._stall_threshold == 0.001

    def test_pull_timeout_param(self, cri_stub):
        puller = ImagePuller(cri_service=cri_stub, pull_timeout=60.0)
        assert puller._pull_timeout == 60.0


# ============================================================
# InitContainerRunner Tests
# ============================================================


class TestInitContainerRunner:
    """Validate InitContainerRunner sequential execution."""

    def test_creation(self, init_runner):
        assert init_runner.total_runs == 0

    def test_run_all_empty(self, init_runner, cri_stub):
        sandbox_id = cri_stub.run_pod_sandbox()
        results = init_runner.run_all(sandbox_id, [])
        assert results == []

    def test_run_single_init(self, init_runner, cri_stub):
        sandbox_id = cri_stub.run_pod_sandbox()
        specs = [InitContainerSpec(name="init-db")]
        results = init_runner.run_all(sandbox_id, specs)
        assert len(results) == 1
        assert results[0].succeeded

    def test_run_multiple_inits(self, init_runner, cri_stub):
        sandbox_id = cri_stub.run_pod_sandbox()
        specs = [
            InitContainerSpec(name="init-1"),
            InitContainerSpec(name="init-2"),
            InitContainerSpec(name="init-3"),
        ]
        results = init_runner.run_all(sandbox_id, specs)
        assert len(results) == 3
        assert all(r.succeeded for r in results)

    def test_run_records_history(self, init_runner, cri_stub):
        sandbox_id = cri_stub.run_pod_sandbox()
        specs = [InitContainerSpec(name="init-1")]
        init_runner.run_all(sandbox_id, specs)
        assert init_runner.total_runs == 1

    def test_run_history_immutable(self, init_runner, cri_stub):
        sandbox_id = cri_stub.run_pod_sandbox()
        specs = [InitContainerSpec(name="init-1")]
        init_runner.run_all(sandbox_id, specs)
        h1 = init_runner.run_history
        h2 = init_runner.run_history
        assert h1 is not h2

    def test_run_result_has_container_id(self, init_runner, cri_stub):
        sandbox_id = cri_stub.run_pod_sandbox()
        specs = [InitContainerSpec(name="init-1")]
        results = init_runner.run_all(sandbox_id, specs)
        assert results[0].container_id != ""

    def test_run_result_has_duration(self, init_runner, cri_stub):
        sandbox_id = cri_stub.run_pod_sandbox()
        specs = [InitContainerSpec(name="init-1")]
        results = init_runner.run_all(sandbox_id, specs)
        assert results[0].duration_ms >= 0

    def test_run_result_exit_code_zero(self, init_runner, cri_stub):
        sandbox_id = cri_stub.run_pod_sandbox()
        specs = [InitContainerSpec(name="init-1")]
        results = init_runner.run_all(sandbox_id, specs)
        assert results[0].exit_code == 0

    def test_total_failures_initial(self, init_runner):
        assert init_runner.total_failures == 0

    def test_run_with_env(self, init_runner, cri_stub):
        sandbox_id = cri_stub.run_pod_sandbox()
        specs = [InitContainerSpec(name="init-1", env={"DB_HOST": "localhost"})]
        results = init_runner.run_all(sandbox_id, specs)
        assert results[0].succeeded

    def test_run_with_command(self, init_runner, cri_stub):
        sandbox_id = cri_stub.run_pod_sandbox()
        specs = [InitContainerSpec(name="init-1", command=["migrate"])]
        results = init_runner.run_all(sandbox_id, specs)
        assert results[0].succeeded

    def test_run_with_event_bus(self, cri_stub):
        bus = MagicMock()
        runner = InitContainerRunner(cri_service=cri_stub, event_bus=bus)
        sandbox_id = cri_stub.run_pod_sandbox()
        specs = [InitContainerSpec(name="init-1")]
        runner.run_all(sandbox_id, specs)
        assert bus.publish.called

    def test_run_sequential_order(self, init_runner, cri_stub):
        sandbox_id = cri_stub.run_pod_sandbox()
        names = ["alpha", "beta", "gamma"]
        specs = [InitContainerSpec(name=n) for n in names]
        results = init_runner.run_all(sandbox_id, specs)
        assert [r.name for r in results] == names

    def test_run_custom_timeout(self, init_runner, cri_stub):
        sandbox_id = cri_stub.run_pod_sandbox()
        specs = [InitContainerSpec(name="init-1", timeout_seconds=120.0)]
        results = init_runner.run_all(sandbox_id, specs)
        assert results[0].succeeded

    def test_run_started_at_set(self, init_runner, cri_stub):
        sandbox_id = cri_stub.run_pod_sandbox()
        specs = [InitContainerSpec(name="init-1")]
        results = init_runner.run_all(sandbox_id, specs)
        assert results[0].started_at is not None

    def test_run_completed_at_set(self, init_runner, cri_stub):
        sandbox_id = cri_stub.run_pod_sandbox()
        specs = [InitContainerSpec(name="init-1")]
        results = init_runner.run_all(sandbox_id, specs)
        assert results[0].completed_at is not None

    def test_max_retries_param(self, cri_stub):
        runner = InitContainerRunner(cri_service=cri_stub, max_retries=5)
        assert runner._max_retries == 5

    def test_run_five_inits(self, init_runner, cri_stub):
        sandbox_id = cri_stub.run_pod_sandbox()
        specs = [InitContainerSpec(name=f"init-{i}") for i in range(5)]
        results = init_runner.run_all(sandbox_id, specs)
        assert len(results) == 5
        assert init_runner.total_runs == 5

    def test_restart_policy_never(self, init_runner, cri_stub):
        sandbox_id = cri_stub.run_pod_sandbox()
        specs = [InitContainerSpec(name="init-1")]
        results = init_runner.run_all(
            sandbox_id, specs, restart_policy=ContainerRestartPolicy.NEVER
        )
        assert results[0].succeeded

    def test_run_result_name_matches_spec(self, init_runner, cri_stub):
        sandbox_id = cri_stub.run_pod_sandbox()
        specs = [InitContainerSpec(name="my-init")]
        results = init_runner.run_all(sandbox_id, specs)
        assert results[0].name == "my-init"

    def test_run_custom_image(self, init_runner, cri_stub):
        sandbox_id = cri_stub.run_pod_sandbox()
        specs = [InitContainerSpec(name="init-1", image="custom-init:v3")]
        results = init_runner.run_all(sandbox_id, specs)
        assert results[0].succeeded

    def test_run_all_returns_list(self, init_runner, cri_stub):
        sandbox_id = cri_stub.run_pod_sandbox()
        specs = [InitContainerSpec(name="init-1")]
        results = init_runner.run_all(sandbox_id, specs)
        assert isinstance(results, list)


# ============================================================
# SidecarInjector Tests
# ============================================================


class TestSidecarInjector:
    """Validate SidecarInjector injection policies."""

    def test_creation(self, sidecar_injector):
        assert sidecar_injector.total_injections == 0

    def test_inject_defaults(self, sidecar_injector):
        spec = PodV2Spec()
        sidecars, volumes, inits = sidecar_injector.inject(spec)
        assert len(sidecars) == 4  # 4 default sidecars

    def test_inject_skip_annotation(self):
        injector = SidecarInjector(default_sidecars=list(DEFAULT_SIDECARS))
        spec = PodV2Spec(
            sidecar_annotations={"fizzbuzz.io/inject-sidecars": "false"}
        )
        sidecars, volumes, inits = injector.inject(spec)
        assert len(sidecars) == 0

    def test_inject_skip_via_annotations(self):
        injector = SidecarInjector(default_sidecars=list(DEFAULT_SIDECARS))
        spec = PodV2Spec(
            annotations={"fizzbuzz.io/inject-sidecars": "false"}
        )
        sidecars, volumes, inits = injector.inject(spec)
        assert len(sidecars) == 0

    def test_inject_no_defaults(self):
        injector = SidecarInjector(default_sidecars=[])
        spec = PodV2Spec()
        sidecars, volumes, inits = injector.inject(spec)
        assert len(sidecars) == 0

    def test_inject_with_policy_matching_labels(self):
        policy = InjectionPolicy(
            name="test-policy",
            selector_labels={"app": "fizzbuzz"},
            containers=[
                SidecarContainerSpec(name="custom-sidecar", image="custom:v1")
            ],
        )
        injector = SidecarInjector(
            policies=[policy], default_sidecars=[]
        )
        spec = PodV2Spec(labels={"app": "fizzbuzz"})
        sidecars, _, _ = injector.inject(spec)
        assert len(sidecars) == 1
        assert sidecars[0].name == "custom-sidecar"

    def test_inject_with_policy_not_matching(self):
        policy = InjectionPolicy(
            name="test-policy",
            selector_labels={"app": "other"},
            containers=[
                SidecarContainerSpec(name="custom-sidecar", image="custom:v1")
            ],
        )
        injector = SidecarInjector(
            policies=[policy], default_sidecars=[]
        )
        spec = PodV2Spec(labels={"app": "fizzbuzz"})
        sidecars, _, _ = injector.inject(spec)
        assert len(sidecars) == 0

    def test_inject_with_namespace_selector(self):
        policy = InjectionPolicy(
            name="prod-policy",
            selector_namespaces=["fizzbuzz-production"],
            containers=[
                SidecarContainerSpec(name="prod-sidecar", image="prod:v1")
            ],
        )
        injector = SidecarInjector(
            policies=[policy], default_sidecars=[]
        )
        spec = PodV2Spec(namespace="fizzbuzz-production")
        sidecars, _, _ = injector.inject(spec)
        assert len(sidecars) == 1

    def test_inject_namespace_not_matching(self):
        policy = InjectionPolicy(
            name="prod-policy",
            selector_namespaces=["fizzbuzz-staging"],
            containers=[
                SidecarContainerSpec(name="prod-sidecar", image="prod:v1")
            ],
        )
        injector = SidecarInjector(
            policies=[policy], default_sidecars=[]
        )
        spec = PodV2Spec(namespace="fizzbuzz-production")
        sidecars, _, _ = injector.inject(spec)
        assert len(sidecars) == 0

    def test_inject_disabled_policy(self):
        policy = InjectionPolicy(
            name="disabled",
            enabled=False,
            containers=[
                SidecarContainerSpec(name="disabled-sidecar", image="x:v1")
            ],
        )
        injector = SidecarInjector(
            policies=[policy], default_sidecars=[]
        )
        spec = PodV2Spec()
        sidecars, _, _ = injector.inject(spec)
        assert len(sidecars) == 0

    def test_inject_required_no_sidecars(self):
        injector = SidecarInjector(default_sidecars=[])
        spec = PodV2Spec(
            sidecar_annotations={"fizzbuzz.io/inject-sidecars": "required"}
        )
        with pytest.raises(SidecarInjectionError):
            injector.inject(spec)

    def test_inject_required_with_sidecars(self, sidecar_injector):
        spec = PodV2Spec(
            sidecar_annotations={"fizzbuzz.io/inject-sidecars": "required"}
        )
        sidecars, _, _ = sidecar_injector.inject(spec)
        assert len(sidecars) == 4

    def test_add_policy(self):
        injector = SidecarInjector(default_sidecars=[])
        policy = InjectionPolicy(name="new-policy")
        injector.add_policy(policy)
        assert len(injector.active_policies) == 1

    def test_remove_policy(self):
        policy = InjectionPolicy(name="to-remove")
        injector = SidecarInjector(
            policies=[policy], default_sidecars=[]
        )
        injector.remove_policy("to-remove")
        assert len(injector.active_policies) == 0

    def test_total_injections_increments(self, sidecar_injector):
        spec = PodV2Spec()
        sidecar_injector.inject(spec)
        sidecar_injector.inject(spec)
        assert sidecar_injector.total_injections == 2

    def test_injection_history(self, sidecar_injector):
        spec = PodV2Spec()
        sidecar_injector.inject(spec)
        assert len(sidecar_injector.injection_history) == 1

    def test_injection_history_skip(self):
        injector = SidecarInjector(default_sidecars=[])
        spec = PodV2Spec(
            sidecar_annotations={"fizzbuzz.io/inject-sidecars": "false"}
        )
        injector.inject(spec)
        assert len(injector.injection_history) == 1
        assert injector.injection_history[0]["policy"] == "skip"

    def test_inject_with_event_bus(self):
        bus = MagicMock()
        injector = SidecarInjector(
            default_sidecars=list(DEFAULT_SIDECARS), event_bus=bus
        )
        spec = PodV2Spec()
        injector.inject(spec)
        assert bus.publish.called

    def test_inject_policy_with_init_containers(self):
        init = InitContainerSpec(name="sidecar-init")
        policy = InjectionPolicy(
            name="with-init",
            init_containers=[init],
            containers=[
                SidecarContainerSpec(name="sc", image="sc:v1")
            ],
        )
        injector = SidecarInjector(
            policies=[policy], default_sidecars=[]
        )
        spec = PodV2Spec()
        sidecars, volumes, inits = injector.inject(spec)
        assert len(inits) == 1
        assert inits[0].name == "sidecar-init"

    def test_inject_policy_with_volumes(self):
        vm = VolumeMount(name="shared-data")
        policy = InjectionPolicy(
            name="with-vol",
            volumes=[vm],
            containers=[
                SidecarContainerSpec(name="sc", image="sc:v1")
            ],
        )
        injector = SidecarInjector(
            policies=[policy], default_sidecars=[]
        )
        spec = PodV2Spec()
        sidecars, volumes, inits = injector.inject(spec)
        assert len(volumes) == 1

    def test_inject_multiple_policies(self):
        p1 = InjectionPolicy(
            name="p1",
            containers=[SidecarContainerSpec(name="sc1", image="sc1:v1")],
        )
        p2 = InjectionPolicy(
            name="p2",
            containers=[SidecarContainerSpec(name="sc2", image="sc2:v1")],
        )
        injector = SidecarInjector(
            policies=[p1, p2], default_sidecars=[]
        )
        spec = PodV2Spec()
        sidecars, _, _ = injector.inject(spec)
        assert len(sidecars) == 2

    def test_default_sidecars_names(self, sidecar_injector):
        spec = PodV2Spec()
        sidecars, _, _ = sidecar_injector.inject(spec)
        names = [s.name for s in sidecars]
        assert "fizzbuzz-sidecar-log" in names
        assert "fizzbuzz-sidecar-metrics" in names
        assert "fizzbuzz-sidecar-trace" in names
        assert "fizzbuzz-sidecar-proxy" in names

    def test_active_policies(self):
        p1 = InjectionPolicy(name="active", enabled=True)
        p2 = InjectionPolicy(name="inactive", enabled=False)
        injector = SidecarInjector(
            policies=[p1, p2], default_sidecars=[]
        )
        assert len(injector.active_policies) == 1

    def test_injection_history_immutable(self, sidecar_injector):
        spec = PodV2Spec()
        sidecar_injector.inject(spec)
        h1 = sidecar_injector.injection_history
        h2 = sidecar_injector.injection_history
        assert h1 is not h2


# ============================================================
# ProbeRunner Tests
# ============================================================


class TestProbeRunner:
    """Validate ProbeRunner health probe execution."""

    def test_creation(self, probe_runner):
        assert probe_runner.total_probes_executed == 0

    def test_register_probe(self, probe_runner):
        config = ProbeConfig(category=ProbeCategory.READINESS)
        probe_runner.register_probe("ctr-1", config)
        status = probe_runner.evaluate_status("ctr-1", ProbeCategory.READINESS)
        assert status.container_id == "ctr-1"

    def test_execute_http_probe(self, probe_runner, cri_stub):
        sandbox_id = cri_stub.run_pod_sandbox()
        cid = cri_stub.create_container(sandbox_id, "test:v1")
        cri_stub.start_container(cid)
        config = ProbeConfig(
            probe_type=ProbeType.HTTP_GET,
            category=ProbeCategory.READINESS,
        )
        probe_runner.register_probe(cid, config)
        result = probe_runner.execute_probe(cid, ProbeCategory.READINESS)
        assert result == ProbeResult.SUCCESS

    def test_execute_tcp_probe(self, probe_runner, cri_stub):
        sandbox_id = cri_stub.run_pod_sandbox()
        cid = cri_stub.create_container(sandbox_id, "test:v1")
        cri_stub.start_container(cid)
        config = ProbeConfig(
            probe_type=ProbeType.TCP_SOCKET,
            category=ProbeCategory.READINESS,
        )
        probe_runner.register_probe(cid, config)
        result = probe_runner.execute_probe(cid, ProbeCategory.READINESS)
        assert result == ProbeResult.SUCCESS

    def test_execute_exec_probe(self, probe_runner, cri_stub):
        sandbox_id = cri_stub.run_pod_sandbox()
        cid = cri_stub.create_container(sandbox_id, "test:v1")
        cri_stub.start_container(cid)
        config = ProbeConfig(
            probe_type=ProbeType.EXEC,
            category=ProbeCategory.READINESS,
        )
        probe_runner.register_probe(cid, config)
        result = probe_runner.execute_probe(cid, ProbeCategory.READINESS)
        assert result == ProbeResult.SUCCESS

    def test_probe_failure_stopped_container(self, probe_runner, cri_stub):
        sandbox_id = cri_stub.run_pod_sandbox()
        cid = cri_stub.create_container(sandbox_id, "test:v1")
        cri_stub.start_container(cid)
        cri_stub.stop_container(cid)
        config = ProbeConfig(
            probe_type=ProbeType.HTTP_GET,
            category=ProbeCategory.READINESS,
        )
        probe_runner.register_probe(cid, config)
        result = probe_runner.execute_probe(cid, ProbeCategory.READINESS)
        assert result == ProbeResult.FAILURE

    def test_execute_all(self, probe_runner, cri_stub):
        sandbox_id = cri_stub.run_pod_sandbox()
        cid = cri_stub.create_container(sandbox_id, "test:v1")
        cri_stub.start_container(cid)
        probe_runner.register_probe(
            cid, ProbeConfig(category=ProbeCategory.READINESS)
        )
        probe_runner.register_probe(
            cid, ProbeConfig(category=ProbeCategory.LIVENESS)
        )
        results = probe_runner.execute_all(cid)
        assert ProbeCategory.READINESS in results
        assert ProbeCategory.LIVENESS in results

    def test_is_ready(self, probe_runner, cri_stub):
        sandbox_id = cri_stub.run_pod_sandbox()
        cid = cri_stub.create_container(sandbox_id, "test:v1")
        cri_stub.start_container(cid)
        config = ProbeConfig(category=ProbeCategory.READINESS)
        probe_runner.register_probe(cid, config)
        probe_runner.execute_probe(cid, ProbeCategory.READINESS)
        assert probe_runner.is_ready(cid) is True

    def test_is_alive(self, probe_runner, cri_stub):
        sandbox_id = cri_stub.run_pod_sandbox()
        cid = cri_stub.create_container(sandbox_id, "test:v1")
        cri_stub.start_container(cid)
        config = ProbeConfig(category=ProbeCategory.LIVENESS)
        probe_runner.register_probe(cid, config)
        probe_runner.execute_probe(cid, ProbeCategory.LIVENESS)
        assert probe_runner.is_alive(cid) is True

    def test_has_started(self, probe_runner, cri_stub):
        sandbox_id = cri_stub.run_pod_sandbox()
        cid = cri_stub.create_container(sandbox_id, "test:v1")
        cri_stub.start_container(cid)
        config = ProbeConfig(category=ProbeCategory.STARTUP)
        probe_runner.register_probe(cid, config)
        probe_runner.execute_probe(cid, ProbeCategory.STARTUP)
        assert probe_runner.has_started(cid) is True

    def test_is_ready_no_probe(self, probe_runner):
        assert probe_runner.is_ready("nonexistent") is False

    def test_clear(self, probe_runner, cri_stub):
        sandbox_id = cri_stub.run_pod_sandbox()
        cid = cri_stub.create_container(sandbox_id, "test:v1")
        config = ProbeConfig(category=ProbeCategory.READINESS)
        probe_runner.register_probe(cid, config)
        probe_runner.clear(cid)
        assert probe_runner.is_ready(cid) is False

    def test_probe_statuses_empty(self, probe_runner):
        assert probe_runner.probe_statuses == {}

    def test_probe_statuses_with_probes(self, probe_runner, cri_stub):
        sandbox_id = cri_stub.run_pod_sandbox()
        cid = cri_stub.create_container(sandbox_id, "test:v1")
        config = ProbeConfig(category=ProbeCategory.READINESS)
        probe_runner.register_probe(cid, config)
        statuses = probe_runner.probe_statuses
        assert cid in statuses

    def test_total_probes_executed(self, probe_runner, cri_stub):
        sandbox_id = cri_stub.run_pod_sandbox()
        cid = cri_stub.create_container(sandbox_id, "test:v1")
        cri_stub.start_container(cid)
        config = ProbeConfig(category=ProbeCategory.READINESS)
        probe_runner.register_probe(cid, config)
        probe_runner.execute_probe(cid, ProbeCategory.READINESS)
        probe_runner.execute_probe(cid, ProbeCategory.READINESS)
        assert probe_runner.total_probes_executed == 2

    def test_consecutive_successes(self, probe_runner, cri_stub):
        sandbox_id = cri_stub.run_pod_sandbox()
        cid = cri_stub.create_container(sandbox_id, "test:v1")
        cri_stub.start_container(cid)
        config = ProbeConfig(category=ProbeCategory.READINESS)
        probe_runner.register_probe(cid, config)
        probe_runner.execute_probe(cid, ProbeCategory.READINESS)
        probe_runner.execute_probe(cid, ProbeCategory.READINESS)
        status = probe_runner.evaluate_status(cid, ProbeCategory.READINESS)
        assert status.consecutive_successes == 2

    def test_consecutive_failures(self, probe_runner, cri_stub):
        sandbox_id = cri_stub.run_pod_sandbox()
        cid = cri_stub.create_container(sandbox_id, "test:v1")
        # Don't start container -> probes will fail
        config = ProbeConfig(
            probe_type=ProbeType.HTTP_GET,
            category=ProbeCategory.READINESS,
        )
        probe_runner.register_probe(cid, config)
        probe_runner.execute_probe(cid, ProbeCategory.READINESS)
        probe_runner.execute_probe(cid, ProbeCategory.READINESS)
        status = probe_runner.evaluate_status(cid, ProbeCategory.READINESS)
        assert status.consecutive_failures == 2

    def test_probe_threshold_evaluation(self, probe_runner, cri_stub):
        sandbox_id = cri_stub.run_pod_sandbox()
        cid = cri_stub.create_container(sandbox_id, "test:v1")
        config = ProbeConfig(
            probe_type=ProbeType.HTTP_GET,
            category=ProbeCategory.READINESS,
            failure_threshold=2,
        )
        probe_runner.register_probe(cid, config)
        probe_runner.execute_probe(cid, ProbeCategory.READINESS)
        probe_runner.execute_probe(cid, ProbeCategory.READINESS)
        status = probe_runner.evaluate_status(cid, ProbeCategory.READINESS)
        assert status.passed is False

    def test_execute_unknown_probe(self, probe_runner):
        result = probe_runner.execute_probe("nonexistent", ProbeCategory.READINESS)
        assert result == ProbeResult.UNKNOWN

    def test_evaluate_status_no_probe(self, probe_runner):
        status = probe_runner.evaluate_status("nonexistent", ProbeCategory.READINESS)
        assert "No probe" in status.message

    def test_probe_with_event_bus(self, cri_stub):
        bus = MagicMock()
        runner = ProbeRunner(cri_service=cri_stub, event_bus=bus)
        sandbox_id = cri_stub.run_pod_sandbox()
        cid = cri_stub.create_container(sandbox_id, "test:v1")
        cri_stub.start_container(cid)
        config = ProbeConfig(category=ProbeCategory.READINESS)
        runner.register_probe(cid, config)
        runner.execute_probe(cid, ProbeCategory.READINESS)
        assert bus.publish.called

    def test_success_resets_failures(self, probe_runner, cri_stub):
        sandbox_id = cri_stub.run_pod_sandbox()
        cid = cri_stub.create_container(sandbox_id, "test:v1")
        config = ProbeConfig(
            probe_type=ProbeType.HTTP_GET,
            category=ProbeCategory.READINESS,
        )
        probe_runner.register_probe(cid, config)
        # Fail once (container not started)
        probe_runner.execute_probe(cid, ProbeCategory.READINESS)
        # Start container -> success
        cri_stub.start_container(cid)
        probe_runner.execute_probe(cid, ProbeCategory.READINESS)
        status = probe_runner.evaluate_status(cid, ProbeCategory.READINESS)
        assert status.consecutive_failures == 0
        assert status.consecutive_successes == 1

    def test_probe_last_result(self, probe_runner, cri_stub):
        sandbox_id = cri_stub.run_pod_sandbox()
        cid = cri_stub.create_container(sandbox_id, "test:v1")
        cri_stub.start_container(cid)
        config = ProbeConfig(category=ProbeCategory.READINESS)
        probe_runner.register_probe(cid, config)
        probe_runner.execute_probe(cid, ProbeCategory.READINESS)
        status = probe_runner.evaluate_status(cid, ProbeCategory.READINESS)
        assert status.last_result == ProbeResult.SUCCESS

    def test_probe_total_count(self, probe_runner, cri_stub):
        sandbox_id = cri_stub.run_pod_sandbox()
        cid = cri_stub.create_container(sandbox_id, "test:v1")
        cri_stub.start_container(cid)
        config = ProbeConfig(category=ProbeCategory.READINESS)
        probe_runner.register_probe(cid, config)
        for _ in range(5):
            probe_runner.execute_probe(cid, ProbeCategory.READINESS)
        status = probe_runner.evaluate_status(cid, ProbeCategory.READINESS)
        assert status.total_probes == 5

    def test_multiple_probe_categories(self, probe_runner, cri_stub):
        sandbox_id = cri_stub.run_pod_sandbox()
        cid = cri_stub.create_container(sandbox_id, "test:v1")
        cri_stub.start_container(cid)
        for cat in ProbeCategory:
            config = ProbeConfig(category=cat)
            probe_runner.register_probe(cid, config)
        results = probe_runner.execute_all(cid)
        assert len(results) == 3

    def test_probe_statuses_copy(self, probe_runner, cri_stub):
        sandbox_id = cri_stub.run_pod_sandbox()
        cid = cri_stub.create_container(sandbox_id, "test:v1")
        config = ProbeConfig(category=ProbeCategory.READINESS)
        probe_runner.register_probe(cid, config)
        s1 = probe_runner.probe_statuses
        s2 = probe_runner.probe_statuses
        assert s1 is not s2

    def test_last_probe_time(self, probe_runner, cri_stub):
        sandbox_id = cri_stub.run_pod_sandbox()
        cid = cri_stub.create_container(sandbox_id, "test:v1")
        cri_stub.start_container(cid)
        config = ProbeConfig(category=ProbeCategory.READINESS)
        probe_runner.register_probe(cid, config)
        probe_runner.execute_probe(cid, ProbeCategory.READINESS)
        status = probe_runner.evaluate_status(cid, ProbeCategory.READINESS)
        assert status.last_probe_time is not None

    def test_clear_nonexistent(self, probe_runner):
        probe_runner.clear("nonexistent")  # Should not raise

    def test_exec_probe_on_stopped_container(self, probe_runner, cri_stub):
        sandbox_id = cri_stub.run_pod_sandbox()
        cid = cri_stub.create_container(sandbox_id, "test:v1")
        # Not started -> exec will fail
        config = ProbeConfig(
            probe_type=ProbeType.EXEC,
            category=ProbeCategory.READINESS,
        )
        probe_runner.register_probe(cid, config)
        result = probe_runner.execute_probe(cid, ProbeCategory.READINESS)
        assert result == ProbeResult.FAILURE


# ============================================================
# VolumeManager Tests
# ============================================================


class TestVolumeManager:
    """Validate VolumeManager provisioning and lifecycle."""

    def test_creation(self, volume_manager):
        assert volume_manager.total_provisioned == 0

    def test_provision_empty_dir(self, volume_manager):
        specs = [VolumeSpec(name="data")]
        provisioned = volume_manager.provision_volumes(specs)
        assert "data" in provisioned
        assert provisioned["data"].startswith("vol-empty-")

    def test_provision_config_map(self, volume_manager):
        specs = [
            VolumeSpec(
                name="config",
                volume_type=VolumeType.CONFIG_MAP,
                config_map_name="app-config",
                data={"key": "value"},
            )
        ]
        provisioned = volume_manager.provision_volumes(specs)
        assert provisioned["config"].startswith("vol-cm-")

    def test_provision_secret(self, volume_manager):
        specs = [
            VolumeSpec(
                name="tls",
                volume_type=VolumeType.SECRET,
                secret_name="tls-cert",
            )
        ]
        provisioned = volume_manager.provision_volumes(specs)
        assert provisioned["tls"].startswith("vol-secret-")

    def test_provision_pvc(self, volume_manager):
        claim = PVClaim(name="db-data")
        volume_manager.create_pvc(claim)
        specs = [
            VolumeSpec(
                name="db",
                volume_type=VolumeType.PERSISTENT_VOLUME_CLAIM,
                claim_name="db-data",
            )
        ]
        provisioned = volume_manager.provision_volumes(specs)
        assert provisioned["db"].startswith("vol-pvc-")

    def test_provision_pvc_not_found(self, volume_manager):
        specs = [
            VolumeSpec(
                name="db",
                volume_type=VolumeType.PERSISTENT_VOLUME_CLAIM,
                claim_name="nonexistent",
            )
        ]
        with pytest.raises(PVCNotFoundError):
            volume_manager.provision_volumes(specs)

    def test_provision_empty_dir_storage_limit(self):
        vm = VolumeManager(storage_pool_bytes=100)
        specs = [VolumeSpec(name="big", size_bytes=200)]
        with pytest.raises(VolumeProvisionError):
            vm.provision_volumes(specs)

    def test_mount_volumes(self, volume_manager):
        specs = [VolumeSpec(name="data")]
        provisioned = volume_manager.provision_volumes(specs)
        mounts = [VolumeMount(name="data", mount_path="/app/data")]
        volume_manager.mount_volumes("ctr-1", mounts, provisioned)

    def test_mount_volumes_not_provisioned(self, volume_manager):
        mounts = [VolumeMount(name="missing", mount_path="/data")]
        with pytest.raises(VolumeMountError):
            volume_manager.mount_volumes("ctr-1", mounts, {})

    def test_cleanup_volumes(self, volume_manager):
        specs = [VolumeSpec(name="data")]
        provisioned = volume_manager.provision_volumes(specs)
        cleaned = volume_manager.cleanup_volumes(list(provisioned.values()))
        assert cleaned == 1

    def test_cleanup_preserves_pvcs(self, volume_manager):
        claim = PVClaim(name="db-data")
        volume_manager.create_pvc(claim)
        specs = [
            VolumeSpec(
                name="db",
                volume_type=VolumeType.PERSISTENT_VOLUME_CLAIM,
                claim_name="db-data",
            )
        ]
        provisioned = volume_manager.provision_volumes(specs)
        cleaned = volume_manager.cleanup_volumes(
            list(provisioned.values()), preserve_pvcs=True
        )
        assert cleaned == 0

    def test_cleanup_force_remove_pvcs(self, volume_manager):
        claim = PVClaim(name="db-data")
        volume_manager.create_pvc(claim)
        specs = [
            VolumeSpec(
                name="db",
                volume_type=VolumeType.PERSISTENT_VOLUME_CLAIM,
                claim_name="db-data",
            )
        ]
        provisioned = volume_manager.provision_volumes(specs)
        cleaned = volume_manager.cleanup_volumes(
            list(provisioned.values()), preserve_pvcs=False
        )
        assert cleaned == 1

    def test_create_pvc(self, volume_manager):
        claim = PVClaim(name="test-pvc")
        result = volume_manager.create_pvc(claim)
        assert result == "test-pvc"

    def test_delete_pvc(self, volume_manager):
        claim = PVClaim(name="test-pvc")
        volume_manager.create_pvc(claim)
        volume_manager.delete_pvc("test-pvc")
        assert len(volume_manager.list_pvcs()) == 0

    def test_list_pvcs(self, volume_manager):
        volume_manager.create_pvc(PVClaim(name="pvc-1"))
        volume_manager.create_pvc(PVClaim(name="pvc-2"))
        assert len(volume_manager.list_pvcs()) == 2

    def test_active_volumes(self, volume_manager):
        specs = [VolumeSpec(name="data")]
        volume_manager.provision_volumes(specs)
        assert volume_manager.active_volumes == 1

    def test_storage_used(self, volume_manager):
        specs = [VolumeSpec(name="data", size_bytes=1000)]
        volume_manager.provision_volumes(specs)
        assert volume_manager.storage_used_bytes == 1000

    def test_storage_available(self, volume_manager):
        initial = volume_manager.storage_available_bytes
        specs = [VolumeSpec(name="data", size_bytes=1000)]
        volume_manager.provision_volumes(specs)
        assert volume_manager.storage_available_bytes == initial - 1000

    def test_total_provisioned(self, volume_manager):
        specs = [VolumeSpec(name="v1"), VolumeSpec(name="v2")]
        volume_manager.provision_volumes(specs)
        assert volume_manager.total_provisioned == 2

    def test_provision_multiple_types(self, volume_manager):
        volume_manager.create_pvc(PVClaim(name="db-pvc"))
        specs = [
            VolumeSpec(name="empty", volume_type=VolumeType.EMPTY_DIR),
            VolumeSpec(
                name="db",
                volume_type=VolumeType.PERSISTENT_VOLUME_CLAIM,
                claim_name="db-pvc",
            ),
            VolumeSpec(
                name="config",
                volume_type=VolumeType.CONFIG_MAP,
                config_map_name="cfg",
            ),
            VolumeSpec(
                name="secret",
                volume_type=VolumeType.SECRET,
                secret_name="sec",
            ),
        ]
        provisioned = volume_manager.provision_volumes(specs)
        assert len(provisioned) == 4

    def test_cleanup_nonexistent(self, volume_manager):
        cleaned = volume_manager.cleanup_volumes(["nonexistent-vol"])
        assert cleaned == 0

    def test_storage_released_on_cleanup(self, volume_manager):
        specs = [VolumeSpec(name="data", size_bytes=5000)]
        provisioned = volume_manager.provision_volumes(specs)
        volume_manager.cleanup_volumes(list(provisioned.values()))
        assert volume_manager.storage_used_bytes == 0

    def test_delete_pvc_nonexistent(self, volume_manager):
        volume_manager.delete_pvc("nonexistent")  # Should not raise

    def test_provision_with_event_bus(self):
        bus = MagicMock()
        vm = VolumeManager(event_bus=bus)
        specs = [VolumeSpec(name="data")]
        vm.provision_volumes(specs)
        assert bus.publish.called

    def test_pvc_bound_after_provision(self, volume_manager):
        claim = PVClaim(name="test-pvc")
        volume_manager.create_pvc(claim)
        specs = [
            VolumeSpec(
                name="pvc-vol",
                volume_type=VolumeType.PERSISTENT_VOLUME_CLAIM,
                claim_name="test-pvc",
            )
        ]
        volume_manager.provision_volumes(specs)
        pvcs = volume_manager.list_pvcs()
        assert pvcs[0].bound is True

    def test_provision_empty_list(self, volume_manager):
        provisioned = volume_manager.provision_volumes([])
        assert provisioned == {}

    def test_cleanup_empty_list(self, volume_manager):
        cleaned = volume_manager.cleanup_volumes([])
        assert cleaned == 0

    def test_multiple_mounts_same_container(self, volume_manager):
        specs = [VolumeSpec(name="v1"), VolumeSpec(name="v2")]
        provisioned = volume_manager.provision_volumes(specs)
        mounts = [
            VolumeMount(name="v1", mount_path="/v1"),
            VolumeMount(name="v2", mount_path="/v2"),
        ]
        volume_manager.mount_volumes("ctr-1", mounts, provisioned)


# ============================================================
# KubeletV2 Tests
# ============================================================


class TestKubeletV2:
    """Validate KubeletV2 CRI-integrated pod lifecycle."""

    def test_creation(self, kubelet):
        assert kubelet.total_pods_created == 0

    def test_create_pod_basic(self, kubelet):
        spec = PodV2Spec(number=15)
        pod = kubelet.create_pod(spec)
        assert pod.phase == PodPhaseV2.RUNNING

    def test_create_pod_has_sandbox(self, kubelet):
        spec = PodV2Spec(number=3)
        pod = kubelet.create_pod(spec)
        assert pod.sandbox_id != ""

    def test_create_pod_has_main_container(self, kubelet):
        spec = PodV2Spec(number=3)
        pod = kubelet.create_pod(spec)
        assert pod.main_container_id != ""

    def test_create_pod_has_sidecars(self, kubelet):
        spec = PodV2Spec(number=3)
        pod = kubelet.create_pod(spec)
        assert len(pod.sidecar_container_ids) == 4  # default sidecars

    def test_create_pod_no_sidecars(self, cri_stub, image_puller, init_runner, probe_runner, volume_manager):
        injector = SidecarInjector(default_sidecars=[])
        kub = KubeletV2(
            cri_service=cri_stub,
            image_puller=image_puller,
            init_runner=init_runner,
            sidecar_injector=injector,
            probe_runner=probe_runner,
            volume_manager=volume_manager,
        )
        spec = PodV2Spec(number=3)
        pod = kub.create_pod(spec)
        assert len(pod.sidecar_container_ids) == 0

    def test_create_pod_with_init_containers(self, kubelet):
        spec = PodV2Spec(
            number=5,
            init_containers=[
                InitContainerSpec(name="init-db"),
                InitContainerSpec(name="init-config"),
            ],
        )
        pod = kubelet.create_pod(spec)
        assert len(pod.init_results) >= 2
        assert all(r.succeeded for r in pod.init_results[:2])

    def test_create_pod_with_volumes(self, kubelet):
        spec = PodV2Spec(
            number=7,
            volumes=[VolumeSpec(name="data")],
            volume_mounts=[VolumeMount(name="data", mount_path="/app/data")],
        )
        pod = kubelet.create_pod(spec)
        assert len(pod.volume_ids) == 1

    def test_create_pod_with_probes(self, kubelet):
        spec = PodV2Spec(
            number=10,
            readiness_probe=ProbeConfig(category=ProbeCategory.READINESS),
            liveness_probe=ProbeConfig(category=ProbeCategory.LIVENESS),
        )
        pod = kubelet.create_pod(spec)
        assert pod.phase == PodPhaseV2.RUNNING

    def test_create_pod_has_node(self, kubelet):
        spec = PodV2Spec(number=3)
        pod = kubelet.create_pod(spec)
        assert pod.node_name is not None
        assert pod.node_name.startswith("fizz-node-")

    def test_create_pod_started_at(self, kubelet):
        spec = PodV2Spec(number=3)
        pod = kubelet.create_pod(spec)
        assert pod.started_at is not None

    def test_evaluate_fizzbuzz_15(self, kubelet):
        result, pod = kubelet.evaluate(15)
        assert result == "FizzBuzz"

    def test_evaluate_fizzbuzz_3(self, kubelet):
        result, pod = kubelet.evaluate(3)
        assert result == "Fizz"

    def test_evaluate_fizzbuzz_5(self, kubelet):
        result, pod = kubelet.evaluate(5)
        assert result == "Buzz"

    def test_evaluate_fizzbuzz_7(self, kubelet):
        result, pod = kubelet.evaluate(7)
        assert result == "7"

    def test_evaluate_pod_result(self, kubelet):
        result, pod = kubelet.evaluate(15)
        assert pod.result == "FizzBuzz"

    def test_evaluate_pod_phase(self, kubelet):
        result, pod = kubelet.evaluate(3)
        assert pod.phase == PodPhaseV2.SUCCEEDED

    def test_evaluate_execution_time(self, kubelet):
        result, pod = kubelet.evaluate(3)
        assert pod.execution_time_ns > 0

    def test_evaluate_pod_events(self, kubelet):
        result, pod = kubelet.evaluate(3)
        assert len(pod.events) >= 1

    def test_total_pods_created(self, kubelet):
        kubelet.create_pod(PodV2Spec(number=1))
        kubelet.create_pod(PodV2Spec(number=2))
        assert kubelet.total_pods_created == 2

    def test_active_pods(self, kubelet):
        kubelet.create_pod(PodV2Spec(number=1))
        assert len(kubelet.active_pods) >= 1

    def test_terminate_pod(self, kubelet):
        spec = PodV2Spec(number=3)
        pod = kubelet.create_pod(spec)
        kubelet.terminate_pod(pod)
        assert pod.phase in (PodPhaseV2.SUCCEEDED, PodPhaseV2.FAILED)

    def test_terminate_pod_finished_at(self, kubelet):
        spec = PodV2Spec(number=3)
        pod = kubelet.create_pod(spec)
        kubelet.terminate_pod(pod)
        assert pod.finished_at is not None

    def test_restart_container(self, kubelet):
        spec = PodV2Spec(number=3)
        pod = kubelet.create_pod(spec)
        kubelet.restart_container(pod, pod.main_container_id, 0)
        assert kubelet.total_restarts == 1

    def test_restart_backoff_calculation(self, kubelet):
        spec = PodV2Spec(number=3)
        pod = kubelet.create_pod(spec)
        kubelet.restart_container(pod, pod.main_container_id, 3)
        # backoff = min(10 * 2^3, 300) = 80
        assert kubelet.restart_history[-1]["backoff_seconds"] == 80.0

    def test_restart_backoff_cap(self, kubelet):
        spec = PodV2Spec(number=3)
        pod = kubelet.create_pod(spec)
        kubelet.restart_container(pod, pod.main_container_id, 10)
        assert kubelet.restart_history[-1]["backoff_seconds"] == 300.0

    def test_restart_history(self, kubelet):
        spec = PodV2Spec(number=3)
        pod = kubelet.create_pod(spec)
        kubelet.restart_container(pod, pod.main_container_id, 0)
        assert len(kubelet.restart_history) == 1

    def test_restart_counts_updated(self, kubelet):
        spec = PodV2Spec(number=3)
        pod = kubelet.create_pod(spec)
        kubelet.restart_container(pod, pod.main_container_id, 0)
        assert pod.restart_counts[pod.main_container_id] == 1

    def test_get_pod_status(self, kubelet):
        spec = PodV2Spec(number=15)
        pod = kubelet.create_pod(spec)
        status = kubelet.get_pod_status(pod)
        assert status["name"] == pod.name
        assert status["phase"] == "RUNNING"

    def test_get_pod_status_has_init_results(self, kubelet):
        spec = PodV2Spec(
            number=3,
            init_containers=[InitContainerSpec(name="init-1")],
        )
        pod = kubelet.create_pod(spec)
        status = kubelet.get_pod_status(pod)
        assert len(status["init_container_results"]) >= 1

    def test_evaluate_with_custom_spec(self, kubelet):
        spec = PodV2Spec(number=0, image="custom:v1")
        result, pod = kubelet.evaluate(30, spec=spec)
        assert result == "FizzBuzz"

    def test_create_pod_with_pull_policy_always(self, kubelet):
        spec = PodV2Spec(
            number=3, image_pull_policy=ImagePullPolicy.ALWAYS
        )
        pod = kubelet.create_pod(spec)
        assert pod.phase == PodPhaseV2.RUNNING

    def test_evaluate_multiple(self, kubelet):
        for n in [1, 2, 3, 4, 5, 6, 10, 15]:
            result, pod = kubelet.evaluate(n)
            if n == 15:
                assert result == "FizzBuzz"
            elif n % 3 == 0:
                assert result == "Fizz"
            elif n % 5 == 0:
                assert result == "Buzz"
            else:
                assert result == str(n)

    def test_image_puller_property(self, kubelet, image_puller):
        assert kubelet.image_puller is image_puller

    def test_init_runner_property(self, kubelet, init_runner):
        assert kubelet.init_runner is init_runner

    def test_sidecar_injector_property(self, kubelet, sidecar_injector):
        assert kubelet.sidecar_injector is sidecar_injector

    def test_probe_runner_property(self, kubelet, probe_runner):
        assert kubelet.probe_runner is probe_runner

    def test_volume_manager_property(self, kubelet, volume_manager):
        assert kubelet.volume_manager is volume_manager

    def test_create_pod_with_startup_probe(self, kubelet):
        spec = PodV2Spec(
            number=3,
            startup_probe=ProbeConfig(category=ProbeCategory.STARTUP),
        )
        pod = kubelet.create_pod(spec)
        assert pod.phase == PodPhaseV2.RUNNING

    def test_evaluate_returns_tuple(self, kubelet):
        result = kubelet.evaluate(3)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_create_pod_skip_sidecars_annotation(self, kubelet):
        spec = PodV2Spec(
            number=3,
            sidecar_annotations={"fizzbuzz.io/inject-sidecars": "false"},
        )
        pod = kubelet.create_pod(spec)
        assert len(pod.sidecar_container_ids) == 0

    def test_create_pod_with_labels(self, kubelet):
        spec = PodV2Spec(
            number=3,
            labels={"app": "fizzbuzz", "env": "test"},
        )
        pod = kubelet.create_pod(spec)
        assert pod.phase == PodPhaseV2.RUNNING

    def test_create_pod_custom_namespace(self, kubelet):
        spec = PodV2Spec(number=3, namespace="fizzbuzz-staging")
        pod = kubelet.create_pod(spec)
        assert pod.spec.namespace == "fizzbuzz-staging"


# ============================================================
# KubeV2Dashboard Tests
# ============================================================


class TestKubeV2Dashboard:
    """Validate KubeV2Dashboard ASCII rendering."""

    def test_creation(self):
        d = KubeV2Dashboard()
        assert d._width == DEFAULT_DASHBOARD_WIDTH

    def test_custom_width(self):
        d = KubeV2Dashboard(width=100)
        assert d._width == 100

    def test_render(self, kubelet):
        d = KubeV2Dashboard()
        output = d.render(kubelet)
        assert "FizzKubeV2 Dashboard" in output

    def test_render_has_version(self, kubelet):
        d = KubeV2Dashboard()
        output = d.render(kubelet)
        assert KUBEV2_VERSION in output

    def test_render_pods_empty(self, kubelet):
        d = KubeV2Dashboard()
        output = d.render_pods(kubelet)
        assert "No pods" in output

    def test_render_pods_with_pod(self, kubelet):
        kubelet.create_pod(PodV2Spec(number=3))
        d = KubeV2Dashboard()
        output = d.render_pods(kubelet)
        assert "fizzbuzz-v2-" in output

    def test_render_pod_detail(self, kubelet):
        pod = kubelet.create_pod(PodV2Spec(number=3))
        d = KubeV2Dashboard()
        output = d.render_pod_detail(pod)
        assert pod.name in output
        assert "Phase:" in output

    def test_render_probes_empty(self, kubelet):
        d = KubeV2Dashboard()
        output = d.render_probes(kubelet)
        assert "No probes" in output

    def test_render_images_empty(self, kubelet):
        d = KubeV2Dashboard()
        output = d.render_images(kubelet)
        # After creating pods, images will be pulled
        assert isinstance(output, str)

    def test_render_events_empty(self, kubelet):
        d = KubeV2Dashboard()
        output = d.render_events(kubelet)
        assert "No events" in output

    def test_center(self):
        d = KubeV2Dashboard(width=20)
        result = d._center("test")
        assert len(result) == 20
        assert "test" in result

    def test_format_bytes_b(self):
        d = KubeV2Dashboard()
        assert "B" in d._format_bytes(500)

    def test_format_bytes_kb(self):
        d = KubeV2Dashboard()
        assert "KB" in d._format_bytes(2048)

    def test_format_bytes_mb(self):
        d = KubeV2Dashboard()
        assert "MB" in d._format_bytes(2097152)

    def test_format_bytes_gb(self):
        d = KubeV2Dashboard()
        assert "GB" in d._format_bytes(2147483648)


# ============================================================
# FizzKubeV2Middleware Tests
# ============================================================


class TestFizzKubeV2Middleware:
    """Validate FizzKubeV2Middleware pipeline integration."""

    def test_name(self, kubelet):
        mw = FizzKubeV2Middleware(kubelet=kubelet)
        assert mw.get_name() == "FizzKubeV2Middleware"

    def test_name_property(self, kubelet):
        mw = FizzKubeV2Middleware(kubelet=kubelet)
        assert mw.name == "FizzKubeV2Middleware"

    def test_priority(self, kubelet):
        mw = FizzKubeV2Middleware(kubelet=kubelet)
        assert mw.get_priority() == 116

    def test_priority_property(self, kubelet):
        mw = FizzKubeV2Middleware(kubelet=kubelet)
        assert mw.priority == 116

    def test_process(self, kubelet):
        mw = FizzKubeV2Middleware(kubelet=kubelet)
        context = ProcessingContext(number=15, session_id="test-session")
        result = mw.process(context, lambda ctx: ctx)
        assert result.metadata.get("fizzkubev2_result") == "FizzBuzz"

    def test_process_enriches_metadata(self, kubelet):
        mw = FizzKubeV2Middleware(kubelet=kubelet)
        context = ProcessingContext(number=3, session_id="test-session")
        result = mw.process(context, lambda ctx: ctx)
        assert "fizzkubev2_pod" in result.metadata
        assert "fizzkubev2_sandbox" in result.metadata
        assert "fizzkubev2_phase" in result.metadata
        assert "fizzkubev2_init_count" in result.metadata
        assert "fizzkubev2_sidecar_count" in result.metadata

    def test_process_has_probe_status(self, kubelet):
        mw = FizzKubeV2Middleware(kubelet=kubelet)
        context = ProcessingContext(number=5, session_id="test-session")
        result = mw.process(context, lambda ctx: ctx)
        assert "fizzkubev2_probe_status" in result.metadata

    def test_process_delegates_to_next(self, kubelet):
        mw = FizzKubeV2Middleware(kubelet=kubelet)
        context = ProcessingContext(number=3, session_id="test-session")
        called = {"value": False}

        def next_handler(ctx):
            called["value"] = True
            return ctx

        mw.process(context, next_handler)
        assert called["value"] is True

    def test_render_dashboard(self, kubelet):
        mw = FizzKubeV2Middleware(kubelet=kubelet)
        output = mw.render_dashboard()
        assert "FizzKubeV2 Dashboard" in output

    def test_render_pods(self, kubelet):
        mw = FizzKubeV2Middleware(kubelet=kubelet)
        output = mw.render_pods()
        assert isinstance(output, str)

    def test_render_pod_detail_found(self, kubelet):
        pod = kubelet.create_pod(PodV2Spec(number=3))
        mw = FizzKubeV2Middleware(kubelet=kubelet)
        output = mw.render_pod_detail(pod.name)
        assert pod.name in output

    def test_render_pod_detail_not_found(self, kubelet):
        mw = FizzKubeV2Middleware(kubelet=kubelet)
        output = mw.render_pod_detail("nonexistent")
        assert "not found" in output

    def test_render_probes(self, kubelet):
        mw = FizzKubeV2Middleware(kubelet=kubelet)
        output = mw.render_probes()
        assert isinstance(output, str)

    def test_render_images(self, kubelet):
        mw = FizzKubeV2Middleware(kubelet=kubelet)
        output = mw.render_images()
        assert isinstance(output, str)

    def test_render_events(self, kubelet):
        mw = FizzKubeV2Middleware(kubelet=kubelet)
        output = mw.render_events()
        assert isinstance(output, str)

    def test_render_stats(self, kubelet):
        mw = FizzKubeV2Middleware(kubelet=kubelet)
        output = mw.render_stats()
        assert "Evaluations:" in output

    def test_process_fizz(self, kubelet):
        mw = FizzKubeV2Middleware(kubelet=kubelet)
        context = ProcessingContext(number=9, session_id="test")
        result = mw.process(context, lambda ctx: ctx)
        assert result.metadata["fizzkubev2_result"] == "Fizz"

    def test_process_buzz(self, kubelet):
        mw = FizzKubeV2Middleware(kubelet=kubelet)
        context = ProcessingContext(number=10, session_id="test")
        result = mw.process(context, lambda ctx: ctx)
        assert result.metadata["fizzkubev2_result"] == "Buzz"

    def test_process_number(self, kubelet):
        mw = FizzKubeV2Middleware(kubelet=kubelet)
        context = ProcessingContext(number=7, session_id="test")
        result = mw.process(context, lambda ctx: ctx)
        assert result.metadata["fizzkubev2_result"] == "7"

    def test_process_fizzbuzz(self, kubelet):
        mw = FizzKubeV2Middleware(kubelet=kubelet)
        context = ProcessingContext(number=30, session_id="test")
        result = mw.process(context, lambda ctx: ctx)
        assert result.metadata["fizzkubev2_result"] == "FizzBuzz"

    def test_dashboard_width(self, kubelet):
        mw = FizzKubeV2Middleware(kubelet=kubelet, dashboard_width=100)
        assert mw.dashboard._width == 100


# ============================================================
# Factory Function Tests
# ============================================================


class TestCreateFizzKubeV2Subsystem:
    """Validate factory function wiring."""

    def test_default_creation(self):
        kubelet, middleware = create_fizzkubev2_subsystem()
        assert isinstance(kubelet, KubeletV2)
        assert isinstance(middleware, FizzKubeV2Middleware)

    def test_with_containerd_daemon(self):
        daemon = MagicMock()
        daemon.cri_service = _CRIStub()
        kubelet, middleware = create_fizzkubev2_subsystem(
            containerd_daemon=daemon
        )
        assert isinstance(kubelet, KubeletV2)

    def test_with_cri_service(self):
        cri = _CRIStub()
        kubelet, middleware = create_fizzkubev2_subsystem(cri_service=cri)
        assert isinstance(kubelet, KubeletV2)

    def test_custom_pull_policy(self):
        kubelet, middleware = create_fizzkubev2_subsystem(
            default_pull_policy="Always"
        )
        assert isinstance(kubelet, KubeletV2)

    def test_invalid_pull_policy(self):
        kubelet, middleware = create_fizzkubev2_subsystem(
            default_pull_policy="invalid"
        )
        assert isinstance(kubelet, KubeletV2)

    def test_no_sidecars(self):
        kubelet, middleware = create_fizzkubev2_subsystem(
            inject_sidecars=False
        )
        spec = PodV2Spec(number=3)
        pod = kubelet.create_pod(spec)
        assert len(pod.sidecar_container_ids) == 0

    def test_with_sidecars(self):
        kubelet, middleware = create_fizzkubev2_subsystem(
            inject_sidecars=True
        )
        spec = PodV2Spec(number=3)
        pod = kubelet.create_pod(spec)
        assert len(pod.sidecar_container_ids) == 4

    def test_custom_storage_pool(self):
        kubelet, middleware = create_fizzkubev2_subsystem(
            storage_pool_bytes=1000
        )
        assert kubelet.volume_manager.storage_available_bytes == 1000

    def test_custom_rules(self):
        rules = [
            {"divisor": 7, "label": "Fizz", "priority": 1},
            {"divisor": 11, "label": "Buzz", "priority": 2},
        ]
        kubelet, middleware = create_fizzkubev2_subsystem(rules=rules)
        result, pod = kubelet.evaluate(77)
        assert result == "FizzBuzz"

    def test_with_event_bus(self):
        bus = MagicMock()
        kubelet, middleware = create_fizzkubev2_subsystem(event_bus=bus)
        kubelet.evaluate(3)
        assert bus.publish.called

    def test_returns_tuple(self):
        result = create_fizzkubev2_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_custom_dashboard_width(self):
        kubelet, middleware = create_fizzkubev2_subsystem(
            dashboard_width=100
        )
        assert middleware.dashboard._width == 100


# ============================================================
# Exception Tests
# ============================================================


class TestKubeV2Exceptions:
    """Validate all 21 FizzKubeV2 exception classes."""

    def test_kubev2_error(self):
        exc = KubeV2Error("test error")
        assert str(exc) == "test error"
        assert exc.error_code == "EFP-KV200"
        assert exc.context == {}

    def test_kubev2_error_custom_code(self):
        exc = KubeV2Error("test", error_code="EFP-CUSTOM")
        assert exc.error_code == "EFP-CUSTOM"

    def test_kubev2_error_with_context(self):
        exc = KubeV2Error("test", context={"key": "value"})
        assert exc.context["key"] == "value"

    def test_kubelet_v2_error(self):
        exc = KubeletV2Error("pod creation failed")
        assert "KubeletV2 error" in str(exc)
        assert exc.error_code == "EFP-KV201"
        assert exc.context["reason"] == "pod creation failed"

    def test_kv2_image_pull_error(self):
        exc = KV2ImagePullError("fizzbuzz:latest", "Always", "timeout")
        assert "fizzbuzz:latest" in str(exc)
        assert exc.error_code == "EFP-KV202"
        assert exc.context["image"] == "fizzbuzz:latest"
        assert exc.context["policy"] == "Always"

    def test_image_pull_backoff_error(self):
        exc = ImagePullBackOffError("fizzbuzz:latest", 3, 40.0)
        assert "backoff" in str(exc)
        assert exc.error_code == "EFP-KV203"
        assert exc.context["attempt"] == 3
        assert exc.context["backoff_seconds"] == 40.0

    def test_image_not_present_error(self):
        exc = ImageNotPresentError("missing:latest")
        assert "missing:latest" in str(exc)
        assert exc.error_code == "EFP-KV204"

    def test_pull_secret_error(self):
        exc = PullSecretError("creds", "reg.io", "auth failed")
        assert "creds" in str(exc)
        assert exc.error_code == "EFP-KV205"
        assert exc.context["registry"] == "reg.io"

    def test_init_container_failed_error(self):
        exc = InitContainerFailedError("init-db", 1, "my-pod")
        assert "init-db" in str(exc)
        assert exc.error_code == "EFP-KV206"
        assert exc.context["exit_code"] == 1

    def test_init_container_timeout_error(self):
        exc = InitContainerTimeoutError("init-db", 60.0)
        assert "timed out" in str(exc)
        assert exc.error_code == "EFP-KV207"
        assert exc.context["timeout_seconds"] == 60.0

    def test_sidecar_injection_error(self):
        exc = SidecarInjectionError("my-pod", "proxy", "conflict")
        assert "proxy" in str(exc)
        assert exc.error_code == "EFP-KV208"

    def test_sidecar_lifecycle_error(self):
        exc = SidecarLifecycleError("proxy", "running", "created")
        assert "proxy" in str(exc)
        assert exc.error_code == "EFP-KV209"
        assert exc.context["expected_state"] == "running"

    def test_probe_failed_error(self):
        exc = ProbeFailedError("ctr-1", "readiness", "httpGet", "timeout")
        assert "readiness" in str(exc)
        assert exc.error_code == "EFP-KV210"

    def test_probe_timeout_error(self):
        exc = ProbeTimeoutError("ctr-1", "liveness", 5.0)
        assert "timed out" in str(exc)
        assert exc.error_code == "EFP-KV211"

    def test_readiness_probe_failed_error(self):
        exc = ReadinessProbeFailedError("ctr-1", 3, 3)
        assert "readiness" in str(exc)
        assert exc.error_code == "EFP-KV212"
        assert exc.context["consecutive_failures"] == 3

    def test_liveness_probe_failed_error(self):
        exc = LivenessProbeFailedError("ctr-1", 3, 3)
        assert "liveness" in str(exc)
        assert exc.error_code == "EFP-KV213"
        assert "restart" in str(exc)

    def test_startup_probe_failed_error(self):
        exc = StartupProbeFailedError("ctr-1", 120.0)
        assert "startup" in str(exc)
        assert exc.error_code == "EFP-KV214"
        assert exc.context["elapsed_seconds"] == 120.0

    def test_volume_provision_error(self):
        exc = VolumeProvisionError("data", "emptyDir", "out of space")
        assert "data" in str(exc)
        assert exc.error_code == "EFP-KV215"

    def test_volume_mount_error(self):
        exc = VolumeMountError("data", "ctr-1", "/app/data", "conflict")
        assert "/app/data" in str(exc)
        assert exc.error_code == "EFP-KV216"

    def test_pvc_not_found_error(self):
        exc = PVCNotFoundError("db-data")
        assert "db-data" in str(exc)
        assert exc.error_code == "EFP-KV217"

    def test_container_restart_backoff_error(self):
        exc = ContainerRestartBackoffError("ctr-1", 3, 40.0)
        assert "backoff" in str(exc)
        assert exc.error_code == "EFP-KV218"
        assert exc.context["restart_count"] == 3

    def test_pod_termination_error(self):
        exc = PodTerminationError("my-pod", "containers not responding")
        assert "my-pod" in str(exc)
        assert exc.error_code == "EFP-KV219"

    def test_kubev2_middleware_error(self):
        exc = KubeV2MiddlewareError(42, "pod creation failed")
        assert "42" in str(exc)
        assert exc.error_code == "EFP-KV220"
        assert exc.evaluation_number == 42

    def test_inheritance_kubev2_error(self):
        assert issubclass(KubeletV2Error, KubeV2Error)
        assert issubclass(KV2ImagePullError, KubeV2Error)
        assert issubclass(ImagePullBackOffError, KubeV2Error)
        assert issubclass(ImageNotPresentError, KubeV2Error)
        assert issubclass(PullSecretError, KubeV2Error)
        assert issubclass(InitContainerFailedError, KubeV2Error)
        assert issubclass(InitContainerTimeoutError, KubeV2Error)
        assert issubclass(SidecarInjectionError, KubeV2Error)
        assert issubclass(SidecarLifecycleError, KubeV2Error)
        assert issubclass(ProbeFailedError, KubeV2Error)
        assert issubclass(ProbeTimeoutError, KubeV2Error)
        assert issubclass(VolumeProvisionError, KubeV2Error)
        assert issubclass(VolumeMountError, KubeV2Error)
        assert issubclass(PVCNotFoundError, KubeV2Error)
        assert issubclass(ContainerRestartBackoffError, KubeV2Error)
        assert issubclass(PodTerminationError, KubeV2Error)
        assert issubclass(KubeV2MiddlewareError, KubeV2Error)

    def test_probe_failed_subclasses(self):
        assert issubclass(ReadinessProbeFailedError, ProbeFailedError)
        assert issubclass(LivenessProbeFailedError, ProbeFailedError)
        assert issubclass(StartupProbeFailedError, ProbeFailedError)


# ============================================================
# CRI Stub Tests
# ============================================================


class TestCRIStub:
    """Validate _CRIStub standalone CRI implementation."""

    def test_creation(self):
        stub = _CRIStub()
        assert stub.sandbox_count == 0

    def test_run_pod_sandbox(self):
        stub = _CRIStub()
        sid = stub.run_pod_sandbox()
        assert sid.startswith("sandbox-")

    def test_stop_pod_sandbox(self):
        stub = _CRIStub()
        sid = stub.run_pod_sandbox()
        stub.stop_pod_sandbox(sid)
        status = stub.sandbox_status(sid)
        assert status["state"] == "stopped"

    def test_remove_pod_sandbox(self):
        stub = _CRIStub()
        sid = stub.run_pod_sandbox()
        stub.remove_pod_sandbox(sid)
        assert stub.sandbox_count == 0

    def test_create_container(self):
        stub = _CRIStub()
        sid = stub.run_pod_sandbox()
        cid = stub.create_container(sid, "test:v1")
        assert cid != ""

    def test_start_container(self):
        stub = _CRIStub()
        sid = stub.run_pod_sandbox()
        cid = stub.create_container(sid, "test:v1")
        result = stub.start_container(cid)
        assert result["state"] == "running"

    def test_stop_container(self):
        stub = _CRIStub()
        sid = stub.run_pod_sandbox()
        cid = stub.create_container(sid, "test:v1")
        stub.start_container(cid)
        stub.stop_container(cid)
        status = stub.container_status(cid)
        assert status["status"] == "stopped"

    def test_remove_container(self):
        stub = _CRIStub()
        sid = stub.run_pod_sandbox()
        cid = stub.create_container(sid, "test:v1")
        stub.remove_container(cid)
        assert stub.container_count == 0

    def test_container_status(self):
        stub = _CRIStub()
        sid = stub.run_pod_sandbox()
        cid = stub.create_container(sid, "test:v1")
        status = stub.container_status(cid)
        assert status["id"] == cid

    def test_pull_image(self):
        stub = _CRIStub()
        result = stub.pull_image("fizzbuzz:v1")
        assert result["image"] == "fizzbuzz:v1"
        assert "digest" in result

    def test_image_exists_false(self):
        stub = _CRIStub()
        assert stub.image_exists("missing") is False

    def test_image_exists_true(self):
        stub = _CRIStub()
        stub.pull_image("fizzbuzz:v1")
        assert stub.image_exists("fizzbuzz:v1") is True

    def test_exec_container_running(self):
        stub = _CRIStub()
        sid = stub.run_pod_sandbox()
        cid = stub.create_container(sid, "test:v1")
        stub.start_container(cid)
        result = stub.exec_container(cid, ["echo", "hello"])
        assert result["exit_code"] == 0

    def test_exec_container_not_running(self):
        stub = _CRIStub()
        sid = stub.run_pod_sandbox()
        cid = stub.create_container(sid, "test:v1")
        result = stub.exec_container(cid, ["echo"])
        assert result["exit_code"] == 1

    def test_sandbox_count(self):
        stub = _CRIStub()
        stub.run_pod_sandbox()
        stub.run_pod_sandbox()
        assert stub.sandbox_count == 2

    def test_container_count(self):
        stub = _CRIStub()
        sid = stub.run_pod_sandbox()
        stub.create_container(sid, "a:v1")
        stub.create_container(sid, "b:v1")
        assert stub.container_count == 2

    def test_image_count(self):
        stub = _CRIStub()
        stub.pull_image("a:v1")
        stub.pull_image("b:v1")
        assert stub.image_count == 2

    def test_sandbox_with_labels(self):
        stub = _CRIStub()
        sid = stub.run_pod_sandbox(labels={"app": "fizz"})
        status = stub.sandbox_status(sid)
        assert status["labels"]["app"] == "fizz"

    def test_container_custom_name(self):
        stub = _CRIStub()
        sid = stub.run_pod_sandbox()
        cid = stub.create_container(sid, "test:v1", name="my-container")
        assert cid == "my-container"

    def test_remove_sandbox_cleans_containers(self):
        stub = _CRIStub()
        sid = stub.run_pod_sandbox()
        stub.create_container(sid, "a:v1")
        stub.create_container(sid, "b:v1")
        stub.remove_pod_sandbox(sid)
        assert stub.container_count == 0

    def test_sandbox_status_unknown(self):
        stub = _CRIStub()
        status = stub.sandbox_status("nonexistent")
        assert status["state"] == "unknown"

    def test_container_status_unknown(self):
        stub = _CRIStub()
        status = stub.container_status("nonexistent")
        assert status["status"] == "unknown"

    def test_stop_sets_exit_code(self):
        stub = _CRIStub()
        sid = stub.run_pod_sandbox()
        cid = stub.create_container(sid, "test:v1")
        stub.start_container(cid)
        stub.stop_container(cid)
        status = stub.container_status(cid)
        assert status["exit_code"] == 0

    def test_start_nonexistent(self):
        stub = _CRIStub()
        result = stub.start_container("nonexistent")
        assert result["state"] == "unknown"
