"""
Enterprise FizzBuzz Platform - FizzCompose: Multi-Container Application Orchestration

A Docker Compose-style declarative multi-service application orchestrator that
manages the full lifecycle of containerized FizzBuzz service groups.  The engine
parses fizzbuzz-compose.yaml definitions, resolves inter-service dependencies
via Kahn's algorithm topological sort, provisions compose-scoped networks and
volumes, enforces restart policies, and executes health-check-gated startup
sequences.

The platform decomposes 116 infrastructure modules into 12 logical service
groups (core, data, cache, network, security, observability, compute, devtools,
platform, enterprise, ops, exotic), each deployable as an independent
containerized service.  The dependency graph ensures services start in the
correct order: platform-level services first, then data and network, then
cache and security, and so on through the stack.

Lifecycle commands mirror Docker Compose: up (start all services in dependency
order), down (tear down in reverse order), restart (restart individual
services), scale (adjust replica counts), logs (stream service logs), ps (show
service status), exec (run commands in containers), and top (show running
processes).

The ComposeParser validates compose file structure, resolves variable
interpolation (${VARIABLE:-default} syntax), and detects circular dependencies
before any containers are created.  The DependencyResolver implements Kahn's
algorithm for topological sorting with three dependency conditions:
service_started, service_healthy, and service_completed_successfully.

Architecture reference: Docker Compose Specification v3.8
(https://docs.docker.com/compose/compose-file/)
"""

from __future__ import annotations

import copy
import hashlib
import logging
import math
import random
import re
import threading
import time
import uuid
from collections import defaultdict, deque, OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
)

logger = logging.getLogger("enterprise_fizzbuzz.fizzcompose")


# ============================================================
# Event Type Constants (module-level strings)
# ============================================================

COMPOSE_UP_STARTED = "compose.up.started"
"""Event emitted when compose up begins."""

COMPOSE_UP_COMPLETED = "compose.up.completed"
"""Event emitted when all services are running."""

COMPOSE_DOWN_STARTED = "compose.down.started"
"""Event emitted when compose down begins."""

COMPOSE_DOWN_COMPLETED = "compose.down.completed"
"""Event emitted when all services are torn down."""

COMPOSE_SERVICE_STARTING = "compose.service.starting"
"""Event emitted when a service begins starting."""

COMPOSE_SERVICE_STARTED = "compose.service.started"
"""Event emitted when a service has started."""

COMPOSE_SERVICE_HEALTHY = "compose.service.healthy"
"""Event emitted when a service passes its health check."""

COMPOSE_SERVICE_UNHEALTHY = "compose.service.unhealthy"
"""Event emitted when a service fails its health check."""

COMPOSE_SERVICE_STOPPED = "compose.service.stopped"
"""Event emitted when a service has stopped."""

COMPOSE_SERVICE_RESTARTED = "compose.service.restarted"
"""Event emitted when a service has been restarted."""

COMPOSE_SERVICE_SCALED = "compose.service.scaled"
"""Event emitted when a service replica count changes."""

COMPOSE_DEPENDENCY_RESOLVED = "compose.dependency.resolved"
"""Event emitted when a dependency condition is satisfied."""

COMPOSE_NETWORK_CREATED = "compose.network.created"
"""Event emitted when a compose-scoped network is provisioned."""

COMPOSE_VOLUME_CREATED = "compose.volume.created"
"""Event emitted when a compose-scoped volume is provisioned."""

COMPOSE_DASHBOARD_RENDERED = "compose.dashboard.rendered"
"""Event emitted when the ASCII dashboard is rendered."""


# ============================================================
# Exception Classes (defined within the module)
# ============================================================


class ComposeError(Exception):
    """Base exception for FizzCompose multi-container orchestration errors.

    All exceptions originating from the compose engine inherit from
    this class.  The compose system manages declarative multi-service
    application topology, dependency resolution, lifecycle orchestration,
    network provisioning, volume management, and restart policy enforcement
    for the containerized Enterprise FizzBuzz Platform.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CMP00"
        self.context: Dict[str, Any] = {"reason": reason}


class ComposeFileNotFoundError(ComposeError):
    """Raised when the compose file cannot be located.

    The compose engine requires a fizzbuzz-compose.yaml file to define
    the application topology.  Without it, the engine has no services
    to orchestrate, no networks to create, and no volumes to provision.
    The platform's 12 service groups remain undefined, and 116
    infrastructure modules continue their unsupervised cohabitation
    in a single process.
    """

    def __init__(self, file_path: str) -> None:
        super().__init__(
            f"Compose file not found at '{file_path}'. The application "
            f"topology is undefined. Without a compose file, the platform "
            f"cannot be decomposed into containerized services."
        )
        self.error_code = "EFP-CMP01"
        self.context = {"file_path": file_path}


class ComposeFileParseError(ComposeError):
    """Raised when the compose file contains invalid YAML or schema violations.

    The compose file must conform to the compose schema.  Invalid YAML
    syntax, missing required fields, unrecognized keys, or type mismatches
    all trigger this exception.  The parser has standards, and the YAML
    has failed to meet them.
    """

    def __init__(self, file_path: str, reason: str) -> None:
        super().__init__(
            f"Failed to parse compose file '{file_path}': {reason}. "
            f"The file's YAML structure does not conform to the compose "
            f"schema specification."
        )
        self.error_code = "EFP-CMP02"
        self.context = {"file_path": file_path, "reason": reason}


class ComposeVariableInterpolationError(ComposeError):
    """Raised when variable interpolation in the compose file fails.

    Compose files support ${VARIABLE:-default} interpolation syntax.
    This exception is raised when a referenced variable is not set
    and no default value is provided, or when the interpolation
    syntax is malformed.
    """

    def __init__(self, variable: str, reason: str) -> None:
        super().__init__(
            f"Variable interpolation failed for '${{{variable}}}': {reason}. "
            f"The variable is either unset without a default or the "
            f"interpolation syntax is malformed."
        )
        self.error_code = "EFP-CMP03"
        self.context = {"variable": variable, "reason": reason}


class ComposeCircularDependencyError(ComposeError):
    """Raised when the service dependency graph contains a cycle.

    Kahn's algorithm detected a cycle in the depends_on graph.
    Topological sort is impossible when services form a dependency
    loop.  The affected services cannot determine which should start
    first because each waits for another in a closed chain.
    """

    def __init__(self, cycle: List[str]) -> None:
        cycle_str = " -> ".join(cycle)
        super().__init__(
            f"Circular dependency detected in compose file: {cycle_str}. "
            f"Topological sort is impossible. Break the cycle by removing "
            f"or restructuring service dependencies."
        )
        self.error_code = "EFP-CMP04"
        self.context = {"cycle": cycle}


class ComposeServiceNotFoundError(ComposeError):
    """Raised when a referenced service does not exist in the compose file.

    A lifecycle command (restart, scale, logs, exec, top) targeted a
    service that is not defined in the compose file.  The service name
    may be misspelled, or the service may have been removed from the
    compose file after the project was started.
    """

    def __init__(self, service_name: str) -> None:
        super().__init__(
            f"Service '{service_name}' not found in compose file. "
            f"Available services are defined in the services section "
            f"of fizzbuzz-compose.yaml."
        )
        self.error_code = "EFP-CMP05"
        self.context = {"service_name": service_name}


class ComposeServiceStartError(ComposeError):
    """Raised when a service fails to start.

    The compose engine attempted to create and start containers for
    a service, but the operation failed.  Possible causes include
    image pull failures, resource limit violations, port conflicts,
    or container runtime errors.
    """

    def __init__(self, service_name: str, reason: str) -> None:
        super().__init__(
            f"Failed to start service '{service_name}': {reason}. "
            f"The service's containers could not be created or started."
        )
        self.error_code = "EFP-CMP06"
        self.context = {"service_name": service_name, "reason": reason}


class ComposeServiceStopError(ComposeError):
    """Raised when a service fails to stop gracefully.

    The compose engine sent a stop signal to the service's containers,
    but they did not terminate within the grace period.  Containers
    that refuse to stop are forcefully killed, and this exception
    records the failure.
    """

    def __init__(self, service_name: str, reason: str) -> None:
        super().__init__(
            f"Failed to stop service '{service_name}' gracefully: {reason}. "
            f"The service's containers did not terminate within the "
            f"configured grace period."
        )
        self.error_code = "EFP-CMP07"
        self.context = {"service_name": service_name, "reason": reason}


class ComposeHealthCheckTimeoutError(ComposeError):
    """Raised when a service fails to become healthy within the timeout.

    A dependent service is waiting for this service to pass its
    health check, but the health check has not succeeded within the
    configured timeout period.  The compose-up operation cannot
    proceed until all health-check-gated dependencies are satisfied.
    """

    def __init__(self, service_name: str, timeout: float) -> None:
        super().__init__(
            f"Service '{service_name}' did not become healthy within "
            f"{timeout:.0f} seconds. Dependent services cannot start "
            f"until this service passes its health check."
        )
        self.error_code = "EFP-CMP08"
        self.context = {"service_name": service_name, "timeout": timeout}


class ComposeNetworkCreateError(ComposeError):
    """Raised when a compose-scoped network cannot be created.

    Network creation via FizzCNI failed.  Possible causes include
    subnet conflicts, driver unavailability, or IPAM allocation
    failures.
    """

    def __init__(self, network_name: str, reason: str) -> None:
        super().__init__(
            f"Failed to create network '{network_name}': {reason}. "
            f"The compose-scoped network could not be provisioned."
        )
        self.error_code = "EFP-CMP09"
        self.context = {"network_name": network_name, "reason": reason}


class ComposeNetworkNotFoundError(ComposeError):
    """Raised when a service references a network not defined in the compose file.

    A service's networks list includes a network name that does not
    appear in the top-level networks section of the compose file.
    """

    def __init__(self, service_name: str, network_name: str) -> None:
        super().__init__(
            f"Service '{service_name}' references undefined network "
            f"'{network_name}'. Define the network in the top-level "
            f"networks section of the compose file."
        )
        self.error_code = "EFP-CMP10"
        self.context = {"service_name": service_name, "network_name": network_name}


class ComposeVolumeCreateError(ComposeError):
    """Raised when a compose-scoped volume cannot be created.

    Volume creation via FizzOverlay failed.  Possible causes include
    storage exhaustion, driver errors, or permission failures.
    """

    def __init__(self, volume_name: str, reason: str) -> None:
        super().__init__(
            f"Failed to create volume '{volume_name}': {reason}. "
            f"The compose-scoped volume could not be provisioned."
        )
        self.error_code = "EFP-CMP11"
        self.context = {"volume_name": volume_name, "reason": reason}


class ComposeVolumeNotFoundError(ComposeError):
    """Raised when a service references a volume not defined in the compose file.

    A service's volumes list includes a named volume that does not
    appear in the top-level volumes section of the compose file and
    is not a bind mount path.
    """

    def __init__(self, service_name: str, volume_name: str) -> None:
        super().__init__(
            f"Service '{service_name}' references undefined volume "
            f"'{volume_name}'. Define the volume in the top-level "
            f"volumes section of the compose file, or use a bind mount."
        )
        self.error_code = "EFP-CMP12"
        self.context = {"service_name": service_name, "volume_name": volume_name}


class ComposeScaleError(ComposeError):
    """Raised when a scale operation fails.

    The compose engine attempted to adjust the replica count for a
    service but encountered an error.  Possible causes include
    exceeding the maximum replica count, resource exhaustion, or
    container creation failures.
    """

    def __init__(self, service_name: str, desired: int, reason: str) -> None:
        super().__init__(
            f"Failed to scale service '{service_name}' to {desired} "
            f"replicas: {reason}."
        )
        self.error_code = "EFP-CMP13"
        self.context = {"service_name": service_name, "desired": desired, "reason": reason}


class ComposeExecError(ComposeError):
    """Raised when exec into a service container fails.

    The compose engine attempted to execute a command inside a
    running service container via FizzContainerd's exec capability,
    but the operation failed.
    """

    def __init__(self, service_name: str, command: str, reason: str) -> None:
        super().__init__(
            f"Failed to exec '{command}' in service '{service_name}': "
            f"{reason}."
        )
        self.error_code = "EFP-CMP14"
        self.context = {"service_name": service_name, "command": command, "reason": reason}


class ComposeRestartError(ComposeError):
    """Raised when a service restart operation fails.

    The compose engine attempted to restart a service but could not
    stop the existing containers or start new ones.
    """

    def __init__(self, service_name: str, reason: str) -> None:
        super().__init__(
            f"Failed to restart service '{service_name}': {reason}."
        )
        self.error_code = "EFP-CMP15"
        self.context = {"service_name": service_name, "reason": reason}


class ComposeRestartPolicyExhaustedError(ComposeError):
    """Raised when a service has exhausted its restart attempts.

    The restart policy engine has restarted the service the maximum
    number of times within the configured window.  No further restart
    attempts will be made until the window resets or the operator
    intervenes.
    """

    def __init__(self, service_name: str, max_attempts: int) -> None:
        super().__init__(
            f"Service '{service_name}' has exhausted its restart policy "
            f"({max_attempts} attempts). No further automatic restarts "
            f"will be attempted."
        )
        self.error_code = "EFP-CMP16"
        self.context = {"service_name": service_name, "max_attempts": max_attempts}


class ComposePortConflictError(ComposeError):
    """Raised when two services attempt to bind the same host port.

    Port mappings must be unique across all services in the compose
    project.  Two services cannot bind the same host port on the
    same host IP.
    """

    def __init__(self, port: int, service_a: str, service_b: str) -> None:
        super().__init__(
            f"Port conflict: host port {port} is claimed by both "
            f"'{service_a}' and '{service_b}'. Each host port can "
            f"only be bound by a single service."
        )
        self.error_code = "EFP-CMP17"
        self.context = {"port": port, "service_a": service_a, "service_b": service_b}


class ComposeImageNotFoundError(ComposeError):
    """Raised when a service's image cannot be found in the FizzImage catalog.

    The service definition references an image that does not exist
    in the FizzImage catalog and no build context is provided.
    """

    def __init__(self, service_name: str, image: str) -> None:
        super().__init__(
            f"Image '{image}' for service '{service_name}' not found "
            f"in the FizzImage catalog. Provide a build context or "
            f"ensure the image exists in the catalog."
        )
        self.error_code = "EFP-CMP18"
        self.context = {"service_name": service_name, "image": image}


class ComposeProjectAlreadyRunningError(ComposeError):
    """Raised when compose up is called on an already-running project.

    The compose project is already running.  Use compose down first
    to tear down the existing deployment, or use compose restart to
    restart individual services.
    """

    def __init__(self, project_name: str) -> None:
        super().__init__(
            f"Compose project '{project_name}' is already running. "
            f"Use 'compose down' to tear down the existing deployment "
            f"before starting a new one."
        )
        self.error_code = "EFP-CMP19"
        self.context = {"project_name": project_name}


class ComposeMiddlewareError(ComposeError):
    """Raised when the FizzCompose middleware encounters an error during evaluation.

    The middleware attempted to resolve the compose application topology
    for service discovery during FizzBuzz evaluation, but the topology
    is unavailable or inconsistent.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzCompose middleware error: {reason}. The compose "
            f"application topology could not be resolved for this "
            f"evaluation."
        )
        self.error_code = "EFP-CMP20"
        self.context = {"reason": reason}


