"""Compliance Chatbot events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("CHATBOT_QUERY_RECEIVED")
EventType.register("CHATBOT_INTENT_CLASSIFIED")
EventType.register("CHATBOT_RESPONSE_GENERATED")
EventType.register("CHATBOT_SESSION_STARTED")
