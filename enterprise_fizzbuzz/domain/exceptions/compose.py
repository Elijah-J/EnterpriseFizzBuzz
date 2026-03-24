"""
Enterprise FizzBuzz Platform - FizzCompose Multi-Container Application Orchestration Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


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

    def __init__(self, cycle: list) -> None:
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