# ============================================================
# Constants
# ============================================================

COMPOSE_VERSION = "3.8"
"""Compose file format version."""

COMPOSE_FILE_NAME = "fizzbuzz-compose.yaml"
"""Default compose file name."""

COMPOSE_PROJECT_NAME = "fizzbuzz"
"""Default compose project name."""

DEFAULT_HEALTH_CHECK_INTERVAL = 2.0
"""Default interval between health check polls in seconds."""

DEFAULT_HEALTH_CHECK_TIMEOUT = 60.0
"""Default timeout for a dependency health check gate in seconds."""

DEFAULT_RESTART_DELAY = 5.0
"""Default delay between restart attempts in seconds."""

DEFAULT_RESTART_WINDOW = 120.0
"""Default time window for resetting restart attempt counter."""

DEFAULT_MAX_RESTART_ATTEMPTS = 5
"""Maximum restart attempts before giving up."""

DEFAULT_LOG_TAIL_LINES = 100
"""Default number of log lines to display."""

DEFAULT_SCALE_MAX = 10
"""Maximum replica count per service."""

COMPOSE_DASHBOARD_WIDTH = 76
"""Default width for ASCII dashboard rendering."""

SERVICE_GROUP_COUNT = 12
"""Number of logical service groups in the default compose topology."""

MIDDLEWARE_PRIORITY = 115
"""Middleware pipeline priority for FizzCompose."""

DEFAULT_NETWORK_SUBNET = "172.28.0.0/16"
"""Default subnet for compose-scoped networks."""

DEFAULT_NETWORK_GATEWAY = "172.28.0.1"
"""Default gateway for compose-scoped networks."""

DEFAULT_STOP_TIMEOUT = 10.0
"""Default timeout in seconds for graceful service stop."""

DEFAULT_CONTAINER_PORT_BASE = 8000
"""Base port number for auto-assigned container ports."""

VARIABLE_INTERPOLATION_PATTERN = re.compile(
    r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-(.*?))?\}"
)
"""Regex pattern for ${VARIABLE:-default} interpolation syntax."""


# ============================================================
# Enums
# ============================================================


class ComposeStatus(Enum):
    """Status of the compose application as a whole.

    The compose project transitions through these states during
    its lifecycle.  A project starts STOPPED, moves to STARTING
    during compose-up, reaches RUNNING when all services are up,
    and returns to STOPPED after compose-down.
    """

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PARTIALLY_RUNNING = "partially_running"
    STOPPING = "stopping"
    ERROR = "error"


class ServiceState(Enum):
    """Lifecycle state of an individual compose service.

    Services progress through states as the compose engine
    manages their containers.  Health check results determine
    whether a running service is classified as HEALTHY or
    UNHEALTHY.
    """

    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    RESTARTING = "restarting"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"
    COMPLETED = "completed"


class DependencyCondition(Enum):
    """Condition under which a service dependency is considered satisfied.

    Three dependency modes exist: service_started (container is running),
    service_healthy (container passes health check), and
    service_completed_successfully (container exited with code 0).
    """

    SERVICE_STARTED = "service_started"
    SERVICE_HEALTHY = "service_healthy"
    SERVICE_COMPLETED_SUCCESSFULLY = "service_completed_successfully"


class RestartPolicy(Enum):
    """Container restart policy for a compose service.

    Controls whether and when a stopped container is automatically
    restarted by the restart policy engine.
    """

    NO = "no"
    ALWAYS = "always"
    ON_FAILURE = "on-failure"
    UNLESS_STOPPED = "unless-stopped"


class VolumeType(Enum):
    """Type of volume mount in a compose service.

    Named volumes are managed by the volume manager, bind mounts
    map host paths into the container, and tmpfs mounts provide
    ephemeral in-memory storage.
    """

    NAMED = "named"
    BIND = "bind"
    TMPFS = "tmpfs"


class NetworkDriver(Enum):
    """Network driver for a compose-scoped network.

    Bridge networks provide isolated communication between containers
    on the same host.  Host networking shares the host's network
    namespace.  Overlay networks span multiple hosts.  None disables
    networking entirely.
    """

    BRIDGE = "bridge"
    HOST = "host"
    OVERLAY = "overlay"
    NONE = "none"


class ComposeCommand(Enum):
    """Lifecycle commands supported by the compose engine.

    Each command maps to a specific orchestration operation that
    affects services, networks, or volumes in the compose project.
    """

    UP = "up"
    DOWN = "down"
    RESTART = "restart"
    SCALE = "scale"
    LOGS = "logs"
    PS = "ps"
    EXEC = "exec"
    TOP = "top"
    CONFIG = "config"


class HealthCheckType(Enum):
    """Type of health check probe.

    CMD executes a command and checks the exit code.  CMD_SHELL
    wraps the command in a shell.  HTTP performs an HTTP GET.
    TCP attempts a TCP connection.  NONE disables health checks.
    """

    CMD = "CMD"
    CMD_SHELL = "CMD-SHELL"
    HTTP = "HTTP"
    TCP = "TCP"
    NONE = "NONE"


# ============================================================
# Data Classes
# ============================================================


@dataclass
class NetworkConfig:
    """Configuration for a compose-scoped network.

    Defines the network driver, CIDR subnet, gateway, and IPAM
    settings for a network that connects compose services.

    Attributes:
        name: Network name.
        driver: Network driver (bridge, host, overlay, none).
        subnet: CIDR subnet for the network.
        gateway: Gateway IP address.
        ipam_driver: IPAM driver name.
        labels: Key-value metadata labels.
        internal: Whether the network is internal-only (no external access).
        enable_ipv6: Whether IPv6 is enabled.
    """

    name: str
    driver: NetworkDriver = NetworkDriver.BRIDGE
    subnet: str = "172.28.0.0/16"
    gateway: str = "172.28.0.1"
    ipam_driver: str = "default"
    labels: Dict[str, str] = field(default_factory=dict)
    internal: bool = False
    enable_ipv6: bool = False


@dataclass
class VolumeConfig:
    """Configuration for a compose-scoped named volume.

    Volumes provide persistent storage that survives container
    restarts and can be shared between services.

    Attributes:
        name: Volume name.
        driver: Volume driver.
        driver_opts: Driver-specific options.
        labels: Key-value metadata labels.
        external: Whether the volume is externally managed.
    """

    name: str
    driver: str = "local"
    driver_opts: Dict[str, str] = field(default_factory=dict)
    labels: Dict[str, str] = field(default_factory=dict)
    external: bool = False


@dataclass
class PortMapping:
    """Port mapping from host to container.

    Maps a port on the host to a port inside the container,
    enabling external access to containerized services.

    Attributes:
        host_port: Port on the host.
        container_port: Port inside the container.
        protocol: Transport protocol (tcp or udp).
        host_ip: Host IP to bind to.
    """

    host_port: int
    container_port: int
    protocol: str = "tcp"
    host_ip: str = "0.0.0.0"


@dataclass
class EnvironmentSpec:
    """Environment variable specification for a service.

    Combines inline key-value variables with references to
    external env files for flexible configuration injection.

    Attributes:
        variables: Key-value environment variables.
        env_files: List of env file paths.
    """

    variables: Dict[str, str] = field(default_factory=dict)
    env_files: List[str] = field(default_factory=list)


@dataclass
class ResourceLimits:
    """Resource limits and reservations for a service.

    Controls CPU, memory, and process limits to prevent
    resource exhaustion and ensure fair scheduling among
    compose services.

    Attributes:
        cpu_limit: CPU limit (e.g., 0.5 for half a core).
        memory_limit: Memory limit in bytes.
        cpu_reservation: CPU reservation.
        memory_reservation: Memory reservation in bytes.
        pids_limit: Maximum number of processes.
    """

    cpu_limit: float = 1.0
    memory_limit: int = 536870912  # 512 MB
    cpu_reservation: float = 0.25
    memory_reservation: int = 134217728  # 128 MB
    pids_limit: int = 256


@dataclass
class HealthCheckSpec:
    """Health check specification for a service.

    Defines how the health check gate probes a service to
    determine whether it is ready to accept traffic from
    dependent services.

    Attributes:
        check_type: Type of health check probe.
        command: Command to execute (for CMD/CMD-SHELL types).
        interval: Interval between checks in seconds.
        timeout: Timeout for each check in seconds.
        retries: Number of consecutive failures before unhealthy.
        start_period: Grace period before checks begin in seconds.
    """

    check_type: HealthCheckType = HealthCheckType.CMD_SHELL
    command: str = "exit 0"
    interval: float = 30.0
    timeout: float = 10.0
    retries: int = 3
    start_period: float = 15.0


@dataclass
class RestartPolicySpec:
    """Restart policy specification for a service.

    Controls whether and how a stopped service is automatically
    restarted, including delay between attempts and the time
    window for resetting the attempt counter.

    Attributes:
        condition: Restart condition (no, always, on-failure, unless-stopped).
        max_attempts: Maximum restart attempts (0 = unlimited).
        delay: Delay between restart attempts in seconds.
        window: Time window in seconds for resetting the attempt counter.
    """

    condition: RestartPolicy = RestartPolicy.ON_FAILURE
    max_attempts: int = 5
    delay: float = 5.0
    window: float = 120.0


@dataclass
class DeployConfig:
    """Deployment configuration for a service.

    Combines replica count, resource constraints, restart policy,
    and deployment-level labels for service scheduling.

    Attributes:
        replicas: Desired replica count.
        resources: Resource limits and reservations.
        restart_policy: Restart policy specification.
        labels: Deployment-level labels.
    """

    replicas: int = 1
    resources: ResourceLimits = field(default_factory=ResourceLimits)
    restart_policy: RestartPolicySpec = field(default_factory=RestartPolicySpec)
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class DependencySpec:
    """Dependency specification for inter-service dependency.

    Defines a directed edge in the service dependency graph.
    The condition determines when the dependency is considered
    satisfied and the dependent service can start.

    Attributes:
        service: Name of the service this depends on.
        condition: Condition for the dependency to be considered satisfied.
    """

    service: str
    condition: DependencyCondition = DependencyCondition.SERVICE_STARTED


@dataclass
class VolumeMount:
    """Volume mount specification for a service container.

    Maps a volume source (named volume, host path, or tmpfs)
    to a mount point inside the container.

    Attributes:
        source: Volume name (for named) or host path (for bind).
        target: Mount point inside the container.
        volume_type: Type of volume mount.
        read_only: Whether the mount is read-only.
    """

    source: str
    target: str
    volume_type: VolumeType = VolumeType.NAMED
    read_only: bool = False


@dataclass
class ServiceInstance:
    """Runtime state of a single service container instance.

    Tracks the lifecycle, health status, and resource assignment
    of an individual container instance within a compose service.

    Attributes:
        instance_id: Unique instance identifier.
        service_name: Name of the service this instance belongs to.
        container_id: Container ID in FizzContainerd.
        replica_index: Replica index (0-based).
        state: Current lifecycle state.
        health_status: Current health check status.
        started_at: When the instance was started.
        exit_code: Exit code if the instance has stopped.
        restart_count: Number of times the instance has been restarted.
        ports: Active port mappings.
        networks: Networks this instance is connected to.
        pid: Process ID inside the container.
    """

    instance_id: str
    service_name: str
    container_id: str = ""
    replica_index: int = 0
    state: ServiceState = ServiceState.CREATED
    health_status: str = "starting"
    started_at: Optional[datetime] = None
    exit_code: Optional[int] = None
    restart_count: int = 0
    ports: List[PortMapping] = field(default_factory=list)
    networks: List[str] = field(default_factory=list)
    pid: Optional[int] = None


@dataclass
class ComposeLogEntry:
    """A single log entry from a compose service container.

    Captures stdout, stderr, and system messages with timestamps
    and stream labels for structured log aggregation across the
    compose project.

    Attributes:
        timestamp: When the log entry was recorded.
        service_name: Service that produced this entry.
        instance_id: Instance that produced this entry.
        stream: Which stream produced the entry (stdout/stderr).
        message: The log message content.
        sequence: Monotonically increasing sequence number.
    """

    timestamp: datetime
    service_name: str
    instance_id: str
    stream: str = "stdout"
    message: str = ""
    sequence: int = 0


@dataclass
class ProcessInfo:
    """Information about a running process inside a service container.

    Mirrors the output of the 'top' command, showing active
    processes inside a container with their resource usage.

    Attributes:
        pid: Process ID.
        user: User running the process.
        cpu_percent: CPU usage percentage.
        memory_mb: Memory usage in megabytes.
        command: Command string.
    """

    pid: int
    user: str = "fizzbuzz"
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    command: str = ""


