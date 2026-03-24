"""Federated Learning events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("FEDERATION_ROUND_STARTED")
EventType.register("FEDERATION_ROUND_COMPLETED")
EventType.register("FEDERATION_CLIENT_TRAINED")
EventType.register("FEDERATION_WEIGHTS_AGGREGATED")
EventType.register("FEDERATION_PRIVACY_BUDGET_UPDATED")
EventType.register("FEDERATION_CONVERGENCE_ACHIEVED")
EventType.register("FEDERATION_DASHBOARD_RENDERED")
