"""Compliance and Regulatory Framework events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("COMPLIANCE_CHECK_STARTED")
EventType.register("COMPLIANCE_CHECK_PASSED")
EventType.register("COMPLIANCE_CHECK_FAILED")
EventType.register("COMPLIANCE_VIOLATION_DETECTED")
EventType.register("COMPLIANCE_DATA_CLASSIFIED")
EventType.register("SOX_SEGREGATION_ENFORCED")
EventType.register("SOX_SEGREGATION_VIOLATION")
EventType.register("SOX_AUDIT_TRAIL_RECORDED")
EventType.register("GDPR_CONSENT_REQUESTED")
EventType.register("GDPR_CONSENT_GRANTED")
EventType.register("GDPR_CONSENT_DENIED")
EventType.register("GDPR_ERASURE_REQUESTED")
EventType.register("GDPR_ERASURE_PARADOX_DETECTED")
EventType.register("GDPR_ERASURE_CERTIFICATE_ISSUED")
EventType.register("HIPAA_PHI_DETECTED")
EventType.register("HIPAA_PHI_ENCRYPTED")
EventType.register("HIPAA_MINIMUM_NECESSARY_APPLIED")
EventType.register("COMPLIANCE_DASHBOARD_RENDERED")