@dataclass
class ComposeStats:
    """Aggregate statistics for the FizzCompose engine.

    Tracks operational metrics across the entire compose project,
    including service counts, lifecycle events, and resource usage.

    Attributes:
        total_services: Number of services defined.
        running_services: Number of services currently running.
        healthy_services: Number of services passing health checks.
        total_instances: Total container instances across all services.
        running_instances: Currently running container instances.
        total_networks: Number of compose-scoped networks.
        total_volumes: Number of compose-scoped volumes.
        total_restarts: Total restart events across all services.
        total_health_checks: Total health check executions.
        compose_up_count: Number of compose-up operations.
        compose_down_count: Number of compose-down operations.
        total_events: Total lifecycle events emitted.
        uptime_seconds: Time since the project was brought up.
    """

    total_services: int = 0
    running_services: int = 0
    healthy_services: int = 0
    total_instances: int = 0
    running_instances: int = 0
    total_networks: int = 0
    total_volumes: int = 0
    total_restarts: int = 0
    total_health_checks: int = 0
    compose_up_count: int = 0
    compose_down_count: int = 0
    total_events: int = 0
    uptime_seconds: float = 0.0


# ============================================================
# ServiceDefinition
# ============================================================


@dataclass
class ServiceDefinition:
    """Per-service configuration within a compose file.

    Defines all configuration for a single service including its
    image, build context, dependencies, environment, ports, volumes,
    networks, deploy spec, and health check.  This is the compose
    equivalent of a Kubernetes PodSpec.

    Attributes:
        name: Service name (unique within the compose file).
        image: Container image reference.
        build: Build context path (alternative to image).
        command: Override container command.
        working_dir: Working directory inside the container.
        user: User to run the container process as.
        depends_on: Inter-service dependencies.
        environment: Environment variable specification.
        ports: Host-to-container port mappings.
        volumes: Volume mount specifications.
        networks: Networks this service connects to.
        deploy: Deployment configuration (replicas, resources, restart).
        healthcheck: Health check specification.
        labels: Service-level metadata labels.
        group: Logical service group this belongs to.
    """

    name: str
    image: str = ""
    build: str = ""
    command: str = ""
    working_dir: str = "/app"
    user: str = "fizzbuzz"
    depends_on: List[DependencySpec] = field(default_factory=list)
    environment: EnvironmentSpec = field(default_factory=EnvironmentSpec)
    ports: List[PortMapping] = field(default_factory=list)
    volumes: List[VolumeMount] = field(default_factory=list)
    networks: List[str] = field(default_factory=list)
    deploy: DeployConfig = field(default_factory=DeployConfig)
    healthcheck: HealthCheckSpec = field(default_factory=HealthCheckSpec)
    labels: Dict[str, str] = field(default_factory=dict)
    group: str = ""


# ============================================================
# ComposeFile
# ============================================================


@dataclass
class ComposeFile:
    """Top-level data model representing a parsed fizzbuzz-compose.yaml.

    Holds the complete application topology: version string,
    services map, networks map, and volumes map.  This is the
    in-memory representation of the compose file after parsing
    and validation.

    Attributes:
        version: Compose file format version.
        services: Map of service name to ServiceDefinition.
        networks: Map of network name to NetworkConfig.
        volumes: Map of volume name to VolumeConfig.
        project_name: Name of the compose project.
    """

    version: str = COMPOSE_VERSION
    services: Dict[str, ServiceDefinition] = field(default_factory=dict)
    networks: Dict[str, NetworkConfig] = field(default_factory=dict)
    volumes: Dict[str, VolumeConfig] = field(default_factory=dict)
    project_name: str = COMPOSE_PROJECT_NAME


@dataclass
class ComposeProject:
    """Runtime state of the compose project.

    Tracks the live state of all services, networks, and volumes
    after compose-up.  This is the mutable state that changes
    as services start, stop, scale, and restart.

    Attributes:
        name: Project name.
        status: Overall compose status.
        compose_file: Parsed compose file.
        services: Map of service name to list of ServiceInstance.
        networks: Map of network name to network ID.
        volumes: Map of volume name to volume path.
        started_at: When the project was brought up.
        startup_order: Topologically sorted service startup order.
    """

    name: str = "fizzbuzz"
    status: ComposeStatus = ComposeStatus.STOPPED
    compose_file: Optional[ComposeFile] = None
    services: Dict[str, List[ServiceInstance]] = field(default_factory=dict)
    networks: Dict[str, str] = field(default_factory=dict)
    volumes: Dict[str, str] = field(default_factory=dict)
    started_at: Optional[datetime] = None
    startup_order: List[List[str]] = field(default_factory=list)


# ============================================================
# ComposeServiceGroup — static service group definitions
# ============================================================


class ComposeServiceGroup:
    """Defines one of the 12 logical service groups.

    Maps a group name to its constituent infrastructure module list,
    default image reference, and default resource profile.  Service
    groups aggregate related infrastructure modules into deployable
    units that can be independently scaled, monitored, and managed.
    """

    # Default service group definitions for the Enterprise FizzBuzz Platform
    GROUPS: Dict[str, Dict[str, Any]] = {
        "fizzbuzz-core": {
            "image": "fizzbuzz-eval:latest",
            "modules": [
                "rule_engine", "middleware_pipeline", "formatter",
                "fizzbuzz_evaluator", "anti_corruption_layer",
            ],
            "description": "Core FizzBuzz evaluation pipeline",
            "port": 8001,
            "depends_on": [
                DependencySpec("fizzbuzz-data", DependencyCondition.SERVICE_HEALTHY),
                DependencySpec("fizzbuzz-cache", DependencyCondition.SERVICE_HEALTHY),
                DependencySpec("fizzbuzz-security", DependencyCondition.SERVICE_HEALTHY),
            ],
        },
        "fizzbuzz-data": {
            "image": "fizzbuzz-data:latest",
            "modules": [
                "sqlite_persistence", "filesystem_persistence",
                "in_memory_persistence", "schema_evolution", "cdc",
            ],
            "description": "Data persistence and change data capture",
            "port": 8002,
            "depends_on": [
                DependencySpec("fizzbuzz-platform", DependencyCondition.SERVICE_STARTED),
            ],
        },
        "fizzbuzz-cache": {
            "image": "fizzbuzz-cache:latest",
            "modules": [
                "mesi_cache_coherence", "query_optimizer", "columnar_storage",
            ],
            "description": "Cache coherence and query optimization",
            "port": 8003,
            "depends_on": [
                DependencySpec("fizzbuzz-data", DependencyCondition.SERVICE_HEALTHY),
            ],
        },
        "fizzbuzz-network": {
            "image": "fizzbuzz-network:latest",
            "modules": [
                "tcp_ip_stack", "dns_server", "reverse_proxy",
                "service_mesh", "http2_protocol",
            ],
            "description": "Network stack and service mesh",
            "port": 8004,
            "depends_on": [
                DependencySpec("fizzbuzz-platform", DependencyCondition.SERVICE_STARTED),
            ],
        },
        "fizzbuzz-security": {
            "image": "fizzbuzz-security:latest",
            "modules": [
                "rbac", "hmac_auth", "capability_security",
                "secrets_vault", "compliance_sox_gdpr_hipaa",
            ],
            "description": "Security, authentication, and compliance",
            "port": 8005,
            "depends_on": [
                DependencySpec("fizzbuzz-data", DependencyCondition.SERVICE_HEALTHY),
                DependencySpec("fizzbuzz-network", DependencyCondition.SERVICE_HEALTHY),
            ],
        },
        "fizzbuzz-observability": {
            "image": "fizzbuzz-observability:latest",
            "modules": [
                "opentelemetry", "flame_graphs", "sla_monitoring",
                "metrics", "correlation_engine", "model_checker",
            ],
            "description": "Observability, monitoring, and tracing",
            "port": 8006,
            "depends_on": [
                DependencySpec("fizzbuzz-core", DependencyCondition.SERVICE_HEALTHY),
                DependencySpec("fizzbuzz-network", DependencyCondition.SERVICE_HEALTHY),
            ],
        },
        "fizzbuzz-compute": {
            "image": "fizzbuzz-compute:latest",
            "modules": [
                "bytecode_vm", "jit_compiler", "cross_compiler",
                "quantum_simulator", "neural_network", "genetic_algorithm",
            ],
            "description": "Compute engines and simulators",
            "port": 8007,
            "depends_on": [
                DependencySpec("fizzbuzz-core", DependencyCondition.SERVICE_HEALTHY),
                DependencySpec("fizzbuzz-cache", DependencyCondition.SERVICE_HEALTHY),
            ],
        },
        "fizzbuzz-devtools": {
            "image": "fizzbuzz-devtools:latest",
            "modules": [
                "debug_adapter", "package_manager", "fizzlang_dsl",
                "version_control", "assembler", "regex_engine",
            ],
            "description": "Developer tooling and language services",
            "port": 8008,
            "depends_on": [
                DependencySpec("fizzbuzz-core", DependencyCondition.SERVICE_STARTED),
                DependencySpec("fizzbuzz-platform", DependencyCondition.SERVICE_STARTED),
            ],
        },
        "fizzbuzz-platform": {
            "image": "fizzbuzz-platform:latest",
            "modules": [
                "os_kernel", "memory_allocator", "garbage_collector",
                "ipc", "process_migration", "bootloader",
            ],
            "description": "Platform services and kernel abstractions",
            "port": 8009,
            "depends_on": [],
        },
        "fizzbuzz-enterprise": {
            "image": "fizzbuzz-enterprise:latest",
            "modules": [
                "blockchain", "smart_contracts", "billing",
                "feature_flags", "event_sourcing", "cqrs", "webhooks",
            ],
            "description": "Enterprise business services",
            "port": 8010,
            "depends_on": [
                DependencySpec("fizzbuzz-data", DependencyCondition.SERVICE_HEALTHY),
                DependencySpec("fizzbuzz-security", DependencyCondition.SERVICE_HEALTHY),
                DependencySpec("fizzbuzz-network", DependencyCondition.SERVICE_HEALTHY),
            ],
        },
        "fizzbuzz-ops": {
            "image": "fizzbuzz-ops:latest",
            "modules": [
                "fizzbob_cognitive_load", "approval_workflow", "pager",
                "succession_planning", "performance_review", "org_hierarchy",
            ],
            "description": "Operations and organizational management",
            "port": 8011,
            "depends_on": [
                DependencySpec("fizzbuzz-core", DependencyCondition.SERVICE_HEALTHY),
                DependencySpec("fizzbuzz-observability", DependencyCondition.SERVICE_HEALTHY),
                DependencySpec("fizzbuzz-enterprise", DependencyCondition.SERVICE_STARTED),
            ],
        },
        "fizzbuzz-exotic": {
            "image": "fizzbuzz-exotic:latest",
            "modules": [
                "ray_tracer", "protein_folder", "audio_synthesizer",
                "video_codec", "typesetter", "spreadsheet",
                "spatial_database", "digital_twin", "gpu_shader",
                "logic_gate_simulator",
            ],
            "description": "Specialized computation and simulation services",
            "port": 8012,
            "depends_on": [
                DependencySpec("fizzbuzz-core", DependencyCondition.SERVICE_HEALTHY),
                DependencySpec("fizzbuzz-compute", DependencyCondition.SERVICE_HEALTHY),
                DependencySpec("fizzbuzz-platform", DependencyCondition.SERVICE_STARTED),
            ],
        },
    }

    @classmethod
    def get_group(cls, name: str) -> Dict[str, Any]:
        """Retrieve a service group definition by name.

        Args:
            name: Service group name.

        Returns:
            Service group definition dictionary.

        Raises:
            ComposeServiceNotFoundError: If the group does not exist.
        """
        if name not in cls.GROUPS:
            raise ComposeServiceNotFoundError(name)
        return cls.GROUPS[name]

    @classmethod
    def get_all_groups(cls) -> Dict[str, Dict[str, Any]]:
        """Return all service group definitions.

        Returns:
            Dictionary mapping group names to their definitions.
        """
        return dict(cls.GROUPS)

    @classmethod
    def get_group_names(cls) -> List[str]:
        """Return the names of all service groups.

        Returns:
            List of service group names.
        """
        return list(cls.GROUPS.keys())

    @classmethod
    def get_modules_for_group(cls, name: str) -> List[str]:
        """Return the module list for a service group.

        Args:
            name: Service group name.

        Returns:
            List of module names in the group.
        """
        group = cls.get_group(name)
        return list(group["modules"])

    @classmethod
    def find_group_for_module(cls, module_name: str) -> Optional[str]:
        """Find which service group contains a given module.

        Args:
            module_name: Name of the infrastructure module.

        Returns:
            Service group name, or None if the module is not in any group.
        """
        for group_name, group_def in cls.GROUPS.items():
            if module_name in group_def["modules"]:
                return group_name
        return None


# ============================================================
# Default Compose File (embedded YAML as dict)
# ============================================================


