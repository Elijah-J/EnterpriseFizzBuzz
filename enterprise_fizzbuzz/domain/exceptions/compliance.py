"""
Enterprise FizzBuzz Platform - Compliance & Regulatory Framework Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class ComplianceError(FizzBuzzError):
    """Base exception for all Compliance & Regulatory Framework errors.

    When the compliance framework itself encounters a failure, the
    irony is palpable: the system designed to enforce regulatory
    compliance has itself become non-compliant. Bob McFizzington's
    stress level increases by 5 points every time this exception
    is instantiated.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-C000",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class SOXSegregationViolationError(ComplianceError):
    """Raised when SOX segregation of duties is violated.

    Sarbanes-Oxley Section 404 requires that no single individual
    can perform incompatible duties. In the FizzBuzz context, this
    means the person who evaluates Fizz cannot also evaluate Buzz.
    If the same virtual personnel member is assigned to both roles,
    the entire evaluation is compromised, and the SEC will be
    notified (they won't care, but we'll notify them anyway).
    """

    def __init__(self, personnel: str, role_a: str, role_b: str) -> None:
        super().__init__(
            f"SOX Segregation of Duties violation: '{personnel}' cannot "
            f"hold both '{role_a}' and '{role_b}' roles simultaneously. "
            f"This is the FizzBuzz equivalent of being both auditor and "
            f"auditee, which is frowned upon by the SEC and common sense alike.",
            error_code="EFP-C100",
            context={
                "personnel": personnel,
                "role_a": role_a,
                "role_b": role_b,
            },
        )
        self.personnel = personnel
        self.role_a = role_a
        self.role_b = role_b


class GDPRErasureParadoxError(ComplianceError):
    """Raised when GDPR right-to-erasure conflicts with immutable data stores.

    THIS IS THE COMPLIANCE PARADOX.

    The data subject has exercised their Article 17 right to erasure.
    However, the data exists in:
      1. An append-only event store (deleting events would violate
         event sourcing's fundamental guarantee of immutability)
      2. An immutable blockchain (deleting blocks would invalidate
         the entire chain's cryptographic integrity)

    Complying with GDPR requires deleting the data.
    Complying with the architecture requires keeping the data.
    Both are non-negotiable.

    The compliance framework has reached a logical paradox from which
    there is no escape. Bob McFizzington has been notified. His stress
    level is now clinically significant.
    """

    def __init__(self, data_subject: int, conflicting_stores: Optional[list[str]] = None) -> None:
        stores = conflicting_stores or ["append-only event store", "immutable blockchain"]
        super().__init__(
            f"GDPR ERASURE PARADOX for data subject {data_subject}: "
            f"Cannot erase from {', '.join(stores)} without violating "
            f"their immutability guarantees. The right to be forgotten "
            f"has collided with the inability to forget. This is fine.",
            error_code="EFP-C200",
            context={
                "data_subject": data_subject,
                "conflicting_stores": stores,
            },
        )
        self.data_subject = data_subject
        self.conflicting_stores = stores


class GDPRConsentRequiredError(ComplianceError):
    """Raised when a FizzBuzz evaluation is attempted without GDPR consent.

    Under GDPR Article 6, all processing of personal data requires a
    lawful basis. Since every number is potentially a natural person's
    age, shoe size, or lucky number, FizzBuzz evaluation constitutes
    personal data processing and requires explicit consent.

    Consent must be freely given, specific, informed, and unambiguous.
    Clicking "I agree" on a 47-page Terms of Service document counts.
    """

    def __init__(self, data_subject: int) -> None:
        super().__init__(
            f"GDPR consent not obtained for data subject {data_subject}. "
            f"FizzBuzz evaluation constitutes personal data processing "
            f"under Article 6 of the GDPR. Please obtain explicit, "
            f"informed, freely-given consent before evaluating this number.",
            error_code="EFP-C201",
            context={"data_subject": data_subject},
        )
        self.data_subject = data_subject


class HIPAAPrivacyViolationError(ComplianceError):
    """Raised when a HIPAA privacy rule is violated during FizzBuzz evaluation.

    The HIPAA Privacy Rule (45 CFR Part 164) establishes national
    standards for the protection of individually identifiable health
    information. FizzBuzz results — particularly "Fizz" and "Buzz" —
    could theoretically be part of a patient's medical record if,
    for example, a healthcare provider used FizzBuzz to determine
    medication dosages (please do not do this).
    """

    def __init__(self, violation_type: str, details: str) -> None:
        super().__init__(
            f"HIPAA Privacy Rule violation ({violation_type}): {details}. "
            f"Protected Health Information may have been exposed. "
            f"Please file an incident report with the Privacy Officer.",
            error_code="EFP-C300",
            context={"violation_type": violation_type, "details": details},
        )
        self.violation_type = violation_type


class HIPAAMinimumNecessaryError(ComplianceError):
    """Raised when the HIPAA Minimum Necessary Rule is violated.

    The Minimum Necessary Rule requires that access to PHI be limited
    to the minimum amount necessary to accomplish the intended purpose.
    If you requested FULL_ACCESS when OPERATIONS level would suffice,
    you are in violation. The HIPAA police have been notified.
    """

    def __init__(self, requested_level: str, permitted_level: str) -> None:
        super().__init__(
            f"HIPAA Minimum Necessary violation: requested '{requested_level}' "
            f"access but only '{permitted_level}' is permitted for this "
            f"operation. FizzBuzz results contain Protected Health "
            f"Information that must be accessed on a need-to-know basis.",
            error_code="EFP-C301",
            context={
                "requested_level": requested_level,
                "permitted_level": permitted_level,
            },
        )
        self.requested_level = requested_level
        self.permitted_level = permitted_level


class ComplianceFrameworkNotEnabledError(ComplianceError):
    """Raised when compliance operations are attempted without enabling the framework.

    The compliance framework is opt-in because mandatory compliance
    for a FizzBuzz application would be... well, it would actually
    be very on-brand for this project, but we drew the line somewhere.
    """

    def __init__(self) -> None:
        super().__init__(
            "Compliance framework is not enabled. Use --compliance to enable "
            "SOX, GDPR, and HIPAA compliance for your FizzBuzz evaluations. "
            "Because modulo arithmetic without regulatory oversight is "
            "basically the Wild West.",
            error_code="EFP-C400",
        )


class ComplianceOfficerUnavailableError(ComplianceError):
    """Raised when the Chief Compliance Officer is unavailable.

    Bob McFizzington, the sole compliance officer for the entire
    Enterprise FizzBuzz Platform, is currently unavailable. This is
    his permanent state. His availability field in the configuration
    is set to 'false' and has never been 'true'. He is simultaneously
    always on-call and never available. He is Schrödinger's compliance
    officer.
    """

    def __init__(self, officer_name: str, stress_level: float) -> None:
        super().__init__(
            f"Chief Compliance Officer '{officer_name}' is unavailable "
            f"(current stress level: {stress_level:.1f}%). "
            f"All compliance decisions have been deferred to the next "
            f"quarterly review, which has been rescheduled indefinitely.",
            error_code="EFP-C401",
            context={
                "officer_name": officer_name,
                "stress_level": stress_level,
            },
        )
        self.officer_name = officer_name
        self.stress_level = stress_level

