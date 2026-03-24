"""
Enterprise FizzBuzz Platform - FizzCompose Test Suite

Comprehensive tests for the Multi-Container Application Orchestration subsystem.
Validates compose file parsing, variable interpolation, dependency resolution via
Kahn's algorithm topological sort, cycle detection, health check gating, compose
engine lifecycle commands (up/down/restart/scale/logs/ps/exec/top), network
creation and DNS resolution, volume creation and mounting, restart policy
evaluation, dashboard rendering, middleware integration, service group
definitions, exception hierarchy, and factory function wiring.

Docker Compose-style multi-service orchestration is fundamental to decomposing
the Enterprise FizzBuzz Platform's 116 infrastructure modules into 12 manageable
service groups with well-defined dependency boundaries.
"""

from __future__ import annotations

import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from fizzcompose import (
    COMPOSE_DASHBOARD_WIDTH,
    COMPOSE_FILE_NAME,
    COMPOSE_PROJECT_NAME,
    COMPOSE_UP_COMPLETED,
    COMPOSE_UP_STARTED,
    COMPOSE_VERSION,
    DEFAULT_HEALTH_CHECK_INTERVAL,
    DEFAULT_HEALTH_CHECK_TIMEOUT,
    DEFAULT_LOG_TAIL_LINES,
    DEFAULT_MAX_RESTART_ATTEMPTS,
    DEFAULT_NETWORK_GATEWAY,
    DEFAULT_NETWORK_SUBNET,
    DEFAULT_RESTART_DELAY,
    DEFAULT_RESTART_WINDOW,
    DEFAULT_SCALE_MAX,
    DEFAULT_STOP_TIMEOUT,
    MIDDLEWARE_PRIORITY,
    SERVICE_GROUP_COUNT,
    ComposeCommand,
    ComposeDashboard,
    ComposeEngine,
    ComposeFile,
    ComposeLogEntry,
    ComposeNetworkManager,
    ComposeParser,
    ComposeProject,
    ComposeServiceGroup,
    ComposeStats,
    ComposeStatus,
    ComposeVolumeManager,
    DeployConfig,
    DependencyCondition,
    DependencyResolver,
    DependencySpec,
    EnvironmentSpec,
    FizzComposeMiddleware,
    HealthCheckGate,
    HealthCheckSpec,
    HealthCheckType,
    NetworkConfig,
    NetworkDriver,
    PortMapping,
    ProcessInfo,
    ResourceLimits,
    RestartPolicy,
    RestartPolicyEngine,
    RestartPolicySpec,
    ServiceDefinition,
    ServiceInstance,
    ServiceState,
    VolumeConfig,
    VolumeMount,
    VolumeType,
    create_fizzcompose_subsystem,
)
from fizzcompose import (
    ComposeCircularDependencyError,
    ComposeError,
    ComposeExecError,
    ComposeFileNotFoundError,
    ComposeFileParseError,
    ComposeHealthCheckTimeoutError,
    ComposeImageNotFoundError,
    ComposeMiddlewareError,
    ComposeNetworkCreateError,
    ComposeNetworkNotFoundError,
    ComposePortConflictError,
    ComposeProjectAlreadyRunningError,
    ComposeRestartError,
    ComposeRestartPolicyExhaustedError,
    ComposeScaleError,
    ComposeServiceNotFoundError,
    ComposeServiceStartError,
    ComposeServiceStopError,
    ComposeVariableInterpolationError,
    ComposeVolumeCreateError,
    ComposeVolumeNotFoundError,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def parser():
    """Create a ComposeParser with test environment variables."""
    return ComposeParser(environment={
        "FIZZBUZZ_VERSION": "2.0",
        "LOG_LEVEL": "DEBUG",
    })


@pytest.fixture
def health_check_gate():
    """Create a HealthCheckGate with fast polling."""
    return HealthCheckGate(interval=0.1, timeout=5.0)


@pytest.fixture
def dependency_resolver(health_check_gate):
    """Create a DependencyResolver."""
    return DependencyResolver(health_check_gate=health_check_gate)


@pytest.fixture
def network_manager():
    """Create a ComposeNetworkManager."""
    return ComposeNetworkManager()


@pytest.fixture
def volume_manager():
    """Create a ComposeVolumeManager."""
    return ComposeVolumeManager()


@pytest.fixture
def restart_engine():
    """Create a RestartPolicyEngine."""
    return RestartPolicyEngine()


@pytest.fixture
def compose_engine(parser, network_manager, volume_manager,
                   dependency_resolver, restart_engine, health_check_gate):
    """Create a fully wired ComposeEngine."""
    return ComposeEngine(
        parser=parser,
        network_manager=network_manager,
        volume_manager=volume_manager,
        dependency_resolver=dependency_resolver,
        restart_policy_engine=restart_engine,
        health_check_gate=health_check_gate,
    )


@pytest.fixture
def running_engine(compose_engine):
    """Create a ComposeEngine with the default project already running."""
    compose_engine.up()
    return compose_engine


@pytest.fixture
def context():
    """Create a ProcessingContext for middleware testing."""
    return ProcessingContext(
        number=15,
        session_id="test-session-compose",
        metadata={},
    )


# ============================================================
# TestComposeEnums
# ============================================================


class TestComposeEnums:
    """Validate all enum members and their string values."""

    def test_compose_status_values(self):
        """ComposeStatus enum has all expected members."""
        assert ComposeStatus.STOPPED.value == "stopped"
        assert ComposeStatus.STARTING.value == "starting"
        assert ComposeStatus.RUNNING.value == "running"
        assert ComposeStatus.PARTIALLY_RUNNING.value == "partially_running"
        assert ComposeStatus.STOPPING.value == "stopping"
        assert ComposeStatus.ERROR.value == "error"

    def test_service_state_values(self):
        """ServiceState enum has all expected lifecycle states."""
        assert ServiceState.CREATED.value == "created"
        assert ServiceState.STARTING.value == "starting"
        assert ServiceState.RUNNING.value == "running"
        assert ServiceState.HEALTHY.value == "healthy"
        assert ServiceState.UNHEALTHY.value == "unhealthy"
        assert ServiceState.RESTARTING.value == "restarting"
        assert ServiceState.STOPPING.value == "stopping"
        assert ServiceState.STOPPED.value == "stopped"
        assert ServiceState.FAILED.value == "failed"
        assert ServiceState.COMPLETED.value == "completed"

    def test_dependency_condition_values(self):
        """DependencyCondition enum has three condition types."""
        assert DependencyCondition.SERVICE_STARTED.value == "service_started"
        assert DependencyCondition.SERVICE_HEALTHY.value == "service_healthy"
        assert DependencyCondition.SERVICE_COMPLETED_SUCCESSFULLY.value == "service_completed_successfully"

    def test_restart_policy_values(self):
        """RestartPolicy enum has four policy types."""
        assert RestartPolicy.NO.value == "no"
        assert RestartPolicy.ALWAYS.value == "always"
        assert RestartPolicy.ON_FAILURE.value == "on-failure"
        assert RestartPolicy.UNLESS_STOPPED.value == "unless-stopped"

    def test_volume_type_values(self):
        """VolumeType enum has three mount types."""
        assert VolumeType.NAMED.value == "named"
        assert VolumeType.BIND.value == "bind"
        assert VolumeType.TMPFS.value == "tmpfs"

    def test_compose_command_values(self):
        """ComposeCommand enum has all lifecycle commands."""
        assert ComposeCommand.UP.value == "up"
        assert ComposeCommand.DOWN.value == "down"
        assert ComposeCommand.RESTART.value == "restart"
        assert ComposeCommand.SCALE.value == "scale"
        assert ComposeCommand.LOGS.value == "logs"
        assert ComposeCommand.PS.value == "ps"
        assert ComposeCommand.EXEC.value == "exec"
        assert ComposeCommand.TOP.value == "top"
        assert ComposeCommand.CONFIG.value == "config"


# ============================================================
# TestComposeDataClasses
# ============================================================


class TestComposeDataClasses:
    """Test dataclass construction, defaults, and field validation."""

    def test_network_config_defaults(self):
        """NetworkConfig has correct default values."""
        config = NetworkConfig(name="test-net")
        assert config.name == "test-net"
        assert config.driver == NetworkDriver.BRIDGE
        assert config.subnet == "172.28.0.0/16"
        assert config.gateway == "172.28.0.1"
        assert config.internal is False
        assert config.enable_ipv6 is False

    def test_service_definition_construction(self):
        """ServiceDefinition can be constructed with full configuration."""
        svc = ServiceDefinition(
            name="test-svc",
            image="test:latest",
            ports=[PortMapping(host_port=8080, container_port=80)],
            deploy=DeployConfig(replicas=3),
        )
        assert svc.name == "test-svc"
        assert svc.image == "test:latest"
        assert len(svc.ports) == 1
        assert svc.deploy.replicas == 3

    def test_volume_config_defaults(self):
        """VolumeConfig has correct default values."""
        config = VolumeConfig(name="data-vol")
        assert config.name == "data-vol"
        assert config.driver == "local"
        assert config.external is False

    def test_port_mapping_defaults(self):
        """PortMapping has correct default protocol and host IP."""
        port = PortMapping(host_port=8080, container_port=80)
        assert port.protocol == "tcp"
        assert port.host_ip == "0.0.0.0"

    def test_resource_limits_defaults(self):
        """ResourceLimits has correct default CPU and memory values."""
        limits = ResourceLimits()
        assert limits.cpu_limit == 1.0
        assert limits.memory_limit == 536870912  # 512 MB
        assert limits.cpu_reservation == 0.25
        assert limits.pids_limit == 256

    def test_health_check_spec_defaults(self):
        """HealthCheckSpec has correct default values."""
        hc = HealthCheckSpec()
        assert hc.check_type == HealthCheckType.CMD_SHELL
        assert hc.command == "exit 0"
        assert hc.interval == 30.0
        assert hc.retries == 3

    def test_service_instance_defaults(self):
        """ServiceInstance starts in CREATED state."""
        inst = ServiceInstance(
            instance_id="test-1",
            service_name="test-svc",
        )
        assert inst.state == ServiceState.CREATED
        assert inst.health_status == "starting"
        assert inst.restart_count == 0
        assert inst.exit_code is None

    def test_compose_file_defaults(self):
        """ComposeFile has correct default values."""
        cf = ComposeFile()
        assert cf.version == COMPOSE_VERSION
        assert cf.project_name == COMPOSE_PROJECT_NAME
        assert len(cf.services) == 0


# ============================================================
# TestComposeParser
# ============================================================


class TestComposeParser:
    """Parse valid compose files, reject invalid data, handle variable interpolation."""

    def test_parse_default_topology(self, parser):
        """Parsing with no data returns the default 12-service topology."""
        compose_file = parser.parse()
        assert len(compose_file.services) == SERVICE_GROUP_COUNT
        assert "fizzbuzz-core" in compose_file.services
        assert "fizzbuzz-platform" in compose_file.services

    def test_parse_custom_services(self, parser):
        """Parsing custom compose data creates correct service definitions."""
        data = {
            "version": "3.8",
            "services": {
                "web": {
                    "image": "web:latest",
                    "ports": ["8080:80"],
                    "environment": {"APP_ENV": "production"},
                },
                "db": {
                    "image": "postgres:14",
                    "ports": [{"published": 5432, "target": 5432}],
                },
            },
            "networks": {
                "app-net": {"driver": "bridge"},
            },
        }
        compose_file = parser.parse(data)
        assert len(compose_file.services) == 2
        assert compose_file.services["web"].image == "web:latest"
        assert len(compose_file.services["web"].ports) == 1
        assert compose_file.services["web"].ports[0].host_port == 8080
        assert compose_file.services["web"].ports[0].container_port == 80
        assert "app-net" in compose_file.networks

    def test_parse_invalid_root(self, parser):
        """Parsing non-dict root raises ComposeFileParseError."""
        with pytest.raises(ComposeFileParseError):
            parser.parse("not a dict")

    def test_variable_interpolation(self):
        """Variables in ${VAR:-default} syntax are resolved from environment."""
        parser = ComposeParser(environment={"MY_IMAGE": "custom:v2"})
        data = {
            "services": {
                "app": {
                    "image": "${MY_IMAGE:-default:latest}",
                },
            },
        }
        compose_file = parser.parse(data)
        assert compose_file.services["app"].image == "custom:v2"

    def test_variable_interpolation_default(self):
        """Unset variables use the default value."""
        parser = ComposeParser(environment={})
        data = {
            "services": {
                "app": {
                    "image": "${UNSET_VAR:-fallback:latest}",
                },
            },
        }
        compose_file = parser.parse(data)
        assert compose_file.services["app"].image == "fallback:latest"


# ============================================================
# TestDependencyResolver
# ============================================================


class TestDependencyResolver:
    """Test topological sort, cycle detection, and dependency condition handling."""

    def test_topological_sort_default(self, dependency_resolver):
        """Default topology sorts into correct tier order."""
        compose_file = ComposeParser().parse()
        tiers = dependency_resolver.resolve(compose_file)
        assert len(tiers) > 0
        # fizzbuzz-platform should be in the first tier (no dependencies)
        assert "fizzbuzz-platform" in tiers[0]

    def test_topological_sort_linear(self, dependency_resolver):
        """Linear dependency chain produces one service per tier."""
        compose_file = ComposeFile(services={
            "a": ServiceDefinition(name="a"),
            "b": ServiceDefinition(
                name="b",
                depends_on=[DependencySpec(service="a")],
            ),
            "c": ServiceDefinition(
                name="c",
                depends_on=[DependencySpec(service="b")],
            ),
        })
        tiers = dependency_resolver.resolve(compose_file)
        assert len(tiers) == 3
        assert tiers[0] == ["a"]
        assert tiers[1] == ["b"]
        assert tiers[2] == ["c"]

    def test_cycle_detection(self, dependency_resolver):
        """Circular dependencies are detected and reported."""
        compose_file = ComposeFile(services={
            "a": ServiceDefinition(
                name="a",
                depends_on=[DependencySpec(service="c")],
            ),
            "b": ServiceDefinition(
                name="b",
                depends_on=[DependencySpec(service="a")],
            ),
            "c": ServiceDefinition(
                name="c",
                depends_on=[DependencySpec(service="b")],
            ),
        })
        with pytest.raises(ComposeCircularDependencyError) as exc_info:
            dependency_resolver.resolve(compose_file)
        assert exc_info.value.error_code == "EFP-CMP04"

    def test_parallel_services(self, dependency_resolver):
        """Independent services appear in the same tier."""
        compose_file = ComposeFile(services={
            "base": ServiceDefinition(name="base"),
            "svc-a": ServiceDefinition(
                name="svc-a",
                depends_on=[DependencySpec(service="base")],
            ),
            "svc-b": ServiceDefinition(
                name="svc-b",
                depends_on=[DependencySpec(service="base")],
            ),
        })
        tiers = dependency_resolver.resolve(compose_file)
        assert tiers[0] == ["base"]
        assert sorted(tiers[1]) == ["svc-a", "svc-b"]

    def test_dependency_conditions(self, dependency_resolver):
        """Dependency conditions are accessible per service."""
        compose_file = ComposeFile(services={
            "db": ServiceDefinition(name="db"),
            "app": ServiceDefinition(
                name="app",
                depends_on=[
                    DependencySpec(service="db", condition=DependencyCondition.SERVICE_HEALTHY),
                ],
            ),
        })
        deps = dependency_resolver.get_dependency_conditions(compose_file, "app")
        assert len(deps) == 1
        assert deps[0].service == "db"
        assert deps[0].condition == DependencyCondition.SERVICE_HEALTHY

    def test_empty_services(self, dependency_resolver):
        """Empty service list produces empty tiers."""
        compose_file = ComposeFile(services={})
        tiers = dependency_resolver.resolve(compose_file)
        assert tiers == []


# ============================================================
# TestComposeEngine
# ============================================================


class TestComposeEngine:
    """Test up/down/restart/scale/logs/ps/exec/top lifecycle operations."""

    def test_up_creates_project(self, compose_engine):
        """Compose up creates a running project with all services."""
        project = compose_engine.up()
        assert project.status == ComposeStatus.RUNNING
        assert len(project.services) == SERVICE_GROUP_COUNT
        assert len(project.networks) > 0
        assert len(project.volumes) > 0

    def test_up_already_running(self, running_engine):
        """Compose up on a running project raises error."""
        with pytest.raises(ComposeProjectAlreadyRunningError):
            running_engine.up()

    def test_down_stops_project(self, running_engine):
        """Compose down stops all services and sets status to STOPPED."""
        running_engine.down()
        assert running_engine.get_project() is None

    def test_restart_service(self, running_engine):
        """Restarting a service creates new instances."""
        old_instances = running_engine.ps().get("fizzbuzz-core", [])
        old_ids = [i.instance_id for i in old_instances]
        new_instances = running_engine.restart("fizzbuzz-core")
        new_ids = [i.instance_id for i in new_instances]
        assert len(new_instances) > 0
        # New instances have different IDs
        assert set(new_ids).isdisjoint(set(old_ids))

    def test_scale_up(self, running_engine):
        """Scaling up adds more instances."""
        instances = running_engine.scale("fizzbuzz-platform", 3)
        assert len(instances) == 3

    def test_scale_down(self, running_engine):
        """Scaling down to 0 removes all instances."""
        instances = running_engine.scale("fizzbuzz-platform", 0)
        assert len(instances) == 0

    def test_scale_exceeds_max(self, running_engine):
        """Scaling beyond max raises ComposeScaleError."""
        with pytest.raises(ComposeScaleError):
            running_engine.scale("fizzbuzz-platform", DEFAULT_SCALE_MAX + 1)

    def test_logs_for_service(self, running_engine):
        """Logs retrieval returns entries for the service."""
        logs = running_engine.logs("fizzbuzz-core")
        assert isinstance(logs, list)

    def test_ps_returns_services(self, running_engine):
        """PS returns all service instances."""
        services = running_engine.ps()
        assert len(services) == SERVICE_GROUP_COUNT
        for svc_name, instances in services.items():
            assert len(instances) > 0

    def test_exec_in_container(self, running_engine):
        """Exec runs a command in a running container."""
        output = running_engine.exec("fizzbuzz-core", "echo hello")
        assert "OK" in output
        assert "fizzbuzz-core" in output

    def test_exec_not_running(self, compose_engine):
        """Exec in a non-running service raises error."""
        with pytest.raises(ComposeServiceNotFoundError):
            compose_engine.exec("nonexistent", "echo hello")

    def test_top_shows_processes(self, running_engine):
        """Top returns process information for running containers."""
        processes = running_engine.top("fizzbuzz-core")
        assert len(processes) > 0
        assert all(isinstance(p, ProcessInfo) for p in processes)
        assert all(p.pid > 0 for p in processes)

    def test_config_returns_compose_file(self, running_engine):
        """Config returns the resolved compose file."""
        config = running_engine.config()
        assert isinstance(config, ComposeFile)
        assert len(config.services) == SERVICE_GROUP_COUNT

    def test_get_stats(self, running_engine):
        """Stats returns aggregate metrics."""
        stats = running_engine.get_stats()
        assert isinstance(stats, ComposeStats)
        assert stats.total_services == SERVICE_GROUP_COUNT
        assert stats.running_services > 0


# ============================================================
# TestComposeNetworkManager
# ============================================================


class TestComposeNetworkManager:
    """Test network creation, service-to-network mapping, and cleanup."""

    def test_create_network(self, network_manager):
        """Creating a network returns a network ID."""
        config = NetworkConfig(name="test-net")
        net_id = network_manager.create_network(config)
        assert net_id.startswith("net-test-net-")
        assert network_manager.get_network_id("test-net") == net_id

    def test_connect_and_resolve_dns(self, network_manager):
        """Connecting a service allocates an IP and enables DNS resolution."""
        config = NetworkConfig(name="app-net")
        network_manager.create_network(config)
        ip = network_manager.connect_service("app-net", "web", "web-0")
        assert ip is not None
        resolved = network_manager.resolve_dns("app-net", "web")
        assert resolved == ip

    def test_cleanup_removes_all(self, network_manager):
        """Cleanup removes all managed networks."""
        network_manager.create_network(NetworkConfig(name="net-1"))
        network_manager.create_network(NetworkConfig(name="net-2"))
        network_manager.cleanup()
        assert len(network_manager.get_all_networks()) == 0


# ============================================================
# TestComposeVolumeManager
# ============================================================


class TestComposeVolumeManager:
    """Test named volume creation, bind mount resolution, and cleanup."""

    def test_create_volume(self, volume_manager):
        """Creating a volume returns a path."""
        config = VolumeConfig(name="data-vol")
        path = volume_manager.create_volume(config)
        assert "data-vol" in path
        assert volume_manager.get_volume_path("data-vol") == path

    def test_mount_and_unmount(self, volume_manager):
        """Mounting a volume into a service records the mount point."""
        volume_manager.create_volume(VolumeConfig(name="shared"))
        path = volume_manager.mount_volume("shared", "web", "/app/data")
        assert path is not None
        mounts = volume_manager.get_mount_points("shared")
        assert "web" in mounts
        volume_manager.unmount_volume("shared", "web")
        mounts = volume_manager.get_mount_points("shared")
        assert "web" not in mounts

    def test_cleanup_removes_all(self, volume_manager):
        """Cleanup removes all managed volumes."""
        volume_manager.create_volume(VolumeConfig(name="vol-1"))
        volume_manager.create_volume(VolumeConfig(name="vol-2"))
        volume_manager.cleanup()
        assert len(volume_manager.get_all_volumes()) == 0


# ============================================================
# TestRestartPolicyEngine
# ============================================================


class TestRestartPolicyEngine:
    """Test policy evaluation for all four restart conditions."""

    def test_no_policy_never_restarts(self, restart_engine):
        """RestartPolicy.NO never triggers a restart."""
        policy = RestartPolicySpec(condition=RestartPolicy.NO)
        assert restart_engine.should_restart("svc", policy, exit_code=1) is False

    def test_always_restarts_on_success(self, restart_engine):
        """RestartPolicy.ALWAYS restarts even on exit code 0."""
        policy = RestartPolicySpec(condition=RestartPolicy.ALWAYS, max_attempts=10)
        assert restart_engine.should_restart("svc", policy, exit_code=0) is True

    def test_on_failure_ignores_success(self, restart_engine):
        """RestartPolicy.ON_FAILURE does not restart on exit code 0."""
        policy = RestartPolicySpec(condition=RestartPolicy.ON_FAILURE)
        assert restart_engine.should_restart("svc", policy, exit_code=0) is False
        assert restart_engine.should_restart("svc", policy, exit_code=1) is True

    def test_unless_stopped_respects_manual(self, restart_engine):
        """RestartPolicy.UNLESS_STOPPED does not restart manually stopped containers."""
        policy = RestartPolicySpec(condition=RestartPolicy.UNLESS_STOPPED, max_attempts=10)
        assert restart_engine.should_restart(
            "svc", policy, exit_code=1, manually_stopped=True
        ) is False
        assert restart_engine.should_restart(
            "svc", policy, exit_code=1, manually_stopped=False
        ) is True

    def test_max_attempts_exhaustion(self, restart_engine):
        """Exceeding max_attempts raises ComposeRestartPolicyExhaustedError."""
        policy = RestartPolicySpec(
            condition=RestartPolicy.ALWAYS,
            max_attempts=2,
            window=3600.0,
        )
        restart_engine.should_restart("svc", policy, exit_code=1)
        restart_engine.record_restart("svc")
        restart_engine.should_restart("svc", policy, exit_code=1)
        restart_engine.record_restart("svc")
        with pytest.raises(ComposeRestartPolicyExhaustedError):
            restart_engine.should_restart("svc", policy, exit_code=1)


# ============================================================
# TestHealthCheckGate
# ============================================================


class TestHealthCheckGate:
    """Test health check execution, timeout detection, and success polling."""

    def test_healthy_running_instance(self, health_check_gate):
        """A running instance passes its health check."""
        instance = ServiceInstance(
            instance_id="hc-1",
            service_name="test",
            state=ServiceState.RUNNING,
            started_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        result = health_check_gate.check("test", instance, HealthCheckSpec())
        assert result is True
        assert health_check_gate.pass_count >= 1

    def test_stopped_instance_fails(self, health_check_gate):
        """A stopped instance fails its health check."""
        instance = ServiceInstance(
            instance_id="hc-2",
            service_name="test",
            state=ServiceState.STOPPED,
        )
        result = health_check_gate.check("test", instance, HealthCheckSpec())
        assert result is False
        assert health_check_gate.fail_count >= 1

    def test_none_health_check_always_passes(self, health_check_gate):
        """HealthCheckType.NONE always returns True."""
        instance = ServiceInstance(
            instance_id="hc-3",
            service_name="test",
            state=ServiceState.STOPPED,
        )
        spec = HealthCheckSpec(check_type=HealthCheckType.NONE)
        result = health_check_gate.check("test", instance, spec)
        assert result is True


# ============================================================
# TestFizzComposeMiddleware
# ============================================================


class TestFizzComposeMiddleware:
    """Test middleware process delegation, topology attachment, and dashboard."""

    def test_process_attaches_metadata(self, compose_engine, context):
        """Middleware attaches compose topology to context metadata."""
        compose_engine.up()
        middleware = FizzComposeMiddleware(engine=compose_engine)

        def next_handler(ctx):
            return ctx

        result = middleware.process(context, next_handler)
        assert result.metadata.get("compose_project") == COMPOSE_PROJECT_NAME
        assert result.metadata.get("compose_status") == "running"
        assert result.metadata.get("compose_services") == SERVICE_GROUP_COUNT
        compose_engine.down()

    def test_process_increments_count(self, compose_engine, context):
        """Middleware increments evaluation count on each call."""
        middleware = FizzComposeMiddleware(engine=compose_engine)

        def next_handler(ctx):
            return ctx

        middleware.process(context, next_handler)
        middleware.process(context, next_handler)
        assert middleware.evaluation_count == 2

    def test_middleware_priority_and_name(self, compose_engine):
        """Middleware reports correct name and priority."""
        middleware = FizzComposeMiddleware(engine=compose_engine)
        assert middleware.get_name() == "FizzComposeMiddleware"
        assert middleware.get_priority() == MIDDLEWARE_PRIORITY
        assert middleware.priority == MIDDLEWARE_PRIORITY
        assert middleware.name == "FizzComposeMiddleware"


# ============================================================
# TestComposeDashboard
# ============================================================


class TestComposeDashboard:
    """Test ASCII table rendering and resource utilization bar chart."""

    def test_dashboard_render_no_project(self, compose_engine):
        """Dashboard renders a message when no project is running."""
        dashboard = ComposeDashboard()
        output = dashboard.render(compose_engine)
        assert "No compose project is running" in output

    def test_dashboard_render_running(self, running_engine):
        """Dashboard renders service table and resource bars when running."""
        dashboard = ComposeDashboard()
        output = dashboard.render(running_engine)
        assert "FizzCompose Dashboard" in output
        assert "fizzbuzz-core" in output
        assert "fizzbuzz-platform" in output
        assert running_engine.get_project().name in output


# ============================================================
# TestComposeServiceGroups
# ============================================================


class TestComposeServiceGroups:
    """Test all 12 service groups are defined with correct module mappings."""

    def test_all_groups_defined(self):
        """All 12 service groups are present."""
        groups = ComposeServiceGroup.get_all_groups()
        assert len(groups) == SERVICE_GROUP_COUNT

    def test_module_to_group_mapping(self):
        """Modules can be looked up to find their containing group."""
        group = ComposeServiceGroup.find_group_for_module("rule_engine")
        assert group == "fizzbuzz-core"

        group = ComposeServiceGroup.find_group_for_module("mesi_cache_coherence")
        assert group == "fizzbuzz-cache"

        group = ComposeServiceGroup.find_group_for_module("ray_tracer")
        assert group == "fizzbuzz-exotic"

        # Non-existent module
        group = ComposeServiceGroup.find_group_for_module("nonexistent_module")
        assert group is None

    def test_group_modules_list(self):
        """Each group has a non-empty modules list."""
        for name in ComposeServiceGroup.get_group_names():
            modules = ComposeServiceGroup.get_modules_for_group(name)
            assert len(modules) > 0

    def test_platform_has_no_dependencies(self):
        """fizzbuzz-platform group has no dependencies (starts first)."""
        group = ComposeServiceGroup.get_group("fizzbuzz-platform")
        assert len(group["depends_on"]) == 0


# ============================================================
# TestComposeExceptions
# ============================================================


class TestComposeExceptions:
    """Test error code format, context population, and inheritance chain."""

    def test_error_code_format(self):
        """All exception error codes follow EFP-CMP## format."""
        exc = ComposeError("test")
        assert exc.error_code == "EFP-CMP00"

        exc = ComposeFileNotFoundError("/path")
        assert exc.error_code == "EFP-CMP01"

        exc = ComposeCircularDependencyError(["a", "b", "a"])
        assert exc.error_code == "EFP-CMP04"

        exc = ComposeMiddlewareError("test")
        assert exc.error_code == "EFP-CMP20"

    def test_context_population(self):
        """Exception context dictionaries are populated correctly."""
        exc = ComposeServiceNotFoundError("test-svc")
        assert exc.context["service_name"] == "test-svc"

        exc = ComposePortConflictError(8080, "web", "api")
        assert exc.context["port"] == 8080
        assert exc.context["service_a"] == "web"
        assert exc.context["service_b"] == "api"

    def test_inheritance_chain(self):
        """All compose exceptions inherit from ComposeError."""
        exceptions = [
            ComposeFileNotFoundError("/path"),
            ComposeFileParseError("/path", "reason"),
            ComposeVariableInterpolationError("VAR", "reason"),
            ComposeCircularDependencyError(["a", "b"]),
            ComposeServiceNotFoundError("svc"),
            ComposeServiceStartError("svc", "reason"),
            ComposeServiceStopError("svc", "reason"),
            ComposeHealthCheckTimeoutError("svc", 60.0),
            ComposeNetworkCreateError("net", "reason"),
            ComposeNetworkNotFoundError("svc", "net"),
            ComposeVolumeCreateError("vol", "reason"),
            ComposeVolumeNotFoundError("svc", "vol"),
            ComposeScaleError("svc", 5, "reason"),
            ComposeExecError("svc", "cmd", "reason"),
            ComposeRestartError("svc", "reason"),
            ComposeRestartPolicyExhaustedError("svc", 5),
            ComposePortConflictError(8080, "a", "b"),
            ComposeImageNotFoundError("svc", "img"),
            ComposeProjectAlreadyRunningError("proj"),
            ComposeMiddlewareError("reason"),
        ]
        for exc in exceptions:
            assert isinstance(exc, ComposeError)
            assert isinstance(exc, Exception)


# ============================================================
# TestCreateFizzcomposeSubsystem
# ============================================================


class TestCreateFizzcomposeSubsystem:
    """Test factory function wiring and return types."""

    def test_factory_returns_tuple(self):
        """Factory function returns (ComposeEngine, FizzComposeMiddleware)."""
        engine, middleware = create_fizzcompose_subsystem()
        assert isinstance(engine, ComposeEngine)
        assert isinstance(middleware, FizzComposeMiddleware)

    def test_factory_middleware_properties(self):
        """Factory-created middleware has correct name and priority."""
        engine, middleware = create_fizzcompose_subsystem()
        assert middleware.get_name() == "FizzComposeMiddleware"
        assert middleware.get_priority() == MIDDLEWARE_PRIORITY

    def test_factory_with_custom_params(self):
        """Factory accepts custom configuration parameters."""
        engine, middleware = create_fizzcompose_subsystem(
            scale_max=20,
            dashboard_width=100,
            enable_dashboard=True,
        )
        assert isinstance(engine, ComposeEngine)
        assert middleware._enable_dashboard is True


# ============================================================
# TestComposeConstants
# ============================================================


class TestComposeConstants:
    """Validate module-level constants."""

    def test_compose_version(self):
        assert COMPOSE_VERSION == "3.8"

    def test_service_group_count(self):
        assert SERVICE_GROUP_COUNT == 12

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 115

    def test_default_scale_max(self):
        assert DEFAULT_SCALE_MAX == 10

    def test_default_network_subnet(self):
        assert DEFAULT_NETWORK_SUBNET == "172.28.0.0/16"


# ============================================================
# TestComposeEventTypes
# ============================================================


class TestComposeEventTypes:
    """Validate event type constants."""

    def test_event_type_strings(self):
        assert COMPOSE_UP_STARTED == "compose.up.started"
        assert COMPOSE_UP_COMPLETED == "compose.up.completed"

    def test_event_bus_integration(self, compose_engine):
        """Events are emitted to the event bus when provided."""
        event_bus = MagicMock()
        engine = ComposeEngine(
            parser=ComposeParser(),
            network_manager=ComposeNetworkManager(),
            volume_manager=ComposeVolumeManager(),
            dependency_resolver=DependencyResolver(),
            restart_policy_engine=RestartPolicyEngine(),
            health_check_gate=HealthCheckGate(),
            event_bus=event_bus,
        )
        engine.up()
        assert event_bus.publish.called
        engine.down()


# ============================================================
# TestDependencyConditionChecking
# ============================================================


class TestDependencyConditionChecking:
    """Test DependencyResolver.check_dependency_satisfied for all conditions."""

    def test_service_started_running(self, dependency_resolver):
        """SERVICE_STARTED is satisfied by RUNNING state."""
        instance = ServiceInstance(
            instance_id="dep-1",
            service_name="test",
            state=ServiceState.RUNNING,
        )
        assert dependency_resolver.check_dependency_satisfied(
            DependencyCondition.SERVICE_STARTED, instance
        ) is True

    def test_service_healthy_requires_healthy(self, dependency_resolver):
        """SERVICE_HEALTHY requires HEALTHY state specifically."""
        running = ServiceInstance(
            instance_id="dep-2",
            service_name="test",
            state=ServiceState.RUNNING,
        )
        healthy = ServiceInstance(
            instance_id="dep-3",
            service_name="test",
            state=ServiceState.HEALTHY,
        )
        assert dependency_resolver.check_dependency_satisfied(
            DependencyCondition.SERVICE_HEALTHY, running
        ) is False
        assert dependency_resolver.check_dependency_satisfied(
            DependencyCondition.SERVICE_HEALTHY, healthy
        ) is True

    def test_completed_successfully(self, dependency_resolver):
        """SERVICE_COMPLETED_SUCCESSFULLY requires COMPLETED state with exit_code 0."""
        instance = ServiceInstance(
            instance_id="dep-4",
            service_name="test",
            state=ServiceState.COMPLETED,
            exit_code=0,
        )
        assert dependency_resolver.check_dependency_satisfied(
            DependencyCondition.SERVICE_COMPLETED_SUCCESSFULLY, instance
        ) is True

        failed = ServiceInstance(
            instance_id="dep-5",
            service_name="test",
            state=ServiceState.COMPLETED,
            exit_code=1,
        )
        assert dependency_resolver.check_dependency_satisfied(
            DependencyCondition.SERVICE_COMPLETED_SUCCESSFULLY, failed
        ) is False


# ============================================================
# TestComposeParserValidation
# ============================================================


class TestComposeParserValidation:
    """Test compose file reference validation."""

    def test_validate_undefined_dependency(self, parser):
        """Validation catches references to undefined services in depends_on."""
        compose_file = ComposeFile(services={
            "app": ServiceDefinition(
                name="app",
                depends_on=[DependencySpec(service="nonexistent")],
            ),
        })
        errors = parser.validate_references(compose_file)
        assert len(errors) > 0
        assert "nonexistent" in errors[0]

    def test_validate_valid_file(self, parser):
        """Validation passes for a correctly defined compose file."""
        compose_file = parser.parse()
        errors = parser.validate_references(compose_file)
        assert len(errors) == 0