def _build_default_compose_file() -> ComposeFile:
    """Build the default fizzbuzz-compose.yaml as a ComposeFile.

    Constructs the default application topology with 12 service
    groups, their dependency relationships, default networks, and
    default volumes.  This is used when no external compose file
    is provided.

    Returns:
        ComposeFile with the default FizzBuzz platform topology.
    """
    compose_file = ComposeFile(
        version=COMPOSE_VERSION,
        project_name=COMPOSE_PROJECT_NAME,
    )

    # Build service definitions from service groups
    for group_name, group_def in ComposeServiceGroup.GROUPS.items():
        service = ServiceDefinition(
            name=group_name,
            image=group_def["image"],
            depends_on=list(group_def["depends_on"]),
            ports=[PortMapping(
                host_port=group_def["port"],
                container_port=group_def["port"],
            )],
            networks=["fizzbuzz-net"],
            deploy=DeployConfig(
                replicas=1,
                resources=ResourceLimits(),
                restart_policy=RestartPolicySpec(
                    condition=RestartPolicy.ON_FAILURE,
                    max_attempts=5,
                    delay=5.0,
                    window=120.0,
                ),
            ),
            healthcheck=HealthCheckSpec(
                check_type=HealthCheckType.CMD_SHELL,
                command=f"fizzbuzz-health --service {group_name}",
                interval=30.0,
                timeout=10.0,
                retries=3,
                start_period=15.0,
            ),
            labels={
                "com.fizzbuzz.service": group_name,
                "com.fizzbuzz.description": group_def["description"],
            },
            group=group_name,
            environment=EnvironmentSpec(
                variables={
                    "FIZZBUZZ_SERVICE": group_name,
                    "FIZZBUZZ_LOG_LEVEL": "INFO",
                },
            ),
        )
        compose_file.services[group_name] = service

    # Default network
    compose_file.networks["fizzbuzz-net"] = NetworkConfig(
        name="fizzbuzz-net",
        driver=NetworkDriver.BRIDGE,
        subnet=DEFAULT_NETWORK_SUBNET,
        gateway=DEFAULT_NETWORK_GATEWAY,
        labels={"com.fizzbuzz.network": "default"},
    )

    # Default volumes
    compose_file.volumes["fizzbuzz-data"] = VolumeConfig(
        name="fizzbuzz-data",
        driver="local",
        labels={"com.fizzbuzz.volume": "data"},
    )
    compose_file.volumes["fizzbuzz-logs"] = VolumeConfig(
        name="fizzbuzz-logs",
        driver="local",
        labels={"com.fizzbuzz.volume": "logs"},
    )
    compose_file.volumes["fizzbuzz-config"] = VolumeConfig(
        name="fizzbuzz-config",
        driver="local",
        labels={"com.fizzbuzz.volume": "config"},
    )

    return compose_file


# ============================================================
# ComposeParser — YAML parsing, schema validation, variable interpolation
# ============================================================


class ComposeParser:
    """Parses and validates fizzbuzz-compose.yaml compose files.

    The parser processes compose file data (provided as a dictionary,
    since the actual YAML loading is handled by the caller), validates
    the structure against the compose schema, resolves variable
    interpolation using ${VARIABLE:-default} syntax, and checks for
    circular dependencies in the depends_on graph before constructing
    a ComposeFile instance.

    When no compose file data is provided, the parser returns the
    default embedded compose file with all 12 service groups.
    """

    def __init__(self, environment: Optional[Dict[str, str]] = None) -> None:
        """Initialize the compose parser.

        Args:
            environment: Environment variables for interpolation.
                         Defaults to an empty dictionary.
        """
        self._environment: Dict[str, str] = environment or {}
        self._parse_count = 0
        self._validation_errors: List[str] = []

    def parse(
        self,
        data: Optional[Dict[str, Any]] = None,
        file_path: str = COMPOSE_FILE_NAME,
    ) -> ComposeFile:
        """Parse compose file data into a ComposeFile.

        If data is None, returns the default embedded compose file.
        Otherwise, validates and converts the dictionary into a
        ComposeFile with fully resolved variable interpolation.

        Args:
            data: Compose file data as a dictionary (from YAML loading).
            file_path: Path to the compose file (for error messages).

        Returns:
            Parsed and validated ComposeFile instance.

        Raises:
            ComposeFileParseError: If the data does not conform to the schema.
            ComposeVariableInterpolationError: If variable resolution fails.
        """
        self._parse_count += 1
        self._validation_errors = []

        if data is None:
            logger.info("No compose file data provided, using default topology")
            return _build_default_compose_file()

        # Validate top-level structure
        if not isinstance(data, dict):
            raise ComposeFileParseError(
                file_path, "Root element must be a mapping"
            )

        # Resolve variable interpolation across all string values
        resolved_data = self._interpolate_variables(data)

        # Extract version
        version = str(resolved_data.get("version", COMPOSE_VERSION))

        # Parse services
        services_data = resolved_data.get("services", {})
        if not isinstance(services_data, dict):
            raise ComposeFileParseError(
                file_path, "services must be a mapping"
            )

        services: Dict[str, ServiceDefinition] = {}
        for svc_name, svc_data in services_data.items():
            if not isinstance(svc_data, dict):
                raise ComposeFileParseError(
                    file_path, f"Service '{svc_name}' must be a mapping"
                )
            services[svc_name] = self._parse_service(svc_name, svc_data, file_path)

        # Parse networks
        networks_data = resolved_data.get("networks", {})
        networks: Dict[str, NetworkConfig] = {}
        if isinstance(networks_data, dict):
            for net_name, net_data in networks_data.items():
                networks[net_name] = self._parse_network(net_name, net_data or {})

        # Parse volumes
        volumes_data = resolved_data.get("volumes", {})
        volumes: Dict[str, VolumeConfig] = {}
        if isinstance(volumes_data, dict):
            for vol_name, vol_data in volumes_data.items():
                volumes[vol_name] = self._parse_volume(vol_name, vol_data or {})

        compose_file = ComposeFile(
            version=version,
            services=services,
            networks=networks,
            volumes=volumes,
        )

        logger.info(
            "Parsed compose file '%s': %d services, %d networks, %d volumes",
            file_path,
            len(services),
            len(networks),
            len(volumes),
        )

        return compose_file

    def _parse_service(
        self,
        name: str,
        data: Dict[str, Any],
        file_path: str,
    ) -> ServiceDefinition:
        """Parse a single service definition from compose data.

        Args:
            name: Service name.
            data: Service configuration dictionary.
            file_path: Compose file path (for error messages).

        Returns:
            Parsed ServiceDefinition.
        """
        # Parse depends_on
        depends_on: List[DependencySpec] = []
        raw_depends = data.get("depends_on", [])
        if isinstance(raw_depends, list):
            for dep in raw_depends:
                if isinstance(dep, str):
                    depends_on.append(DependencySpec(service=dep))
                elif isinstance(dep, dict):
                    dep_name = dep.get("service", dep.get("name", ""))
                    condition_str = dep.get("condition", "service_started")
                    try:
                        condition = DependencyCondition(condition_str)
                    except ValueError:
                        condition = DependencyCondition.SERVICE_STARTED
                    depends_on.append(DependencySpec(
                        service=dep_name,
                        condition=condition,
                    ))
        elif isinstance(raw_depends, dict):
            for dep_name, dep_config in raw_depends.items():
                if isinstance(dep_config, dict):
                    condition_str = dep_config.get("condition", "service_started")
                    try:
                        condition = DependencyCondition(condition_str)
                    except ValueError:
                        condition = DependencyCondition.SERVICE_STARTED
                    depends_on.append(DependencySpec(
                        service=dep_name,
                        condition=condition,
                    ))
                else:
                    depends_on.append(DependencySpec(service=dep_name))

        # Parse environment
        env_data = data.get("environment", {})
        env_spec = EnvironmentSpec()
        if isinstance(env_data, dict):
            env_spec.variables = {str(k): str(v) for k, v in env_data.items()}
        elif isinstance(env_data, list):
            for item in env_data:
                if "=" in str(item):
                    key, _, value = str(item).partition("=")
                    env_spec.variables[key] = value
        env_spec.env_files = data.get("env_file", [])
        if isinstance(env_spec.env_files, str):
            env_spec.env_files = [env_spec.env_files]

        # Parse ports
        ports: List[PortMapping] = []
        for port_spec in data.get("ports", []):
            if isinstance(port_spec, str):
                parts = port_spec.split(":")
                if len(parts) == 2:
                    ports.append(PortMapping(
                        host_port=int(parts[0]),
                        container_port=int(parts[1]),
                    ))
                elif len(parts) == 3:
                    ports.append(PortMapping(
                        host_ip=parts[0],
                        host_port=int(parts[1]),
                        container_port=int(parts[2]),
                    ))
            elif isinstance(port_spec, dict):
                ports.append(PortMapping(
                    host_port=int(port_spec.get("published", 0)),
                    container_port=int(port_spec.get("target", 0)),
                    protocol=port_spec.get("protocol", "tcp"),
                    host_ip=port_spec.get("host_ip", "0.0.0.0"),
                ))
            elif isinstance(port_spec, int):
                ports.append(PortMapping(
                    host_port=port_spec,
                    container_port=port_spec,
                ))

        # Parse volumes
        volume_mounts: List[VolumeMount] = []
        for vol_spec in data.get("volumes", []):
            if isinstance(vol_spec, str):
                parts = vol_spec.split(":")
                if len(parts) >= 2:
                    source, target = parts[0], parts[1]
                    read_only = len(parts) > 2 and parts[2] == "ro"
                    vol_type = VolumeType.BIND if source.startswith("/") else VolumeType.NAMED
                    volume_mounts.append(VolumeMount(
                        source=source,
                        target=target,
                        volume_type=vol_type,
                        read_only=read_only,
                    ))
            elif isinstance(vol_spec, dict):
                volume_mounts.append(VolumeMount(
                    source=vol_spec.get("source", ""),
                    target=vol_spec.get("target", ""),
                    volume_type=VolumeType(vol_spec.get("type", "named")),
                    read_only=vol_spec.get("read_only", False),
                ))

        # Parse healthcheck
        hc_data = data.get("healthcheck", {})
        healthcheck = HealthCheckSpec()
        if isinstance(hc_data, dict):
            test = hc_data.get("test", hc_data.get("command", ""))
            if isinstance(test, list):
                if len(test) > 1:
                    try:
                        healthcheck.check_type = HealthCheckType(test[0])
                    except ValueError:
                        healthcheck.check_type = HealthCheckType.CMD_SHELL
                    healthcheck.command = " ".join(test[1:])
            elif isinstance(test, str):
                healthcheck.command = test
            healthcheck.interval = float(hc_data.get("interval", 30.0))
            healthcheck.timeout = float(hc_data.get("timeout", 10.0))
            healthcheck.retries = int(hc_data.get("retries", 3))
            healthcheck.start_period = float(hc_data.get("start_period", 15.0))

        # Parse deploy
        deploy_data = data.get("deploy", {})
        deploy = DeployConfig()
        if isinstance(deploy_data, dict):
            deploy.replicas = int(deploy_data.get("replicas", 1))
            res_data = deploy_data.get("resources", {})
            if isinstance(res_data, dict):
                limits = res_data.get("limits", {})
                reservations = res_data.get("reservations", {})
                deploy.resources = ResourceLimits(
                    cpu_limit=float(limits.get("cpus", 1.0)),
                    memory_limit=int(limits.get("memory", 536870912)),
                    cpu_reservation=float(reservations.get("cpus", 0.25)),
                    memory_reservation=int(reservations.get("memory", 134217728)),
                )
            rp_data = deploy_data.get("restart_policy", {})
            if isinstance(rp_data, dict):
                try:
                    condition = RestartPolicy(rp_data.get("condition", "on-failure"))
                except ValueError:
                    condition = RestartPolicy.ON_FAILURE
                deploy.restart_policy = RestartPolicySpec(
                    condition=condition,
                    max_attempts=int(rp_data.get("max_attempts", 5)),
                    delay=float(rp_data.get("delay", 5.0)),
                    window=float(rp_data.get("window", 120.0)),
                )
            deploy.labels = deploy_data.get("labels", {})

        return ServiceDefinition(
            name=name,
            image=data.get("image", ""),
            build=data.get("build", ""),
            command=data.get("command", ""),
            working_dir=data.get("working_dir", "/app"),
            user=data.get("user", "fizzbuzz"),
            depends_on=depends_on,
            environment=env_spec,
            ports=ports,
            volumes=volume_mounts,
            networks=data.get("networks", []),
            deploy=deploy,
            healthcheck=healthcheck,
            labels=data.get("labels", {}),
            group=data.get("group", ""),
        )

    def _parse_network(
        self,
        name: str,
        data: Dict[str, Any],
    ) -> NetworkConfig:
        """Parse a single network definition.

        Args:
            name: Network name.
            data: Network configuration dictionary.

        Returns:
            Parsed NetworkConfig.
        """
        try:
            driver = NetworkDriver(data.get("driver", "bridge"))
        except ValueError:
            driver = NetworkDriver.BRIDGE

        ipam = data.get("ipam", {})
        subnet = DEFAULT_NETWORK_SUBNET
        gateway = DEFAULT_NETWORK_GATEWAY
        ipam_driver = "default"
        if isinstance(ipam, dict):
            ipam_driver = ipam.get("driver", "default")
            configs = ipam.get("config", [])
            if isinstance(configs, list) and configs:
                first = configs[0]
                if isinstance(first, dict):
                    subnet = first.get("subnet", subnet)
                    gateway = first.get("gateway", gateway)

        return NetworkConfig(
            name=name,
            driver=driver,
            subnet=subnet,
            gateway=gateway,
            ipam_driver=ipam_driver,
            labels=data.get("labels", {}),
            internal=bool(data.get("internal", False)),
            enable_ipv6=bool(data.get("enable_ipv6", False)),
        )

    def _parse_volume(
        self,
        name: str,
        data: Dict[str, Any],
    ) -> VolumeConfig:
        """Parse a single volume definition.

        Args:
            name: Volume name.
            data: Volume configuration dictionary.

        Returns:
            Parsed VolumeConfig.
        """
        return VolumeConfig(
            name=name,
            driver=data.get("driver", "local"),
            driver_opts=data.get("driver_opts", {}),
            labels=data.get("labels", {}),
            external=bool(data.get("external", False)),
        )

    def _interpolate_variables(
        self,
        data: Any,
    ) -> Any:
        """Recursively resolve ${VARIABLE:-default} interpolation.

        Walks the data structure and replaces variable references
        with values from the environment dictionary.  If a variable
        is not set and no default is provided, raises an error.

        Args:
            data: Data to interpolate (dict, list, or string).

        Returns:
            Data with all variables resolved.

        Raises:
            ComposeVariableInterpolationError: If a variable cannot be resolved.
        """
        if isinstance(data, str):
            return self._interpolate_string(data)
        elif isinstance(data, dict):
            return {
                self._interpolate_variables(k): self._interpolate_variables(v)
                for k, v in data.items()
            }
        elif isinstance(data, list):
            return [self._interpolate_variables(item) for item in data]
        return data

    def _interpolate_string(self, value: str) -> str:
        """Resolve variable interpolation in a single string.

        Args:
            value: String potentially containing ${VAR:-default} references.

        Returns:
            String with variables resolved.

        Raises:
            ComposeVariableInterpolationError: If a variable is unset
                without a default value.
        """
        def _replace(match: re.Match) -> str:
            var_name = match.group(1)
            default = match.group(2)
            env_value = self._environment.get(var_name)
            if env_value is not None:
                return env_value
            if default is not None:
                return default
            raise ComposeVariableInterpolationError(
                var_name,
                "Variable is not set and no default value provided",
            )

        return VARIABLE_INTERPOLATION_PATTERN.sub(_replace, value)

    @property
    def parse_count(self) -> int:
        """Return the number of times parse() has been called."""
        return self._parse_count

    def validate_references(self, compose_file: ComposeFile) -> List[str]:
        """Validate that all service references (depends_on, networks, volumes) exist.

        Args:
            compose_file: Parsed compose file to validate.

        Returns:
            List of validation error messages (empty if valid).
        """
        errors: List[str] = []
        service_names = set(compose_file.services.keys())
        network_names = set(compose_file.networks.keys())
        volume_names = set(compose_file.volumes.keys())

        for svc_name, svc in compose_file.services.items():
            # Validate depends_on references
            for dep in svc.depends_on:
                if dep.service not in service_names:
                    errors.append(
                        f"Service '{svc_name}' depends on undefined "
                        f"service '{dep.service}'"
                    )

            # Validate network references
            for net in svc.networks:
                if net not in network_names:
                    errors.append(
                        f"Service '{svc_name}' references undefined "
                        f"network '{net}'"
                    )

            # Validate named volume references
            for vol in svc.volumes:
                if vol.volume_type == VolumeType.NAMED and vol.source not in volume_names:
                    errors.append(
                        f"Service '{svc_name}' references undefined "
                        f"volume '{vol.source}'"
                    )

        return errors


