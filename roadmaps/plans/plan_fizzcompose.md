# Implementation Plan: FizzCompose -- Multi-Container Application Orchestration

**Date:** 2026-03-24
**Feature:** Idea 3 from Brainstorm Report v17
**Target File:** `enterprise_fizzbuzz/infrastructure/fizzcompose.py` (~3,200 lines)
**Test File:** `tests/test_fizzcompose.py` (~400 lines)
**Re-export Stub:** `fizzcompose.py` (root level)

---

## 1. Class Inventory

### Core Classes

| # | Class | Responsibility | Approx. Lines |
|---|-------|---------------|---------------|
| 1 | `ComposeFile` | Top-level data model representing a parsed `fizzbuzz-compose.yaml` — holds version, services map, networks map, volumes map | ~60 |
| 2 | `ServiceDefinition` | Per-service configuration: image, build, depends_on, environment, env_file, ports, volumes, networks, deploy spec (replicas, resources, restart_policy), healthcheck, labels, command, working_dir, user | ~80 |
| 3 | `ComposeParser` | Parses and validates `fizzbuzz-compose.yaml` against the compose schema. Resolves variable interpolation (`${VARIABLE:-default}`), validates image references, checks for circular dependencies in depends_on graph | ~280 |
| 4 | `DependencyResolver` | Constructs a DAG from service `depends_on` declarations. Performs topological sort using Kahn's algorithm. Detects cycles. Supports three dependency conditions: `service_started`, `service_healthy`, `service_completed_successfully`. Implements health-check gate polling | ~350 |
| 5 | `ComposeEngine` | Core orchestration engine implementing lifecycle commands: `up`, `down`, `restart`, `scale`, `logs`, `ps`, `exec`, `top`. Coordinates all managers and resolvers | ~500 |
| 6 | `ComposeNetworkManager` | Creates and manages compose-scoped networks via FizzCNI. Handles service-to-network mapping, network isolation, DNS-based service name resolution | ~250 |
| 7 | `ComposeVolumeManager` | Creates and manages named volumes and bind mounts. Volumes are FizzOverlay persistent layers. Supports shared state across services | ~250 |
| 8 | `RestartPolicyEngine` | Monitors container exits and applies configured restart policies (`always`, `on-failure`, `unless-stopped`, `no`). Tracks attempt counts with configurable delay and reset window | ~200 |
| 9 | `HealthCheckGate` | Executes health check commands against containers at configurable intervals with timeout. Reports healthy/unhealthy status. Used by DependencyResolver for `service_healthy` condition gating | ~180 |
| 10 | `FizzComposeMiddleware` | IMiddleware implementation (priority 115). Makes compose application topology available during FizzBuzz evaluation for service discovery and dependency resolution context | ~120 |
| 11 | `ComposeDashboard` | ASCII dashboard rendering for compose service status. Renders service table with name, container ID, image, state, health, ports, uptime. Bar chart for resource utilization per service | ~200 |
| 12 | `ComposeServiceGroup` | Defines one of the 12 logical service groups. Maps group name to its constituent infrastructure module list, default image, and default resource profile | ~80 |

---

## 2. Service Groups (12 Groups)

Each service group aggregates related infrastructure modules into a single deployable service unit. Groups are defined in the default `fizzbuzz-compose.yaml` embedded in the module.

