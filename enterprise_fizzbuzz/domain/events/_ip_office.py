"""Intellectual Property Office events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("IP_TRADEMARK_REGISTERED")
EventType.register("IP_TRADEMARK_RENEWED")
EventType.register("IP_TRADEMARK_EXPIRED")
EventType.register("IP_TRADEMARK_SEARCH")
EventType.register("IP_PATENT_FILED")
EventType.register("IP_PATENT_GRANTED")
EventType.register("IP_PATENT_REJECTED")
EventType.register("IP_PATENT_PRIOR_ART_FOUND")
EventType.register("IP_COPYRIGHT_REGISTERED")
EventType.register("IP_LICENSE_GRANTED")
EventType.register("IP_LICENSE_REVOKED")
EventType.register("IP_DISPUTE_FILED")
EventType.register("IP_DISPUTE_RESOLVED")
EventType.register("IP_DASHBOARD_RENDERED")
