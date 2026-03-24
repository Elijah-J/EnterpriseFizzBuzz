"""FizzKube Container Orchestration properties"""

from __future__ import annotations

from typing import Any


class FizzkubeConfigMixin:
    """Configuration properties for the fizzkube subsystem."""

    # ------------------------------------------------------------------
    # FizzKube Container Orchestration properties
    # ------------------------------------------------------------------

    @property
    def fizzkube_enabled(self) -> bool:
        """Whether FizzKube container orchestration is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzkube", {}).get("enabled", False)

    @property
    def fizzkube_num_nodes(self) -> int:
        """Number of simulated worker nodes in the cluster."""
        self._ensure_loaded()
        return self._raw_config.get("fizzkube", {}).get("num_nodes", 3)

    @property
    def fizzkube_default_replicas(self) -> int:
        """Default desired replica count per ReplicaSet."""
        self._ensure_loaded()
        return self._raw_config.get("fizzkube", {}).get("default_replicas", 2)

    @property
    def fizzkube_cpu_per_node(self) -> int:
        """CPU capacity per node in milliFizz."""
        self._ensure_loaded()
        return self._raw_config.get("fizzkube", {}).get("cpu_per_node", 4000)

    @property
    def fizzkube_memory_per_node(self) -> int:
        """Memory capacity per node in FizzBytes."""
        self._ensure_loaded()
        return self._raw_config.get("fizzkube", {}).get("memory_per_node", 8192)

    @property
    def fizzkube_pod_cpu_request(self) -> int:
        """CPU requested per pod in milliFizz."""
        self._ensure_loaded()
        return self._raw_config.get("fizzkube", {}).get("pod_cpu_request", 100)

    @property
    def fizzkube_pod_memory_request(self) -> int:
        """Memory requested per pod in FizzBytes."""
        self._ensure_loaded()
        return self._raw_config.get("fizzkube", {}).get("pod_memory_request", 128)

    @property
    def fizzkube_pod_cpu_limit(self) -> int:
        """CPU limit per pod in milliFizz."""
        self._ensure_loaded()
        return self._raw_config.get("fizzkube", {}).get("pod_cpu_limit", 200)

    @property
    def fizzkube_pod_memory_limit(self) -> int:
        """Memory limit per pod in FizzBytes."""
        self._ensure_loaded()
        return self._raw_config.get("fizzkube", {}).get("pod_memory_limit", 256)

    @property
    def fizzkube_hpa_enabled(self) -> bool:
        """Whether the Horizontal Pod Autoscaler is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzkube", {}).get("hpa", {}).get("enabled", True)

    @property
    def fizzkube_hpa_min_replicas(self) -> int:
        """Minimum replica count for HPA."""
        self._ensure_loaded()
        return self._raw_config.get("fizzkube", {}).get("hpa", {}).get("min_replicas", 1)

    @property
    def fizzkube_hpa_max_replicas(self) -> int:
        """Maximum replica count for HPA."""
        self._ensure_loaded()
        return self._raw_config.get("fizzkube", {}).get("hpa", {}).get("max_replicas", 10)

    @property
    def fizzkube_hpa_target_cpu_utilization(self) -> int:
        """Target CPU utilization percentage for HPA."""
        self._ensure_loaded()
        return self._raw_config.get("fizzkube", {}).get("hpa", {}).get("target_cpu_utilization", 70)

    @property
    def fizzkube_hpa_scale_up_cooldown(self) -> int:
        """Cooldown seconds after scale-up."""
        self._ensure_loaded()
        return self._raw_config.get("fizzkube", {}).get("hpa", {}).get("scale_up_cooldown_seconds", 15)

    @property
    def fizzkube_hpa_scale_down_cooldown(self) -> int:
        """Cooldown seconds after scale-down."""
        self._ensure_loaded()
        return self._raw_config.get("fizzkube", {}).get("hpa", {}).get("scale_down_cooldown_seconds", 30)

    @property
    def fizzkube_namespace(self) -> str:
        """Default Kubernetes namespace."""
        self._ensure_loaded()
        return self._raw_config.get("fizzkube", {}).get("namespace", "fizzbuzz-production")

    @property
    def fizzkube_resource_quota_cpu(self) -> int:
        """Namespace CPU quota in milliFizz."""
        self._ensure_loaded()
        return self._raw_config.get("fizzkube", {}).get("resource_quota", {}).get("cpu_limit", 16000)

    @property
    def fizzkube_resource_quota_memory(self) -> int:
        """Namespace memory quota in FizzBytes."""
        self._ensure_loaded()
        return self._raw_config.get("fizzkube", {}).get("resource_quota", {}).get("memory_limit", 32768)

    @property
    def fizzkube_dashboard_width(self) -> int:
        """Dashboard width for the FizzKube dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzkube", {}).get("dashboard", {}).get("width", 60)

