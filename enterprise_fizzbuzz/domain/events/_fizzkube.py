"""FizzKube Container Orchestration events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("FIZZKUBE_POD_CREATED")
EventType.register("FIZZKUBE_POD_SCHEDULED")
EventType.register("FIZZKUBE_POD_RUNNING")
EventType.register("FIZZKUBE_POD_SUCCEEDED")
EventType.register("FIZZKUBE_POD_FAILED")
EventType.register("FIZZKUBE_NODE_ADDED")
EventType.register("FIZZKUBE_NODE_CONDITION_CHANGED")
EventType.register("FIZZKUBE_SCHEDULER_FILTER")
EventType.register("FIZZKUBE_SCHEDULER_SCORE")
EventType.register("FIZZKUBE_REPLICASET_RECONCILE")
EventType.register("FIZZKUBE_HPA_SCALE")
EventType.register("FIZZKUBE_HPA_DECISION")
EventType.register("FIZZKUBE_ETCD_PUT")
EventType.register("FIZZKUBE_ETCD_GET")
EventType.register("FIZZKUBE_DASHBOARD_RENDERED")
