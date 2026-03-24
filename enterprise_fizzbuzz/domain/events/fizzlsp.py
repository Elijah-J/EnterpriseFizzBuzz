"""FizzLSP Language Server Protocol events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("LSP_SERVER_INITIALIZED")
EventType.register("LSP_SERVER_SHUTDOWN")
EventType.register("LSP_DOCUMENT_OPENED")
EventType.register("LSP_DOCUMENT_CHANGED")
EventType.register("LSP_DOCUMENT_CLOSED")
EventType.register("LSP_DIAGNOSTICS_PUBLISHED")
EventType.register("LSP_COMPLETION_SERVED")
EventType.register("LSP_DEFINITION_RESOLVED")
EventType.register("LSP_HOVER_SERVED")
EventType.register("LSP_RENAME_PERFORMED")
EventType.register("LSP_DASHBOARD_RENDERED")