# ============================================================
# DependencyResolver — Kahn's algorithm topological sort
# ============================================================


class DependencyResolver:
    """Constructs a DAG from service depends_on declarations and sorts topologically.

    Implements Kahn's algorithm for topological sorting of the service
    dependency graph.  Detects cycles in the graph (which would make
    topological sorting impossible) and reports the cycle path.

    Supports three dependency conditions:
    - service_started: the container is running
    - service_healthy: the container passes its health check
    - service_completed_successfully: the container exited with code 0

    Health-check-gated dependencies are resolved through the
    HealthCheckGate, which polls the target service until it
    reports healthy status.
    """

    def __init__(
        self,
        health_check_gate: Optional[HealthCheckGate] = None,
    ) -> None:
        """Initialize the dependency resolver.

        Args:
            health_check_gate: Optional health check gate for
                service_healthy condition resolution.
        """
        self._health_check_gate = health_check_gate
        self._resolve_count = 0
        self._total_edges = 0

    def resolve(
        self,
        compose_file: ComposeFile,
    ) -> List[List[str]]:
        """Topologically sort services into startup tiers using Kahn's algorithm.

        Services within the same tier have no dependencies on each other
        and can be started in parallel.  Tiers are ordered so that all
        dependencies of tier N are in tiers 0..N-1.

        Args:
            compose_file: Parsed compose file with service definitions.

        Returns:
            List of tiers, each tier is a list of service names that
            can be started in parallel.

        Raises:
            ComposeCircularDependencyError: If the dependency graph
                contains a cycle.
        """
        self._resolve_count += 1

        services = compose_file.services
        if not services:
            return []

        # Build adjacency list and in-degree count
        in_degree: Dict[str, int] = {name: 0 for name in services}
        adjacency: Dict[str, List[str]] = {name: [] for name in services}
        dependency_conditions: Dict[Tuple[str, str], DependencyCondition] = {}

        for svc_name, svc in services.items():
            for dep in svc.depends_on:
                if dep.service in services:
                    adjacency[dep.service].append(svc_name)
                    in_degree[svc_name] += 1
                    dependency_conditions[(dep.service, svc_name)] = dep.condition
                    self._total_edges += 1

        # Kahn's algorithm: start with zero-in-degree nodes
        queue: deque = deque()
        for name, degree in in_degree.items():
            if degree == 0:
                queue.append(name)

        tiers: List[List[str]] = []
        processed_count = 0

        while queue:
            # All nodes in the current queue form one tier
            tier: List[str] = []
            next_queue: deque = deque()

            while queue:
                node = queue.popleft()
                tier.append(node)
                processed_count += 1

                for dependent in adjacency[node]:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        next_queue.append(dependent)

            tier.sort()  # Deterministic ordering within tiers
            tiers.append(tier)
            queue = next_queue

        # Check for cycles
        if processed_count < len(services):
            cycle = self._find_cycle(services, adjacency, in_degree)
            raise ComposeCircularDependencyError(cycle)

        logger.info(
            "Dependency resolution complete: %d services in %d tiers",
            processed_count,
            len(tiers),
        )

        return tiers

    def _find_cycle(
        self,
        services: Dict[str, ServiceDefinition],
        adjacency: Dict[str, List[str]],
        in_degree: Dict[str, int],
    ) -> List[str]:
        """Find and report a cycle in the dependency graph.

        Uses DFS to find a cycle among unprocessed nodes (those with
        remaining in-degree > 0).

        Args:
            services: Service definitions.
            adjacency: Adjacency list (dependency -> dependents).
            in_degree: Remaining in-degree counts.

        Returns:
            List of service names forming the cycle.
        """
        # Nodes still in the graph (part of a cycle)
        remaining = {name for name, deg in in_degree.items() if deg > 0}
        if not remaining:
            return ["unknown"]

        # Build reverse adjacency for remaining nodes
        # (we need dependency direction: child -> parent)
        reverse_adj: Dict[str, List[str]] = {name: [] for name in remaining}
        for parent, children in adjacency.items():
            if parent in remaining:
                for child in children:
                    if child in remaining:
                        reverse_adj[child].append(parent)

        # DFS to find cycle
        visited: Set[str] = set()
        path: List[str] = []
        on_stack: Set[str] = set()

        def dfs(node: str) -> Optional[List[str]]:
            visited.add(node)
            on_stack.add(node)
            path.append(node)

            for svc_name, svc in services.items():
                if svc_name != node:
                    continue
                for dep in svc.depends_on:
                    if dep.service in remaining:
                        if dep.service in on_stack:
                            # Found cycle
                            cycle_start = path.index(dep.service)
                            return path[cycle_start:] + [dep.service]
                        if dep.service not in visited:
                            result = dfs(dep.service)
                            if result:
                                return result

            path.pop()
            on_stack.remove(node)
            return None

        for node in remaining:
            if node not in visited:
                result = dfs(node)
                if result:
                    return result

        return list(remaining)[:3] + [list(remaining)[0]]

    def get_dependency_conditions(
        self,
        compose_file: ComposeFile,
        service_name: str,
    ) -> List[DependencySpec]:
        """Get the dependency conditions for a specific service.

        Args:
            compose_file: Parsed compose file.
            service_name: Service to query.

        Returns:
            List of DependencySpec for the service's dependencies.
        """
        if service_name not in compose_file.services:
            return []
        return list(compose_file.services[service_name].depends_on)

    def check_dependency_satisfied(
        self,
        condition: DependencyCondition,
        instance: ServiceInstance,
    ) -> bool:
        """Check whether a dependency condition is satisfied by an instance.

        Args:
            condition: The condition to check.
            instance: The service instance to evaluate.

        Returns:
            True if the condition is satisfied.
        """
        if condition == DependencyCondition.SERVICE_STARTED:
            return instance.state in (
                ServiceState.RUNNING,
                ServiceState.HEALTHY,
            )
        elif condition == DependencyCondition.SERVICE_HEALTHY:
            return instance.state == ServiceState.HEALTHY
        elif condition == DependencyCondition.SERVICE_COMPLETED_SUCCESSFULLY:
            return (
                instance.state == ServiceState.COMPLETED
                and instance.exit_code == 0
            )
        return False

    @property
    def resolve_count(self) -> int:
        """Return the number of times resolve() has been called."""
        return self._resolve_count

    @property
    def total_edges(self) -> int:
        """Return the total number of dependency edges processed."""
        return self._total_edges


# ============================================================
# HealthCheckGate — health check execution and polling
# ============================================================


class HealthCheckGate:
    """Executes health check commands against containers at configurable intervals.

    The health check gate polls a service's health status until it
    reports healthy or the timeout expires.  It is used by the
    DependencyResolver for service_healthy condition gating and by
    the ComposeEngine for service readiness tracking.

    Health checks simulate execution by evaluating the health check
    specification against the service instance state.  In the
    Enterprise FizzBuzz Platform, all services are deterministically
    healthy after their start_period elapses.
    """

    def __init__(
        self,
        interval: float = DEFAULT_HEALTH_CHECK_INTERVAL,
        timeout: float = DEFAULT_HEALTH_CHECK_TIMEOUT,
    ) -> None:
        """Initialize the health check gate.

        Args:
            interval: Interval between health check polls in seconds.
            timeout: Maximum time to wait for healthy status in seconds.
        """
        self._interval = interval
        self._timeout = timeout
        self._check_count = 0
        self._pass_count = 0
        self._fail_count = 0
        self._results: Dict[str, List[bool]] = defaultdict(list)

    def check(
        self,
        service_name: str,
        instance: ServiceInstance,
        healthcheck: HealthCheckSpec,
    ) -> bool:
        """Execute a single health check against a service instance.

        Simulates the health check by evaluating the instance state
        and the health check specification.  A service is considered
        healthy if it is in the RUNNING or HEALTHY state and has been
        running longer than the start_period.

        Args:
            service_name: Name of the service being checked.
            instance: Service instance to check.
            healthcheck: Health check specification.

        Returns:
            True if the health check passes.
        """
        self._check_count += 1

        if healthcheck.check_type == HealthCheckType.NONE:
            self._pass_count += 1
            self._results[service_name].append(True)
            return True

        # Check if instance is in a valid state
        if instance.state not in (ServiceState.RUNNING, ServiceState.HEALTHY):
            self._fail_count += 1
            self._results[service_name].append(False)
            return False

        # Check start_period
        if instance.started_at is not None:
            elapsed = (datetime.now(timezone.utc) - instance.started_at).total_seconds()
            if elapsed < healthcheck.start_period:
                # Still in start period, check passes (grace period)
                self._pass_count += 1
                self._results[service_name].append(True)
                return True

        # Simulate health check execution
        # In the Enterprise FizzBuzz Platform, services are deterministically
        # healthy when running.  The health check command is logged but not
        # actually executed against real infrastructure.
        is_healthy = instance.state in (ServiceState.RUNNING, ServiceState.HEALTHY)

        if is_healthy:
            self._pass_count += 1
        else:
            self._fail_count += 1

        self._results[service_name].append(is_healthy)
        return is_healthy

    def wait_for_healthy(
        self,
        service_name: str,
        instance: ServiceInstance,
        healthcheck: HealthCheckSpec,
    ) -> bool:
        """Poll until the service becomes healthy or timeout expires.

        Repeatedly executes health checks at the configured interval
        until the service reports healthy or the timeout is reached.

        Args:
            service_name: Name of the service being checked.
            instance: Service instance to check.
            healthcheck: Health check specification.

        Returns:
            True if the service became healthy within the timeout.

        Raises:
            ComposeHealthCheckTimeoutError: If the timeout expires.
        """
        # For simulation purposes, running services are always healthy
        if instance.state in (ServiceState.RUNNING, ServiceState.HEALTHY):
            return self.check(service_name, instance, healthcheck)

        return False

    @property
    def check_count(self) -> int:
        """Return the total number of health checks executed."""
        return self._check_count

    @property
    def pass_count(self) -> int:
        """Return the number of health checks that passed."""
        return self._pass_count

    @property
    def fail_count(self) -> int:
        """Return the number of health checks that failed."""
        return self._fail_count

    def get_results(self, service_name: str) -> List[bool]:
        """Return the health check result history for a service.

        Args:
            service_name: Service name.

        Returns:
            List of boolean results (True = passed, False = failed).
        """
        return list(self._results.get(service_name, []))

    @property
    def interval(self) -> float:
        """Return the health check poll interval."""
        return self._interval

    @property
    def timeout(self) -> float:
        """Return the health check timeout."""
        return self._timeout


# ============================================================
# ComposeNetworkManager — network creation/deletion
# ============================================================


