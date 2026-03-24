"""Service Mesh Simulation configuration properties"""

from __future__ import annotations

from typing import Any


class ServiceMeshConfigMixin:
    """Configuration properties for the service mesh subsystem."""

    # ----------------------------------------------------------------
    # Service Mesh Simulation configuration properties
    # ----------------------------------------------------------------

    @property
    def service_mesh_enabled(self) -> bool:
        """Whether the Service Mesh Simulation is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("service_mesh", {}).get("enabled", False)

    @property
    def service_mesh_mtls_enabled(self) -> bool:
        """Whether military-grade mTLS (base64) is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("service_mesh", {}).get("mtls", {}).get("enabled", True)

    @property
    def service_mesh_mtls_log_handshakes(self) -> bool:
        """Whether to log every mTLS handshake for compliance theatre."""
        self._ensure_loaded()
        return self._raw_config.get("service_mesh", {}).get("mtls", {}).get("log_handshakes", True)

    @property
    def service_mesh_latency_enabled(self) -> bool:
        """Whether to inject simulated network latency between services."""
        self._ensure_loaded()
        return self._raw_config.get("service_mesh", {}).get("fault_injection", {}).get("latency_enabled", False)

    @property
    def service_mesh_latency_min_ms(self) -> int:
        """Minimum injected latency in milliseconds."""
        self._ensure_loaded()
        return self._raw_config.get("service_mesh", {}).get("fault_injection", {}).get("latency_min_ms", 1)

    @property
    def service_mesh_latency_max_ms(self) -> int:
        """Maximum injected latency in milliseconds."""
        self._ensure_loaded()
        return self._raw_config.get("service_mesh", {}).get("fault_injection", {}).get("latency_max_ms", 10)

    @property
    def service_mesh_packet_loss_enabled(self) -> bool:
        """Whether to simulate packet loss between services."""
        self._ensure_loaded()
        return self._raw_config.get("service_mesh", {}).get("fault_injection", {}).get("packet_loss_enabled", False)

    @property
    def service_mesh_packet_loss_rate(self) -> float:
        """Probability of dropping a request (0.0 - 1.0)."""
        self._ensure_loaded()
        return self._raw_config.get("service_mesh", {}).get("fault_injection", {}).get("packet_loss_rate", 0.05)

    @property
    def service_mesh_canary_enabled(self) -> bool:
        """Whether canary deployments for v2 services are enabled."""
        self._ensure_loaded()
        return self._raw_config.get("service_mesh", {}).get("canary", {}).get("enabled", False)

    @property
    def service_mesh_canary_traffic_percentage(self) -> int:
        """Percentage of traffic routed to canary (v2) services."""
        self._ensure_loaded()
        return self._raw_config.get("service_mesh", {}).get("canary", {}).get("traffic_percentage", 20)

    @property
    def service_mesh_circuit_breaker_enabled(self) -> bool:
        """Whether per-service mesh circuit breakers are enabled."""
        self._ensure_loaded()
        return self._raw_config.get("service_mesh", {}).get("circuit_breaker", {}).get("enabled", True)

    @property
    def service_mesh_circuit_breaker_failure_threshold(self) -> int:
        """Number of failures before tripping the mesh circuit."""
        self._ensure_loaded()
        return self._raw_config.get("service_mesh", {}).get("circuit_breaker", {}).get("failure_threshold", 3)

    @property
    def service_mesh_circuit_breaker_reset_timeout_ms(self) -> int:
        """Time in ms before attempting half-open from open state."""
        self._ensure_loaded()
        return self._raw_config.get("service_mesh", {}).get("circuit_breaker", {}).get("reset_timeout_ms", 5000)