| # | Service Group | Image | Modules |
|---|--------------|-------|---------|
| 1 | `fizzbuzz-core` | `fizzbuzz-eval:latest` | Rule engine, middleware pipeline, formatter, FizzBuzz evaluator, anti-corruption layer |
| 2 | `fizzbuzz-data` | `fizzbuzz-data:latest` | SQLite persistence, filesystem persistence, in-memory persistence, schema evolution, CDC |
| 3 | `fizzbuzz-cache` | `fizzbuzz-cache:latest` | MESI cache coherence, query optimizer, columnar storage |
| 4 | `fizzbuzz-network` | `fizzbuzz-network:latest` | TCP/IP stack, DNS server, reverse proxy, service mesh, HTTP/2 protocol |
| 5 | `fizzbuzz-security` | `fizzbuzz-security:latest` | RBAC, HMAC auth, capability security, secrets vault, compliance (SOX/GDPR/HIPAA) |
| 6 | `fizzbuzz-observability` | `fizzbuzz-observability:latest` | OpenTelemetry, flame graphs, SLA monitoring, metrics, correlation engine, model checker |
| 7 | `fizzbuzz-compute` | `fizzbuzz-compute:latest` | Bytecode VM, JIT compiler, cross-compiler, quantum simulator, neural network, genetic algorithm |
| 8 | `fizzbuzz-devtools` | `fizzbuzz-devtools:latest` | Debug adapter, package manager, FizzLang DSL, version control, assembler, regex engine |
| 9 | `fizzbuzz-platform` | `fizzbuzz-platform:latest` | OS kernel, memory allocator, garbage collector, IPC, process migration, bootloader |
| 10 | `fizzbuzz-enterprise` | `fizzbuzz-enterprise:latest` | Blockchain, smart contracts, billing, feature flags, event sourcing, CQRS, webhooks |
| 11 | `fizzbuzz-ops` | `fizzbuzz-ops:latest` | FizzBob cognitive load, approval workflow, pager, succession planning, performance review, org hierarchy |
| 12 | `fizzbuzz-exotic` | `fizzbuzz-exotic:latest` | Ray tracer, protein folder, audio synthesizer, video codec, typesetter, spreadsheet, spatial database, digital twin, GPU shader, logic gate simulator |

### Dependency Graph (Default)

```
fizzbuzz-core
├── depends_on: fizzbuzz-data (service_healthy)
├── depends_on: fizzbuzz-cache (service_healthy)
└── depends_on: fizzbuzz-security (service_healthy)

fizzbuzz-data
└── depends_on: fizzbuzz-platform (service_started)

fizzbuzz-cache
└── depends_on: fizzbuzz-data (service_healthy)

fizzbuzz-network
└── depends_on: fizzbuzz-platform (service_started)

fizzbuzz-security
├── depends_on: fizzbuzz-data (service_healthy)
└── depends_on: fizzbuzz-network (service_healthy)

fizzbuzz-observability
├── depends_on: fizzbuzz-core (service_healthy)
└── depends_on: fizzbuzz-network (service_healthy)

fizzbuzz-compute
├── depends_on: fizzbuzz-core (service_healthy)
└── depends_on: fizzbuzz-cache (service_healthy)

fizzbuzz-devtools
├── depends_on: fizzbuzz-core (service_started)
└── depends_on: fizzbuzz-platform (service_started)

fizzbuzz-platform
└── (no dependencies — starts first)

fizzbuzz-enterprise
├── depends_on: fizzbuzz-data (service_healthy)
├── depends_on: fizzbuzz-security (service_healthy)
└── depends_on: fizzbuzz-network (service_healthy)

fizzbuzz-ops
├── depends_on: fizzbuzz-core (service_healthy)
├── depends_on: fizzbuzz-observability (service_healthy)
└── depends_on: fizzbuzz-enterprise (service_started)

fizzbuzz-exotic
├── depends_on: fizzbuzz-core (service_healthy)
├── depends_on: fizzbuzz-compute (service_healthy)
└── depends_on: fizzbuzz-platform (service_started)
```