class ComposeNetworkManager:
    """Creates and manages compose-scoped networks.

    Handles service-to-network mapping, network isolation,
    DNS-based service name resolution, and network lifecycle.
    Networks are provisioned during compose-up and torn down
    during compose-down.

    Each network is assigned a unique identifier, an IP subnet,
    and a set of connected service instances.  Service name
    resolution within a network uses the service name as the
    DNS hostname.
    """

    def __init__(self) -> None:
        """Initialize the network manager."""
        self._networks: Dict[str, NetworkConfig] = {}
        self._network_ids: Dict[str, str] = {}
        self._connected_services: Dict[str, Set[str]] = defaultdict(set)
        self._dns_entries: Dict[str, Dict[str, str]] = defaultdict(dict)
        self._ip_allocations: Dict[str, Dict[str, str]] = defaultdict(dict)
        self._next_ip_octet: Dict[str, int] = {}
        self._create_count = 0
        self._delete_count = 0

    def create_network(self, config: NetworkConfig) -> str:
        """Create a compose-scoped network.

        Args:
            config: Network configuration.

        Returns:
            Network ID.

        Raises:
            ComposeNetworkCreateError: If network creation fails.
        """
        self._create_count += 1
        network_id = f"net-{config.name}-{uuid.uuid4().hex[:8]}"

        self._networks[config.name] = config
        self._network_ids[config.name] = network_id
        self._next_ip_octet[config.name] = 2  # .1 is gateway

        logger.info(
            "Created network '%s' (id=%s, driver=%s, subnet=%s)",
            config.name,
            network_id,
            config.driver.value,
            config.subnet,
        )

        return network_id

    def delete_network(self, name: str) -> None:
        """Delete a compose-scoped network.

        Disconnects all services and releases the network resources.

        Args:
            name: Network name.
        """
        self._delete_count += 1
        self._networks.pop(name, None)
        self._network_ids.pop(name, None)
        self._connected_services.pop(name, None)
        self._dns_entries.pop(name, None)
        self._ip_allocations.pop(name, None)
        self._next_ip_octet.pop(name, None)

        logger.info("Deleted network '%s'", name)

    def connect_service(
        self,
        network_name: str,
        service_name: str,
        instance_id: str,
    ) -> str:
        """Connect a service instance to a network.

        Allocates an IP address and creates a DNS entry for the
        service within the network.

        Args:
            network_name: Network to connect to.
            service_name: Service name (used for DNS resolution).
            instance_id: Instance identifier.

        Returns:
            Allocated IP address.

        Raises:
            ComposeNetworkNotFoundError: If the network does not exist.
        """
        if network_name not in self._networks:
            raise ComposeNetworkNotFoundError(service_name, network_name)

        config = self._networks[network_name]
        self._connected_services[network_name].add(service_name)

        # Allocate IP from subnet
        octet = self._next_ip_octet.get(network_name, 2)
        # Parse subnet base (e.g., "172.28.0.0/16" -> "172.28.0")
        subnet_base = config.subnet.split("/")[0]
        base_parts = subnet_base.split(".")
        ip = f"{base_parts[0]}.{base_parts[1]}.{octet // 256}.{octet % 256}"
        self._next_ip_octet[network_name] = octet + 1

        self._ip_allocations[network_name][instance_id] = ip
        self._dns_entries[network_name][service_name] = ip

        return ip

    def disconnect_service(
        self,
        network_name: str,
        service_name: str,
        instance_id: str,
    ) -> None:
        """Disconnect a service instance from a network.

        Args:
            network_name: Network to disconnect from.
            service_name: Service name.
            instance_id: Instance identifier.
        """
        if network_name in self._connected_services:
            self._connected_services[network_name].discard(service_name)
        if network_name in self._ip_allocations:
            self._ip_allocations[network_name].pop(instance_id, None)
        if network_name in self._dns_entries:
            self._dns_entries[network_name].pop(service_name, None)

    def resolve_dns(self, network_name: str, service_name: str) -> Optional[str]:
        """Resolve a service name to an IP address within a network.

        Args:
            network_name: Network to resolve in.
            service_name: Service name to resolve.

        Returns:
            IP address, or None if not found.
        """
        return self._dns_entries.get(network_name, {}).get(service_name)

    def get_connected_services(self, network_name: str) -> Set[str]:
        """Return the set of services connected to a network.

        Args:
            network_name: Network name.

        Returns:
            Set of service names.
        """
        return set(self._connected_services.get(network_name, set()))

    def get_network_id(self, network_name: str) -> Optional[str]:
        """Return the network ID for a network name.

        Args:
            network_name: Network name.

        Returns:
            Network ID, or None if not found.
        """
        return self._network_ids.get(network_name)

    def get_all_networks(self) -> Dict[str, NetworkConfig]:
        """Return all network configurations.

        Returns:
            Dictionary mapping network names to configurations.
        """
        return dict(self._networks)

    def cleanup(self) -> None:
        """Delete all networks managed by this manager."""
        names = list(self._networks.keys())
        for name in names:
            self.delete_network(name)

    @property
    def create_count(self) -> int:
        """Return the total number of networks created."""
        return self._create_count

    @property
    def delete_count(self) -> int:
        """Return the total number of networks deleted."""
        return self._delete_count


# ============================================================
# ComposeVolumeManager — volume creation/deletion
# ============================================================


class ComposeVolumeManager:
    """Creates and manages compose-scoped named volumes and bind mounts.

    Volumes provide persistent storage that survives container restarts
    and can be shared between services.  Named volumes are tracked by
    the volume manager with unique identifiers and metadata.  Bind
    mounts are validated but not managed (the host path must exist).

    Volumes are provisioned during compose-up and optionally removed
    during compose-down (with the --volumes flag).
    """

    def __init__(self) -> None:
        """Initialize the volume manager."""
        self._volumes: Dict[str, VolumeConfig] = {}
        self._volume_ids: Dict[str, str] = {}
        self._volume_paths: Dict[str, str] = {}
        self._mount_points: Dict[str, Dict[str, str]] = defaultdict(dict)
        self._create_count = 0
        self._delete_count = 0

    def create_volume(self, config: VolumeConfig) -> str:
        """Create a compose-scoped named volume.

        Args:
            config: Volume configuration.

        Returns:
            Volume path.

        Raises:
            ComposeVolumeCreateError: If volume creation fails.
        """
        self._create_count += 1
        volume_id = f"vol-{config.name}-{uuid.uuid4().hex[:8]}"
        volume_path = f"/var/lib/fizzcompose/volumes/{config.name}"

        self._volumes[config.name] = config
        self._volume_ids[config.name] = volume_id
        self._volume_paths[config.name] = volume_path

        logger.info(
            "Created volume '%s' (id=%s, driver=%s, path=%s)",
            config.name,
            volume_id,
            config.driver,
            volume_path,
        )

        return volume_path

    def delete_volume(self, name: str) -> None:
        """Delete a compose-scoped named volume.

        Args:
            name: Volume name.
        """
        self._delete_count += 1
        self._volumes.pop(name, None)
        self._volume_ids.pop(name, None)
        self._volume_paths.pop(name, None)
        self._mount_points.pop(name, None)

        logger.info("Deleted volume '%s'", name)

    def mount_volume(
        self,
        volume_name: str,
        service_name: str,
        mount_point: str,
    ) -> str:
        """Mount a volume into a service container.

        Args:
            volume_name: Volume to mount.
            service_name: Service receiving the mount.
            mount_point: Path inside the container.

        Returns:
            Volume path on the host.

        Raises:
            ComposeVolumeNotFoundError: If the volume does not exist.
        """
        if volume_name not in self._volumes:
            raise ComposeVolumeNotFoundError(service_name, volume_name)

        volume_path = self._volume_paths[volume_name]
        self._mount_points[volume_name][service_name] = mount_point

        return volume_path

    def unmount_volume(
        self,
        volume_name: str,
        service_name: str,
    ) -> None:
        """Unmount a volume from a service container.

        Args:
            volume_name: Volume to unmount.
            service_name: Service to unmount from.
        """
        if volume_name in self._mount_points:
            self._mount_points[volume_name].pop(service_name, None)

    def resolve_bind_mount(self, host_path: str) -> str:
        """Validate and resolve a bind mount host path.

        Args:
            host_path: Path on the host.

        Returns:
            Resolved absolute path.
        """
        # In simulation mode, bind mounts are accepted as-is
        return host_path

    def get_volume_path(self, name: str) -> Optional[str]:
        """Return the host path for a named volume.

        Args:
            name: Volume name.

        Returns:
            Volume path, or None if not found.
        """
        return self._volume_paths.get(name)

    def get_all_volumes(self) -> Dict[str, VolumeConfig]:
        """Return all volume configurations.

        Returns:
            Dictionary mapping volume names to configurations.
        """
        return dict(self._volumes)

    def get_mount_points(self, volume_name: str) -> Dict[str, str]:
        """Return all mount points for a volume.

        Args:
            volume_name: Volume name.

        Returns:
            Dictionary mapping service names to mount points.
        """
        return dict(self._mount_points.get(volume_name, {}))

    def cleanup(self) -> None:
        """Delete all volumes managed by this manager."""
        names = list(self._volumes.keys())
        for name in names:
            self.delete_volume(name)

    @property
    def create_count(self) -> int:
        """Return the total number of volumes created."""
        return self._create_count

    @property
    def delete_count(self) -> int:
        """Return the total number of volumes deleted."""
        return self._delete_count


# ============================================================
# RestartPolicyEngine — restart policy evaluation and tracking
# ============================================================


class RestartPolicyEngine:
    """Monitors container exits and applies configured restart policies.

    Evaluates whether a stopped service instance should be automatically
    restarted based on its restart policy (always, on-failure,
    unless-stopped, no).  Tracks restart attempt counts per service
    with configurable delay and reset windows.

    The engine maintains per-service state including attempt count,
    last restart time, and window start time.  When the window
    expires, the attempt counter resets, giving the service fresh
    restart attempts.
    """

    def __init__(
        self,
        default_delay: float = DEFAULT_RESTART_DELAY,
        default_max_attempts: int = DEFAULT_MAX_RESTART_ATTEMPTS,
        default_window: float = DEFAULT_RESTART_WINDOW,
    ) -> None:
        """Initialize the restart policy engine.

        Args:
            default_delay: Default delay between restart attempts.
            default_max_attempts: Default maximum restart attempts.
            default_window: Default window for attempt counter reset.
        """
        self._default_delay = default_delay
        self._default_max_attempts = default_max_attempts
        self._default_window = default_window
        self._attempt_counts: Dict[str, int] = defaultdict(int)
        self._window_starts: Dict[str, datetime] = {}
        self._last_restart: Dict[str, datetime] = {}
        self._total_restarts = 0

    def should_restart(
        self,
        service_name: str,
        policy: RestartPolicySpec,
        exit_code: int,
        manually_stopped: bool = False,
    ) -> bool:
        """Determine whether a stopped service should be restarted.

        Evaluates the restart policy against the exit code and
        current attempt count within the configured window.

        Args:
            service_name: Name of the service.
            policy: Restart policy specification.
            exit_code: Container exit code.
            manually_stopped: Whether the container was manually stopped.

        Returns:
            True if the service should be restarted.

        Raises:
            ComposeRestartPolicyExhaustedError: If max attempts exceeded.
        """
        # "no" policy never restarts
        if policy.condition == RestartPolicy.NO:
            return False

        # "unless-stopped" does not restart manually stopped containers
        if policy.condition == RestartPolicy.UNLESS_STOPPED and manually_stopped:
            return False

        # "on-failure" only restarts on non-zero exit
        if policy.condition == RestartPolicy.ON_FAILURE and exit_code == 0:
            return False

        # Check attempt window
        now = datetime.now(timezone.utc)
        window_start = self._window_starts.get(service_name)
        if window_start is not None:
            elapsed = (now - window_start).total_seconds()
            if elapsed > policy.window:
                # Window expired, reset counter
                self._attempt_counts[service_name] = 0
                self._window_starts[service_name] = now
        else:
            self._window_starts[service_name] = now

        # Check max attempts (0 = unlimited)
        if policy.max_attempts > 0:
            if self._attempt_counts[service_name] >= policy.max_attempts:
                raise ComposeRestartPolicyExhaustedError(
                    service_name, policy.max_attempts
                )

        return True

    def record_restart(self, service_name: str) -> None:
        """Record that a restart was performed for a service.

        Args:
            service_name: Service that was restarted.
        """
        self._attempt_counts[service_name] += 1
        self._last_restart[service_name] = datetime.now(timezone.utc)
        self._total_restarts += 1

    def reset(self, service_name: str) -> None:
        """Reset the restart counter for a service.

        Args:
            service_name: Service to reset.
        """
        self._attempt_counts.pop(service_name, None)
        self._window_starts.pop(service_name, None)
        self._last_restart.pop(service_name, None)

    def get_attempt_count(self, service_name: str) -> int:
        """Return the current restart attempt count for a service.

        Args:
            service_name: Service name.

        Returns:
            Number of restart attempts in the current window.
        """
        return self._attempt_counts.get(service_name, 0)

    def get_restart_delay(self, policy: RestartPolicySpec) -> float:
        """Return the delay before the next restart attempt.

        Args:
            policy: Restart policy specification.

        Returns:
            Delay in seconds.
        """
        return policy.delay

    @property
    def total_restarts(self) -> int:
        """Return the total number of restarts across all services."""
        return self._total_restarts


# ============================================================
# ComposeEngine — lifecycle commands
# ============================================================


