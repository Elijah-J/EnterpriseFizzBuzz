"""Feature descriptor for FizzKube container orchestration."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzKubeFeature(FeatureDescriptor):
    name = "fizzkube"
    description = "Container orchestration that schedules FizzBuzz evaluations as pods across simulated worker nodes"
    middleware_priority = 60
    cli_flags = [
        ("--fizzkube", {"action": "store_true",
                        "help": "Enable FizzKube Container Orchestration: schedule FizzBuzz evaluations as pods across simulated worker nodes"}),
        ("--fizzkube-pods", {"type": int, "default": None, "metavar": "N",
                             "help": "Number of simulated worker nodes in the FizzKube cluster (default: from config)"}),
        ("--fizzkube-dashboard", {"action": "store_true",
                                  "help": "Display the FizzKube Container Orchestration ASCII dashboard after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzkube", False),
            getattr(args, "fizzkube_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzkube import (
            FizzKubeControlPlane,
            FizzKubeMiddleware,
        )

        num_nodes = getattr(args, "fizzkube_pods", None)
        if num_nodes is None:
            num_nodes = config.fizzkube_num_nodes

        cp = FizzKubeControlPlane(
            num_nodes=num_nodes,
            cpu_per_node=config.fizzkube_cpu_per_node,
            memory_per_node=config.fizzkube_memory_per_node,
            pod_cpu_request=config.fizzkube_pod_cpu_request,
            pod_memory_request=config.fizzkube_pod_memory_request,
            pod_cpu_limit=config.fizzkube_pod_cpu_limit,
            pod_memory_limit=config.fizzkube_pod_memory_limit,
            desired_replicas=config.fizzkube_default_replicas,
            namespace_name=config.fizzkube_namespace,
            quota_cpu=config.fizzkube_resource_quota_cpu,
            quota_memory=config.fizzkube_resource_quota_memory,
            hpa_enabled=config.fizzkube_hpa_enabled,
            hpa_min_replicas=config.fizzkube_hpa_min_replicas,
            hpa_max_replicas=config.fizzkube_hpa_max_replicas,
            hpa_target_cpu=config.fizzkube_hpa_target_cpu_utilization,
            rules=list(config.rules),
            event_callback=event_bus.publish if event_bus else None,
        )

        middleware = FizzKubeMiddleware(
            control_plane=cp,
            event_bus=event_bus,
        )

        return cp, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "fizzkube_dashboard", False):
            return None
        if middleware is None:
            return None
        from enterprise_fizzbuzz.infrastructure.fizzkube import FizzKubeDashboard
        return FizzKubeDashboard.render(
            middleware._control_plane,
            width=60,
        )
