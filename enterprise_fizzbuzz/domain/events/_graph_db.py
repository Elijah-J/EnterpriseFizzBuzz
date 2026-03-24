"""Graph Database events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("GRAPH_NODE_CREATED")
EventType.register("GRAPH_EDGE_CREATED")
EventType.register("GRAPH_POPULATED")
EventType.register("GRAPH_QUERY_EXECUTED")
EventType.register("GRAPH_ANALYSIS_STARTED")
EventType.register("GRAPH_ANALYSIS_COMPLETED")
EventType.register("GRAPH_COMMUNITY_DETECTED")
EventType.register("GRAPH_DASHBOARD_RENDERED")
