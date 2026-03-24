"""FinOps Cost Tracking and Chargeback Engine events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("FINOPS_COST_RECORDED")
EventType.register("FINOPS_TAX_APPLIED")
EventType.register("FINOPS_INVOICE_GENERATED")
EventType.register("FINOPS_BUDGET_WARNING")
EventType.register("FINOPS_BUDGET_EXCEEDED")
EventType.register("FINOPS_EXCHANGE_RATE_UPDATED")
EventType.register("FINOPS_SAVINGS_PLAN_COMPUTED")
EventType.register("FINOPS_DASHBOARD_RENDERED")