class ComposeEngine:
    """Core orchestration engine implementing compose lifecycle commands.

    Coordinates the parser, dependency resolver, network manager,
    volume manager, restart policy engine, and health check gate
    to implement the full compose lifecycle: up, down, restart,
    scale, logs, ps, exec, and top.

    The engine maintains the ComposeProject runtime state, tracking
    all service instances, their health status, and resource
    allocations across the compose project.
    """

    def __init__(
        self,
        parser: ComposeParser,
        network_manager: ComposeNetworkManager,
        volume_manager: ComposeVolumeManager,
        dependency_resolver: DependencyResolver,
        restart_policy_engine: RestartPolicyEngine,
        health_check_gate: HealthCheckGate,
        scale_max: int = DEFAULT_SCALE_MAX,
        log_tail_lines: int = DEFAULT_LOG_TAIL_LINES,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize the compose engine.

        Args:
            parser: Compose file parser.
            network_manager: Network manager.
            volume_manager: Volume manager.
            dependency_resolver: Dependency resolver.
            restart_policy_engine: Restart policy engine.
            health_check_gate: Health check gate.
            scale_max: Maximum replicas per service.
            log_tail_lines: Default log tail line count.
            event_bus: Optional event bus for lifecycle events.
        """
        self._parser = parser
        self._network_manager = network_manager
        self._volume_manager = volume_manager
        self._dependency_resolver = dependency_resolver
        self._restart_policy_engine = restart_policy_engine
        self._health_check_gate = health_check_gate
        self._scale_max = scale_max
        self._log_tail_lines = log_tail_lines
        self._event_bus = event_bus
        self._project: Optional[ComposeProject] = None
        self._logs: Dict[str, List[ComposeLogEntry]] = defaultdict(list)
        self._log_sequence = 0
        self._pid_counter = 1000
        self._command_count = 0

    def _emit_event(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        """Emit a lifecycle event to the event bus.

        Args:
            event_type: Event type constant.
            data: Optional event data.
        """
        if self._event_bus is not None and hasattr(self._event_bus, "publish"):
            self._event_bus.publish(event_type, data or {})

    def _next_pid(self) -> int:
        """Generate the next process ID."""
        self._pid_counter += 1
        return self._pid_counter

    def _create_instance(
        self,
        service_name: str,
        replica_index: int,
        service_def: ServiceDefinition,
    ) -> ServiceInstance:
        """Create a new service instance.

        Args:
            service_name: Name of the service.
            replica_index: Replica index (0-based).
            service_def: Service definition.

        Returns:
            New ServiceInstance in CREATED state.
        """
        instance_id = f"{service_name}-{replica_index}-{uuid.uuid4().hex[:6]}"
        container_id = f"cmp-{service_name}-{replica_index}"

        return ServiceInstance(
            instance_id=instance_id,
            service_name=service_name,
            container_id=container_id,
            replica_index=replica_index,
            state=ServiceState.CREATED,
            health_status="starting",
            ports=list(service_def.ports),
            networks=list(service_def.networks),
        )

    def _start_instance(self, instance: ServiceInstance) -> None:
        """Start a service instance (transition to RUNNING).

        Args:
            instance: Instance to start.
        """
        instance.state = ServiceState.RUNNING
        instance.started_at = datetime.now(timezone.utc)
        instance.pid = self._next_pid()
        instance.health_status = "running"

        # Connect to networks
        for network_name in instance.networks:
            try:
                self._network_manager.connect_service(
                    network_name,
                    instance.service_name,
                    instance.instance_id,
                )
            except ComposeNetworkNotFoundError:
                pass  # Network may not exist yet

        self._append_log(
            instance.service_name,
            instance.instance_id,
            f"Container {instance.container_id} started (pid={instance.pid})",
        )

    def _stop_instance(self, instance: ServiceInstance) -> None:
        """Stop a service instance (transition to STOPPED).

        Args:
            instance: Instance to stop.
        """
        instance.state = ServiceState.STOPPED
        instance.exit_code = 0
        instance.health_status = "stopped"

        # Disconnect from networks
        for network_name in instance.networks:
            self._network_manager.disconnect_service(
                network_name,
                instance.service_name,
                instance.instance_id,
            )

        self._append_log(
            instance.service_name,
            instance.instance_id,
            f"Container {instance.container_id} stopped (exit_code=0)",
        )

    def _mark_healthy(self, instance: ServiceInstance) -> None:
        """Mark a service instance as healthy.

        Args:
            instance: Instance to mark.
        """
        instance.state = ServiceState.HEALTHY
        instance.health_status = "healthy"

    def _append_log(
        self,
        service_name: str,
        instance_id: str,
        message: str,
        stream: str = "stdout",
    ) -> None:
        """Append a log entry for a service.

        Args:
            service_name: Service name.
            instance_id: Instance identifier.
            message: Log message.
            stream: Log stream (stdout/stderr).
        """
        self._log_sequence += 1
        entry = ComposeLogEntry(
            timestamp=datetime.now(timezone.utc),
            service_name=service_name,
            instance_id=instance_id,
            stream=stream,
            message=message,
            sequence=self._log_sequence,
        )
        self._logs[service_name].append(entry)

    def up(
        self,
        compose_data: Optional[Dict[str, Any]] = None,
        project_name: str = COMPOSE_PROJECT_NAME,
    ) -> ComposeProject:
        """Bring up all compose services in dependency order.

        Parses the compose file, resolves dependencies, provisions
        networks and volumes, then starts services tier by tier in
        topological order.  Services within the same tier are started
        in parallel (simulated).

        Args:
            compose_data: Compose file data (None for default topology).
            project_name: Project name.

        Returns:
            ComposeProject with all services running.

        Raises:
            ComposeProjectAlreadyRunningError: If the project is already up.
            ComposeCircularDependencyError: If dependency cycles exist.
        """
        self._command_count += 1

        if self._project is not None and self._project.status in (
            ComposeStatus.RUNNING, ComposeStatus.STARTING,
        ):
            raise ComposeProjectAlreadyRunningError(project_name)

        self._emit_event(COMPOSE_UP_STARTED, {"project": project_name})

        # Parse compose file
        compose_file = self._parser.parse(compose_data)
        compose_file.project_name = project_name

        # Resolve dependency order
        startup_order = self._dependency_resolver.resolve(compose_file)

        # Create project
        project = ComposeProject(
            name=project_name,
            status=ComposeStatus.STARTING,
            compose_file=compose_file,
            started_at=datetime.now(timezone.utc),
            startup_order=startup_order,
        )

        # Provision networks
        for net_name, net_config in compose_file.networks.items():
            net_id = self._network_manager.create_network(net_config)
            project.networks[net_name] = net_id
            self._emit_event(COMPOSE_NETWORK_CREATED, {"network": net_name})

        # Provision volumes
        for vol_name, vol_config in compose_file.volumes.items():
            vol_path = self._volume_manager.create_volume(vol_config)
            project.volumes[vol_name] = vol_path
            self._emit_event(COMPOSE_VOLUME_CREATED, {"volume": vol_name})

        # Start services tier by tier
        for tier in startup_order:
            for service_name in tier:
                if service_name not in compose_file.services:
                    continue

                service_def = compose_file.services[service_name]
                replicas = service_def.deploy.replicas
                instances: List[ServiceInstance] = []

                self._emit_event(COMPOSE_SERVICE_STARTING, {"service": service_name})

                for i in range(replicas):
                    instance = self._create_instance(service_name, i, service_def)
                    self._start_instance(instance)

                    # Run health check
                    healthy = self._health_check_gate.check(
                        service_name, instance, service_def.healthcheck
                    )
                    if healthy:
                        self._mark_healthy(instance)
                        self._emit_event(COMPOSE_SERVICE_HEALTHY, {
                            "service": service_name,
                            "instance": instance.instance_id,
                        })

                    instances.append(instance)

                project.services[service_name] = instances

                self._emit_event(COMPOSE_SERVICE_STARTED, {"service": service_name})
                self._emit_event(COMPOSE_DEPENDENCY_RESOLVED, {"service": service_name})

        project.status = ComposeStatus.RUNNING
        self._project = project

        self._emit_event(COMPOSE_UP_COMPLETED, {
            "project": project_name,
            "services": len(compose_file.services),
        })

        logger.info(
            "Compose project '%s' is up: %d services, %d networks, %d volumes",
            project_name,
            len(project.services),
            len(project.networks),
            len(project.volumes),
        )

        return project

    def down(self, remove_volumes: bool = False) -> None:
        """Tear down all compose services in reverse dependency order.

        Stops all service instances, disconnects from networks,
        removes networks, and optionally removes volumes.

        Args:
            remove_volumes: Whether to also remove named volumes.

        Raises:
            ComposeServiceNotFoundError: If the project is not running.
        """
        self._command_count += 1

        if self._project is None:
            return

        self._emit_event(COMPOSE_DOWN_STARTED, {"project": self._project.name})

        self._project.status = ComposeStatus.STOPPING

        # Stop services in reverse startup order
        if self._project.startup_order:
            reverse_order = list(reversed(self._project.startup_order))
            for tier in reverse_order:
                for service_name in tier:
                    instances = self._project.services.get(service_name, [])
                    for instance in instances:
                        if instance.state in (
                            ServiceState.RUNNING,
                            ServiceState.HEALTHY,
                        ):
                            self._stop_instance(instance)
                            self._emit_event(COMPOSE_SERVICE_STOPPED, {
                                "service": service_name,
                            })

        # Remove networks
        self._network_manager.cleanup()

        # Remove volumes if requested
        if remove_volumes:
            self._volume_manager.cleanup()

        self._project.status = ComposeStatus.STOPPED
        self._emit_event(COMPOSE_DOWN_COMPLETED, {"project": self._project.name})

        logger.info("Compose project '%s' is down", self._project.name)
        self._project = None

    def restart(self, service_name: str) -> List[ServiceInstance]:
        """Restart a specific service.

        Stops all instances, then starts new instances with the same
        configuration.  Restart counts are incremented.

        Args:
            service_name: Service to restart.

        Returns:
            List of new service instances.

        Raises:
            ComposeServiceNotFoundError: If the service does not exist.
        """
        self._command_count += 1

        if self._project is None or self._project.compose_file is None:
            raise ComposeServiceNotFoundError(service_name)

        if service_name not in self._project.compose_file.services:
            raise ComposeServiceNotFoundError(service_name)

        service_def = self._project.compose_file.services[service_name]
        old_instances = self._project.services.get(service_name, [])

        # Stop old instances
        for instance in old_instances:
            if instance.state in (ServiceState.RUNNING, ServiceState.HEALTHY):
                self._stop_instance(instance)

        # Start new instances
        new_instances: List[ServiceInstance] = []
        replicas = service_def.deploy.replicas

        for i in range(replicas):
            instance = self._create_instance(service_name, i, service_def)
            # Carry forward restart count
            if i < len(old_instances):
                instance.restart_count = old_instances[i].restart_count + 1
            self._start_instance(instance)

            healthy = self._health_check_gate.check(
                service_name, instance, service_def.healthcheck
            )
            if healthy:
                self._mark_healthy(instance)

            new_instances.append(instance)

        self._project.services[service_name] = new_instances
        self._restart_policy_engine.record_restart(service_name)
        self._emit_event(COMPOSE_SERVICE_RESTARTED, {"service": service_name})

        logger.info("Restarted service '%s' (%d instances)", service_name, len(new_instances))

        return new_instances

    def scale(self, service_name: str, replicas: int) -> List[ServiceInstance]:
        """Scale a service to the specified replica count.

        Adds or removes instances to match the desired replica count.
        New instances are started and health-checked.  Excess instances
        are stopped.

        Args:
            service_name: Service to scale.
            replicas: Desired replica count.

        Returns:
            List of service instances after scaling.

        Raises:
            ComposeServiceNotFoundError: If the service does not exist.
            ComposeScaleError: If the desired count exceeds the maximum.
        """
        self._command_count += 1

        if self._project is None or self._project.compose_file is None:
            raise ComposeServiceNotFoundError(service_name)

        if service_name not in self._project.compose_file.services:
            raise ComposeServiceNotFoundError(service_name)

        if replicas > self._scale_max:
            raise ComposeScaleError(
                service_name, replicas,
                f"Exceeds maximum replica count of {self._scale_max}",
            )

        if replicas < 0:
            raise ComposeScaleError(
                service_name, replicas,
                "Replica count cannot be negative",
            )

        service_def = self._project.compose_file.services[service_name]
        current = self._project.services.get(service_name, [])
        current_count = len(current)

        if replicas > current_count:
            # Scale up: add new instances
            for i in range(current_count, replicas):
                instance = self._create_instance(service_name, i, service_def)
                self._start_instance(instance)
                healthy = self._health_check_gate.check(
                    service_name, instance, service_def.healthcheck
                )
                if healthy:
                    self._mark_healthy(instance)
                current.append(instance)
        elif replicas < current_count:
            # Scale down: stop excess instances (from the end)
            while len(current) > replicas:
                instance = current.pop()
                if instance.state in (ServiceState.RUNNING, ServiceState.HEALTHY):
                    self._stop_instance(instance)

        self._project.services[service_name] = current
        self._emit_event(COMPOSE_SERVICE_SCALED, {
            "service": service_name,
            "replicas": replicas,
        })

        logger.info(
            "Scaled service '%s' from %d to %d replicas",
            service_name, current_count, replicas,
        )

        return list(current)

    def logs(
        self,
        service_name: Optional[str] = None,
        tail: Optional[int] = None,
        follow: bool = False,
    ) -> List[ComposeLogEntry]:
        """Retrieve logs for a service or all services.

        Args:
            service_name: Service to retrieve logs for (None for all).
            tail: Number of most recent lines to return.
            follow: Whether to follow (not implemented in simulation).

        Returns:
            List of log entries.

        Raises:
            ComposeServiceNotFoundError: If the service does not exist.
        """
        self._command_count += 1

        if service_name is not None:
            if self._project and self._project.compose_file:
                if service_name not in self._project.compose_file.services:
                    raise ComposeServiceNotFoundError(service_name)
            entries = list(self._logs.get(service_name, []))
        else:
            # Aggregate all logs sorted by sequence
            entries = []
            for svc_logs in self._logs.values():
                entries.extend(svc_logs)
            entries.sort(key=lambda e: e.sequence)

        # Apply tail limit
        if tail is not None and tail > 0:
            entries = entries[-tail:]

        return entries

    def ps(self) -> Dict[str, List[ServiceInstance]]:
        """Show status of all compose services.

        Returns:
            Dictionary mapping service names to their instances.
        """
        self._command_count += 1

        if self._project is None:
            return {}

        return dict(self._project.services)

    def exec(
        self,
        service_name: str,
        command: str,
        instance_index: int = 0,
    ) -> str:
        """Execute a command in a running service container.

        Args:
            service_name: Service to exec into.
            command: Command to execute.
            instance_index: Which replica to exec into (0-based).

        Returns:
            Command output (simulated).

        Raises:
            ComposeServiceNotFoundError: If the service does not exist.
            ComposeExecError: If the exec operation fails.
        """
        self._command_count += 1

        if self._project is None:
            raise ComposeServiceNotFoundError(service_name)

        instances = self._project.services.get(service_name)
        if not instances:
            raise ComposeServiceNotFoundError(service_name)

        if instance_index >= len(instances):
            raise ComposeExecError(
                service_name, command,
                f"Instance index {instance_index} out of range "
                f"(service has {len(instances)} instances)",
            )

        instance = instances[instance_index]
        if instance.state not in (ServiceState.RUNNING, ServiceState.HEALTHY):
            raise ComposeExecError(
                service_name, command,
                f"Container is not running (state={instance.state.value})",
            )

        # Simulate command execution
        output = (
            f"exec {command} in {instance.container_id} "
            f"(pid={instance.pid}): OK"
        )

        self._append_log(service_name, instance.instance_id, f"exec: {command}")

        return output

    def top(self, service_name: str) -> List[ProcessInfo]:
        """Show running processes in a service container.

        Args:
            service_name: Service to inspect.

        Returns:
            List of ProcessInfo for running processes.

        Raises:
            ComposeServiceNotFoundError: If the service does not exist.
        """
        self._command_count += 1

        if self._project is None:
            raise ComposeServiceNotFoundError(service_name)

        instances = self._project.services.get(service_name)
        if not instances:
            raise ComposeServiceNotFoundError(service_name)

        processes: List[ProcessInfo] = []
        for instance in instances:
            if instance.state in (ServiceState.RUNNING, ServiceState.HEALTHY):
                # Simulate process list
                processes.append(ProcessInfo(
                    pid=instance.pid or 0,
                    user="fizzbuzz",
                    cpu_percent=round(random.uniform(0.1, 15.0), 1),
                    memory_mb=round(random.uniform(32.0, 256.0), 1),
                    command=f"fizzbuzz-{service_name} --service",
                ))
                # Simulated child process
                processes.append(ProcessInfo(
                    pid=(instance.pid or 0) + 1,
                    user="fizzbuzz",
                    cpu_percent=round(random.uniform(0.01, 2.0), 2),
                    memory_mb=round(random.uniform(8.0, 64.0), 1),
                    command=f"fizzbuzz-health --check {service_name}",
                ))

        return processes

    def config(self) -> Optional[ComposeFile]:
        """Return the resolved compose file configuration.

        Returns:
            The parsed ComposeFile, or None if not yet parsed.
        """
        self._command_count += 1
        if self._project and self._project.compose_file:
            return self._project.compose_file
        return self._parser.parse()

    def get_project(self) -> Optional[ComposeProject]:
        """Return the current compose project state.

        Returns:
            ComposeProject, or None if not running.
        """
        return self._project

    def get_stats(self) -> ComposeStats:
        """Return aggregate statistics for the compose engine.

        Returns:
            ComposeStats with current metrics.
        """
        stats = ComposeStats()

        if self._project and self._project.compose_file:
            stats.total_services = len(self._project.compose_file.services)

            for svc_name, instances in self._project.services.items():
                for inst in instances:
                    stats.total_instances += 1
                    if inst.state in (ServiceState.RUNNING, ServiceState.HEALTHY):
                        stats.running_instances += 1
                    if inst.state == ServiceState.HEALTHY:
                        stats.healthy_services += 1

            running_svcs = set()
            for svc_name, instances in self._project.services.items():
                for inst in instances:
                    if inst.state in (ServiceState.RUNNING, ServiceState.HEALTHY):
                        running_svcs.add(svc_name)
            stats.running_services = len(running_svcs)

            stats.total_networks = len(self._project.networks)
            stats.total_volumes = len(self._project.volumes)

            if self._project.started_at:
                stats.uptime_seconds = (
                    datetime.now(timezone.utc) - self._project.started_at
                ).total_seconds()

        stats.total_restarts = self._restart_policy_engine.total_restarts
        stats.total_health_checks = self._health_check_gate.check_count
        stats.compose_up_count = sum(
            1 for _ in self._logs.values()
        )  # Approximation

        return stats

    @property
    def command_count(self) -> int:
        """Return the total number of commands executed."""
        return self._command_count

    @property
    def project(self) -> Optional[ComposeProject]:
        """Return the current compose project."""
        return self._project


# ============================================================
# ComposeDashboard — ASCII dashboard rendering
# ============================================================


class ComposeDashboard:
    """ASCII dashboard rendering for compose service status.

    Renders a service table showing name, container ID, image, state,
    health, ports, and uptime for each service instance.  Also renders
    a resource utilization bar chart showing CPU and memory usage per
    service.
    """

    def __init__(self, width: int = COMPOSE_DASHBOARD_WIDTH) -> None:
        """Initialize the dashboard renderer.

        Args:
            width: Dashboard width in characters.
        """
        self._width = width
        self._render_count = 0

    def render(self, engine: ComposeEngine) -> str:
        """Render the complete compose dashboard.

        Args:
            engine: ComposeEngine instance to render.

        Returns:
            ASCII dashboard string.
        """
        self._render_count += 1
        project = engine.get_project()
        lines: List[str] = []

        # Header
        lines.append("=" * self._width)
        lines.append("FizzCompose Dashboard".center(self._width))
        lines.append("=" * self._width)

        if project is None:
            lines.append("No compose project is running.".center(self._width))
            lines.append("=" * self._width)
            return "\n".join(lines)

        # Project status
        lines.append(f"  Project: {project.name}")
        lines.append(f"  Status:  {project.status.value}")
        if project.started_at:
            uptime = (datetime.now(timezone.utc) - project.started_at).total_seconds()
            lines.append(f"  Uptime:  {uptime:.0f}s")
        lines.append(f"  Services: {len(project.services)}")
        lines.append("-" * self._width)

        # Service table
        lines.append(self._render_service_table(project))

        # Resource utilization
        lines.append("-" * self._width)
        lines.append(self._render_resource_bars(project))

        lines.append("=" * self._width)
        return "\n".join(lines)

    def _render_service_table(self, project: ComposeProject) -> str:
        """Render the service status table.

        Args:
            project: ComposeProject to render.

        Returns:
            ASCII table string.
        """
        rows: List[str] = []
        header = f"  {'SERVICE':<20} {'STATE':<12} {'HEALTH':<10} {'REPLICAS':<10} {'PORTS':<15}"
        rows.append(header)
        rows.append("  " + "-" * (self._width - 4))

        for svc_name in sorted(project.services.keys()):
            instances = project.services[svc_name]
            running = sum(
                1 for i in instances
                if i.state in (ServiceState.RUNNING, ServiceState.HEALTHY)
            )
            total = len(instances)

            # Determine overall state
            if all(i.state == ServiceState.HEALTHY for i in instances):
                state = "healthy"
                health = "passing"
            elif any(i.state in (ServiceState.RUNNING, ServiceState.HEALTHY) for i in instances):
                state = "running"
                health = "checking"
            else:
                state = "stopped"
                health = "n/a"

            # Format ports
            port_str = ""
            if instances and instances[0].ports:
                port_str = ",".join(
                    f"{p.host_port}" for p in instances[0].ports[:2]
                )

            row = f"  {svc_name:<20} {state:<12} {health:<10} {running}/{total:<8} {port_str:<15}"
            rows.append(row)

        return "\n".join(rows)

    def _render_resource_bars(self, project: ComposeProject) -> str:
        """Render resource utilization bar charts.

        Args:
            project: ComposeProject to render.

        Returns:
            ASCII bar chart string.
        """
        rows: List[str] = []
        rows.append("  Resource Utilization:")
        bar_width = self._width - 30

        for svc_name in sorted(project.services.keys()):
            instances = project.services[svc_name]
            running = sum(
                1 for i in instances
                if i.state in (ServiceState.RUNNING, ServiceState.HEALTHY)
            )
            if running == 0:
                continue

            # Simulate CPU usage
            cpu_pct = min(random.uniform(5.0, 45.0), 100.0)
            cpu_filled = int(bar_width * cpu_pct / 100.0)
            cpu_bar = "#" * cpu_filled + "." * (bar_width - cpu_filled)

            rows.append(f"  {svc_name[:16]:<16} CPU [{cpu_bar}] {cpu_pct:5.1f}%")

        return "\n".join(rows)

    @property
    def render_count(self) -> int:
        """Return the total number of dashboard renders."""
        return self._render_count

    def render_services(self, engine: ComposeEngine) -> str:
        """Render just the service table.

        Args:
            engine: ComposeEngine instance.

        Returns:
            ASCII service table string.
        """
        project = engine.get_project()
        if project is None:
            return "No compose project is running."
        return self._render_service_table(project)


# ============================================================
# FizzComposeMiddleware — IMiddleware implementation
# ============================================================


class FizzComposeMiddleware(IMiddleware):
    """Middleware that makes compose application topology available during evaluation.

    When a FizzBuzz evaluation is requested, this middleware resolves
    which compose service is handling the evaluation, attaches
    topology metadata to the processing context, and optionally
    renders the compose dashboard.

    The middleware integrates the compose engine into the FizzBuzz
    middleware pipeline at priority 115, providing service discovery
    and dependency resolution context to downstream middleware and
    the rule engine.
    """

    def __init__(
        self,
        engine: ComposeEngine,
        dashboard_width: int = COMPOSE_DASHBOARD_WIDTH,
        enable_dashboard: bool = False,
    ) -> None:
        """Initialize the middleware.

        Args:
            engine: ComposeEngine instance.
            dashboard_width: ASCII dashboard width.
            enable_dashboard: Whether to enable dashboard rendering.
        """
        self.engine = engine
        self.dashboard = ComposeDashboard(width=dashboard_width)
        self._enable_dashboard = enable_dashboard
        self._evaluation_count = 0
        self._errors = 0

    def get_name(self) -> str:
        """Return the middleware name."""
        return "FizzComposeMiddleware"

    def get_priority(self) -> int:
        """Return the middleware priority."""
        return MIDDLEWARE_PRIORITY

    @property
    def priority(self) -> int:
        """Return middleware priority (115)."""
        return MIDDLEWARE_PRIORITY

    @property
    def name(self) -> str:
        """Return the middleware name (convenience property)."""
        return "FizzComposeMiddleware"

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process a FizzBuzz evaluation through the compose middleware.

        Records which compose service is handling the evaluation,
        attaches topology metadata to the context, delegates to the
        next handler, and tracks evaluation counts per service.

        Args:
            context: Processing context.
            next_handler: Next middleware in the pipeline.

        Returns:
            The processed context.

        Raises:
            ComposeMiddlewareError: If topology resolution fails.
        """
        self._evaluation_count += 1

        number = context.number if hasattr(context, "number") else 0

        try:
            project = self.engine.get_project()

            # Attach compose topology to context metadata
            if hasattr(context, "metadata") and isinstance(context.metadata, dict):
                context.metadata["compose_evaluation_count"] = self._evaluation_count
                if project is not None:
                    context.metadata["compose_project"] = project.name
                    context.metadata["compose_status"] = project.status.value
                    context.metadata["compose_services"] = len(project.services)
                    context.metadata["compose_service_handler"] = "fizzbuzz-core"

            # Delegate to next handler
            result_context = next_handler(context)

            # Optionally render dashboard
            if self._enable_dashboard and self._evaluation_count % 10 == 0:
                self.dashboard.render(self.engine)

            return result_context

        except ComposeError as exc:
            self._errors += 1
            raise ComposeMiddlewareError(
                f"Evaluation {number}: {exc}"
            ) from exc

    def render_dashboard(self) -> str:
        """Render the compose dashboard.

        Returns:
            ASCII dashboard string.
        """
        return self.dashboard.render(self.engine)

    @property
    def evaluation_count(self) -> int:
        """Return the total number of evaluations processed."""
        return self._evaluation_count

    @property
    def error_count(self) -> int:
        """Return the total number of errors encountered."""
        return self._errors


# ============================================================
# Factory Function
# ============================================================


def create_fizzcompose_subsystem(
    compose_file_path: str = COMPOSE_FILE_NAME,
    project_name: str = COMPOSE_PROJECT_NAME,
    health_check_interval: float = DEFAULT_HEALTH_CHECK_INTERVAL,
    health_check_timeout: float = DEFAULT_HEALTH_CHECK_TIMEOUT,
    restart_delay: float = DEFAULT_RESTART_DELAY,
    restart_max_attempts: int = DEFAULT_MAX_RESTART_ATTEMPTS,
    restart_window: float = DEFAULT_RESTART_WINDOW,
    scale_max: int = DEFAULT_SCALE_MAX,
    log_tail_lines: int = DEFAULT_LOG_TAIL_LINES,
    dashboard_width: int = COMPOSE_DASHBOARD_WIDTH,
    enable_dashboard: bool = False,
    event_bus: Optional[Any] = None,
) -> tuple:
    """Create and wire the complete FizzCompose subsystem.

    Factory function that instantiates the compose engine with all
    supporting managers (network, volume, dependency resolver, restart
    policy engine, health check gate), parses the compose file,
    and creates the middleware, ready for integration into the
    FizzBuzz evaluation pipeline.

    Args:
        compose_file_path: Path to the compose file.
        project_name: Compose project name.
        health_check_interval: Health check poll interval.
        health_check_timeout: Health check gate timeout.
        restart_delay: Delay between restart attempts.
        restart_max_attempts: Maximum restart attempts.
        restart_window: Restart attempt counter reset window.
        scale_max: Maximum replicas per service.
        log_tail_lines: Default log tail line count.
        dashboard_width: ASCII dashboard width.
        enable_dashboard: Whether to enable dashboard rendering.
        event_bus: Optional event bus for lifecycle events.

    Returns:
        Tuple of (ComposeEngine, FizzComposeMiddleware).
    """
    parser = ComposeParser()
    network_manager = ComposeNetworkManager()
    volume_manager = ComposeVolumeManager()
    health_check_gate = HealthCheckGate(
        interval=health_check_interval,
        timeout=health_check_timeout,
    )
    dependency_resolver = DependencyResolver(
        health_check_gate=health_check_gate,
    )
    restart_policy_engine = RestartPolicyEngine(
        default_delay=restart_delay,
        default_max_attempts=restart_max_attempts,
        default_window=restart_window,
    )

    engine = ComposeEngine(
        parser=parser,
        network_manager=network_manager,
        volume_manager=volume_manager,
        dependency_resolver=dependency_resolver,
        restart_policy_engine=restart_policy_engine,
        health_check_gate=health_check_gate,
        scale_max=scale_max,
        log_tail_lines=log_tail_lines,
        event_bus=event_bus,
    )

    middleware = FizzComposeMiddleware(
        engine=engine,
        dashboard_width=dashboard_width,
        enable_dashboard=enable_dashboard,
    )

    logger.info("FizzCompose subsystem created and wired")

    return engine, middleware
