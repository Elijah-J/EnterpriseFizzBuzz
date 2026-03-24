"""SLA Monitoring events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("SLA_EVALUATION_RECORDED")
EventType.register("SLA_SLO_CHECKED")
EventType.register("SLA_SLO_VIOLATION")
EventType.register("SLA_ALERT_FIRED")
EventType.register("SLA_ALERT_ACKNOWLEDGED")
EventType.register("SLA_ALERT_RESOLVED")
EventType.register("SLA_ERROR_BUDGET_UPDATED")
EventType.register("SLA_ERROR_BUDGET_EXHAUSTED")