Topological sort (Kahn's algorithm) produces startup order:
1. `fizzbuzz-platform`
2. `fizzbuzz-data`, `fizzbuzz-network` (parallel — both depend only on platform)
3. `fizzbuzz-cache`, `fizzbuzz-security` (parallel — both depend on data/network)
4. `fizzbuzz-core`, `fizzbuzz-devtools` (parallel — dependencies resolved)
5. `fizzbuzz-compute`, `fizzbuzz-observability`, `fizzbuzz-enterprise` (parallel)
6. `fizzbuzz-ops`, `fizzbuzz-exotic` (parallel — final tier)

---

## 3. Enums

All enums defined within `fizzcompose.py`, following the pattern from `fizzcontainerd.py` (string values for serialization).

```python
class ComposeStatus(Enum):
    """Status of the compose application as a whole."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PARTIALLY_RUNNING = "partially_running"
    STOPPING = "stopping"
    ERROR = "error"


class ServiceState(Enum):
    """Lifecycle state of an individual compose service."""
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
    """Condition under which a service dependency is considered satisfied."""
    SERVICE_STARTED = "service_started"
    SERVICE_HEALTHY = "service_healthy"
    SERVICE_COMPLETED_SUCCESSFULLY = "service_completed_successfully"


class RestartPolicy(Enum):
    """Container restart policy for a compose service."""
    NO = "no"
    ALWAYS = "always"
    ON_FAILURE = "on-failure"
    UNLESS_STOPPED = "unless-stopped"


class VolumeType(Enum):
    """Type of volume mount in a compose service."""
    NAMED = "named"
    BIND = "bind"
    TMPFS = "tmpfs"


class NetworkDriver(Enum):
    """Network driver for a compose-scoped network."""
    BRIDGE = "bridge"
    HOST = "host"
    OVERLAY = "overlay"
    NONE = "none"


class ComposeCommand(Enum):
    """Lifecycle commands supported by the compose engine."""
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
    """Type of health check probe."""
    CMD = "CMD"
    CMD_SHELL = "CMD-SHELL"
    HTTP = "HTTP"
    TCP = "TCP"
    NONE = "NONE"
```

---

## 4. Data Classes

All dataclasses defined within `fizzcompose.py`, following the pattern from `fizzcontainerd.py`.

```python
@dataclass
class NetworkConfig:
    """Configuration for a compose-scoped network.

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

    Attributes:
        variables: Key-value environment variables.
        env_files: List of env file paths.
    """
    variables: Dict[str, str] = field(default_factory=dict)
    env_files: List[str] = field(default_factory=list)


@dataclass
class ResourceLimits:
    """Resource limits and reservations for a service.

    Attributes:
        cpu_limit: CPU limit (e.g., "0.5" for half a core).
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

    Attributes:
        service: Name of the service this depends on.
        condition: Condition for the dependency to be considered satisfied.
    """
    service: str
    condition: DependencyCondition = DependencyCondition.SERVICE_STARTED


@dataclass
class VolumeMount:
    """Volume mount specification for a service container.

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
class ComposeProject:
    """Runtime state of the compose project.

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
```

---

## 5. Constants

```python
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
```

---

## 6. Exception Classes (~20, EFP-CMP prefix)

All exceptions defined in `enterprise_fizzbuzz/domain/exceptions.py`, following the `ContainerdError` pattern.

```python
# ============================================================
# FizzCompose Multi-Container Application Orchestration Exceptions
# ============================================================


class ComposeError(FizzBuzzError):
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
        self.context = {"reason": reason}


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
```

---

## 7. EventType Entries (~15 entries)

Add to `enterprise_fizzbuzz/domain/models.py` in the `EventType` enum, following the containerd pattern:

```python
    # FizzCompose: Multi-Container Application Orchestration events
    COMPOSE_UP_STARTED = auto()
    COMPOSE_UP_COMPLETED = auto()
    COMPOSE_DOWN_STARTED = auto()
    COMPOSE_DOWN_COMPLETED = auto()
    COMPOSE_SERVICE_STARTING = auto()
    COMPOSE_SERVICE_STARTED = auto()
    COMPOSE_SERVICE_HEALTHY = auto()
    COMPOSE_SERVICE_UNHEALTHY = auto()
    COMPOSE_SERVICE_STOPPED = auto()
    COMPOSE_SERVICE_RESTARTED = auto()
    COMPOSE_SERVICE_SCALED = auto()
    COMPOSE_DEPENDENCY_RESOLVED = auto()
    COMPOSE_NETWORK_CREATED = auto()
    COMPOSE_VOLUME_CREATED = auto()
    COMPOSE_DASHBOARD_RENDERED = auto()
```

---

## 8. Config Properties (~10)

Add to `ConfigurationManager` (following existing pattern):

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `fizzcompose_enabled` | `bool` | `False` | Enable the FizzCompose subsystem |
| `fizzcompose_file_path` | `str` | `"fizzbuzz-compose.yaml"` | Path to the compose file |
| `fizzcompose_project_name` | `str` | `"fizzbuzz"` | Compose project name |
| `fizzcompose_health_check_interval` | `float` | `2.0` | Interval between health check polls (seconds) |
| `fizzcompose_health_check_timeout` | `float` | `60.0` | Timeout for dependency health check gates (seconds) |
| `fizzcompose_restart_delay` | `float` | `5.0` | Delay between restart attempts (seconds) |
| `fizzcompose_restart_max_attempts` | `int` | `5` | Maximum restart attempts |
| `fizzcompose_scale_max` | `int` | `10` | Maximum replica count per service |
| `fizzcompose_log_tail_lines` | `int` | `100` | Default number of log lines to display |
| `fizzcompose_dashboard_width` | `int` | `76` | ASCII dashboard width |

---

## 9. YAML Config Section

Add to `config.yaml`:

```yaml
fizzcompose:
  enabled: false
  file_path: "fizzbuzz-compose.yaml"
  project_name: "fizzbuzz"
  health_check:
    interval: 2.0
    timeout: 60.0
  restart:
    delay: 5.0
    max_attempts: 5
    window: 120.0
  scale:
    max_replicas: 10
  log:
    tail_lines: 100
  dashboard:
    width: 76
    enabled: false
  default_network:
    driver: bridge
    subnet: "172.28.0.0/16"
    gateway: "172.28.0.1"
```

---

## 10. CLI Flags

Add to `__main__.py` argument parser:

```python
# FizzCompose flags
parser.add_argument("--fizzcompose", action="store_true",
                    help="Enable FizzCompose multi-container orchestration")
parser.add_argument("--fizzcompose-up", action="store_true",
                    help="Bring up all compose services in dependency order")
parser.add_argument("--fizzcompose-down", action="store_true",
                    help="Tear down all compose services in reverse dependency order")
parser.add_argument("--fizzcompose-ps", action="store_true",
                    help="Show status of all compose services")
parser.add_argument("--fizzcompose-logs", type=str, default=None, metavar="SERVICE",
                    help="Stream logs for a specific service")
parser.add_argument("--fizzcompose-scale", type=str, default=None, metavar="SERVICE=REPLICAS",
                    help="Scale a service to the specified replica count")
parser.add_argument("--fizzcompose-restart", type=str, default=None, metavar="SERVICE",
                    help="Restart a specific service")
parser.add_argument("--fizzcompose-exec", nargs=2, default=None, metavar=("SERVICE", "COMMAND"),
                    help="Execute a command in a running service container")
parser.add_argument("--fizzcompose-top", type=str, default=None, metavar="SERVICE",
                    help="Show running processes in a service container")
parser.add_argument("--fizzcompose-config", action="store_true",
                    help="Validate and display the resolved compose file")
```

---

## 11. Middleware

### FizzComposeMiddleware

- **Class:** `FizzComposeMiddleware(IMiddleware)`
- **Priority:** 115 (one above FizzContainerd's 112, below higher-layer subsystems)
- **Imports:** `IMiddleware` from `enterprise_fizzbuzz.domain.interfaces`, `FizzBuzzResult`, `ProcessingContext`, `EventType` from `enterprise_fizzbuzz.domain.models`
- **Constructor args:** `engine: ComposeEngine`, `dashboard_width: int`, `enable_dashboard: bool`
- **Methods:**
  - `get_name() -> str`: returns `"FizzComposeMiddleware"`
  - `get_priority() -> int`: returns `MIDDLEWARE_PRIORITY` (115)
  - `priority` property: returns `MIDDLEWARE_PRIORITY`
  - `name` property: returns `"FizzComposeMiddleware"`
  - `process(context: ProcessingContext, result: FizzBuzzResult, next_handler: Callable) -> FizzBuzzResult`:
    1. Record which compose service is handling this evaluation
    2. Attach compose topology metadata to the result's context
    3. Delegate to `next_handler(context, result)`
    4. Track evaluation count per service
    5. Optionally render dashboard
    6. Return result

---

## 12. Factory Function

```python
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
```

Function body:
1. Create `ComposeParser` and parse the compose file
2. Create `ComposeNetworkManager`
3. Create `ComposeVolumeManager`
4. Create `HealthCheckGate(interval, timeout)`
5. Create `DependencyResolver(health_check_gate)`
6. Create `RestartPolicyEngine(delay, max_attempts, window)`
7. Create `ComposeEngine(parser, network_manager, volume_manager, dependency_resolver, restart_policy_engine, ...)`
8. Create `FizzComposeMiddleware(engine, dashboard_width, enable_dashboard)`
9. Log subsystem creation
10. Return `(engine, middleware)`

---

## 13. Test Classes

File: `tests/test_fizzcompose.py` (~400 lines, ~45 tests)

| Test Class | Tests | Description |
|-----------|-------|-------------|
| `TestComposeEnums` | 6 | Validate all enum members and their string values |
| `TestComposeDataClasses` | 8 | Test dataclass construction, defaults, field validation |
| `TestComposeParser` | 5 | Parse valid compose files, reject invalid YAML, detect missing fields, variable interpolation |
| `TestDependencyResolver` | 6 | Topological sort, cycle detection, dependency condition handling, startup order, health check gating |
| `TestComposeEngine` | 8 | up/down/restart/scale/logs/ps/exec/top lifecycle operations |
| `TestComposeNetworkManager` | 3 | Network creation, service-to-network mapping, cleanup |
| `TestComposeVolumeManager` | 3 | Named volume creation, bind mount resolution, cleanup |
| `TestRestartPolicyEngine` | 4 | Policy evaluation for all four restart conditions, attempt tracking, window reset |
| `TestHealthCheckGate` | 3 | Health check execution, timeout detection, success polling |
| `TestFizzComposeMiddleware` | 3 | Middleware process delegation, topology attachment, dashboard rendering |
| `TestComposeDashboard` | 2 | ASCII table rendering, resource utilization bar chart |
| `TestComposeServiceGroups` | 2 | All 12 service groups defined, module-to-group mapping |
| `TestComposeExceptions` | 3 | Error code format, context population, inheritance chain |
| `TestCreateFizzcomposeSubsystem` | 2 | Factory function wiring, return types |

**Total:** ~58 tests across 14 test classes

---

## 14. Re-export Stub

File: `fizzcompose.py` (root level)

```python
"""Re-export stub for backward compatibility.

This module re-exports the public API from the canonical location
within the enterprise_fizzbuzz.infrastructure package.
"""

from enterprise_fizzbuzz.infrastructure.fizzcompose import (  # noqa: F401
    ComposeFile,
    ServiceDefinition,
    ComposeParser,
    DependencyResolver,
    ComposeEngine,
    ComposeNetworkManager,
    ComposeVolumeManager,
    RestartPolicyEngine,
    HealthCheckGate,
    FizzComposeMiddleware,
    ComposeDashboard,
    ComposeServiceGroup,
    ComposeStatus,
    ServiceState,
    DependencyCondition,
    RestartPolicy,
    VolumeType,
    NetworkDriver,
    ComposeCommand,
    HealthCheckType,
    create_fizzcompose_subsystem,
)
```

---

## Implementation Order

1. **Constants block** (~14 constants)
2. **Enums block** (8 enums)
3. **Data classes block** (~14 data classes)
4. **ComposeServiceGroup** — static service group definitions with module lists
5. **ComposeParser** — YAML parsing, schema validation, variable interpolation
6. **DependencyResolver** — Kahn's algorithm topological sort, cycle detection, health-check gates
7. **HealthCheckGate** — health check execution and polling
8. **ComposeNetworkManager** — network creation/deletion via FizzCNI integration
9. **ComposeVolumeManager** — volume creation/deletion via FizzOverlay integration
10. **RestartPolicyEngine** — restart policy evaluation and attempt tracking
11. **ComposeEngine** — lifecycle commands (up, down, restart, scale, logs, ps, exec, top)
12. **ComposeDashboard** — ASCII dashboard rendering
13. **FizzComposeMiddleware** — IMiddleware implementation
14. **Factory function** — `create_fizzcompose_subsystem()`

### Parallel Work (exceptions + models)

- Add `ComposeError` hierarchy (20 exceptions, CMP01-CMP20) to `domain/exceptions.py`
- Add 15 `EventType` entries to `domain/models.py`
- Add config properties to `ConfigurationManager`
- Add YAML config section to `config.yaml`
- Add CLI flags to `__main__.py`
- Create re-export stub at root

---

## Line Count Estimate

| Component | Lines |
|-----------|-------|
| Module docstring + imports | ~50 |
| Constants | ~50 |
| Enums | ~100 |
| Data classes | ~300 |
| ComposeServiceGroup | ~80 |
| ComposeParser | ~280 |
| DependencyResolver | ~350 |
| HealthCheckGate | ~180 |
| ComposeNetworkManager | ~250 |
| ComposeVolumeManager | ~250 |
| RestartPolicyEngine | ~200 |
| ComposeEngine | ~500 |
| ComposeDashboard | ~200 |
| FizzComposeMiddleware | ~120 |
| Factory function | ~60 |
| Embedded default compose YAML | ~150 |
| **Total (fizzcompose.py)** | **~3,120** |
| Exceptions (in domain/exceptions.py) | ~250 |
| EventType entries (in domain/models.py) | ~20 |
| Config properties | ~30 |
| CLI flags | ~30 |
| Re-export stub | ~25 |
| Tests | ~400 |
| **Grand Total** | **~3,875** |
