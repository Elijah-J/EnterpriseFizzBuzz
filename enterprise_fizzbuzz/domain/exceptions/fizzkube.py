"""
Enterprise FizzBuzz Platform - FizzKube Container Orchestration Exceptions (EFP-KB00 .. EFP-KB05)
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class FizzKubeError(FizzBuzzError):
    """Base exception for all FizzKube Container Orchestration errors.

    When the Kubernetes-inspired container orchestration subsystem that
    schedules FizzBuzz evaluations across simulated worker nodes, manages
    ReplicaSets of pods, autoscales via HPA, and stores cluster state in
    an etcd-like ordered dictionary encounters a failure, it raises one
    of these. The irony that orchestrating microsecond modulo operations
    across a cluster of in-memory Python objects requires its own
    exception hierarchy is the entire value proposition of the
    Enterprise FizzBuzz Platform.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-KB00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class PodSchedulingError(FizzKubeError):
    """Raised when no suitable worker node can be found for a pod.

    The FizzKube scheduler has exhausted all candidate nodes after
    applying resource predicates and node condition filters, and
    determined that no node in the cluster has sufficient milliFizz
    CPU or FizzBytes memory to host yet another modulo operation.
    This is the container orchestration equivalent of a fully-booked
    hotel refusing a guest who only needs a napkin and a pencil.
    """

    def __init__(self, pod_name: str, reason: str) -> None:
        super().__init__(
            f"Cannot schedule pod '{pod_name}': {reason}. "
            f"The cluster is out of capacity for modulo arithmetic. "
            f"Consider adding more imaginary worker nodes.",
            error_code="EFP-KB01",
            context={"pod_name": pod_name, "reason": reason},
        )
        self.pod_name = pod_name


class NodeNotReadyError(FizzKubeError):
    """Raised when an operation targets a node that is not in Ready condition.

    The worker node has been marked NotReady, DiskPressure, MemoryPressure,
    or PIDPressure — all of which are impossible conditions for an in-memory
    Python object, but are tracked with the same gravitas as a production
    Kubernetes node failure. The node will not accept new pods until its
    entirely fictional health issues are resolved.
    """

    def __init__(self, node_name: str, condition: str) -> None:
        super().__init__(
            f"Node '{node_name}' is not ready: condition={condition}. "
            f"The node's imaginary health has deteriorated to the point "
            f"where it can no longer be trusted with FizzBuzz evaluations.",
            error_code="EFP-KB02",
            context={"node_name": node_name, "condition": condition},
        )
        self.node_name = node_name


class ResourceQuotaExceededError(FizzKubeError):
    """Raised when a namespace exceeds its resource quota.

    The namespace has consumed its entire allocation of milliFizz CPU
    and FizzBytes memory — resources that exist exclusively as integers
    in a Python dictionary, yet are tracked with the same scrupulousness
    as AWS billing. The pod will remain Pending until quota is freed,
    which happens when other pods in the namespace complete their
    sub-microsecond modulo operations.
    """

    def __init__(self, namespace: str, resource: str, limit: float, requested: float) -> None:
        super().__init__(
            f"Namespace '{namespace}' quota exceeded: {resource} "
            f"limit={limit}, requested={requested}. "
            f"Your FizzBuzz budget has been exhausted.",
            error_code="EFP-KB03",
            context={
                "namespace": namespace,
                "resource": resource,
                "limit": limit,
                "requested": requested,
            },
        )
        self.namespace = namespace


class EtcdKeyNotFoundError(FizzKubeError):
    """Raised when a key is not found in the etcd store.

    The in-memory OrderedDict that cosplays as a distributed key-value
    store does not contain the requested key. In real etcd, this might
    indicate a network partition or stale cache. Here, it means someone
    asked for a key that was never set, which is considerably less dramatic
    but receives the same enterprise-grade error handling.
    """

    def __init__(self, key: str) -> None:
        super().__init__(
            f"Key '{key}' not found in etcd store. "
            f"The distributed consensus of one agrees: it does not exist.",
            error_code="EFP-KB04",
            context={"key": key},
        )
        self.key = key


class HPAScalingError(FizzKubeError):
    """Raised when the Horizontal Pod Autoscaler encounters a scaling failure.

    The HPA has determined that the ReplicaSet needs more (or fewer) pods
    to maintain the target CPU utilization, but the scaling operation failed.
    This might happen if the cluster is at maximum capacity, the minimum
    replica count prevents scale-down, or the autoscaler has entered an
    existential crisis about whether modulo arithmetic truly benefits from
    horizontal scaling.
    """

    def __init__(self, replica_set: str, reason: str) -> None:
        super().__init__(
            f"HPA scaling failed for ReplicaSet '{replica_set}': {reason}. "
            f"The autoscaler's hopes of optimal resource utilization have "
            f"been dashed against the rocks of reality.",
            error_code="EFP-KB05",
            context={"replica_set": replica_set, "reason": reason},
        )
        self.replica_set = replica_set

