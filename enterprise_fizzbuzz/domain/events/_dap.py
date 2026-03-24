"""FizzDAP Debug Adapter Protocol events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("DAP_SESSION_INITIALIZED")
EventType.register("DAP_BREAKPOINT_SET")
EventType.register("DAP_BREAKPOINT_HIT")
EventType.register("DAP_EXECUTION_STOPPED")
EventType.register("DAP_EXECUTION_CONTINUED")
EventType.register("DAP_EXECUTION_TERMINATED")
EventType.register("DAP_STACK_TRACE_REQUESTED")
EventType.register("DAP_VARIABLES_INSPECTED")
EventType.register("DAP_EXPRESSION_EVALUATED")
EventType.register("DAP_DASHBOARD_RENDERED")
