"""Formal Verification and Proof System events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("VERIFICATION_STARTED")
EventType.register("VERIFICATION_PROPERTY_CHECKED")
EventType.register("VERIFICATION_PROOF_CONSTRUCTED")
EventType.register("VERIFICATION_HOARE_TRIPLE_CHECKED")
EventType.register("VERIFICATION_COMPLETED")
EventType.register("VERIFICATION_DASHBOARD_RENDERED")
