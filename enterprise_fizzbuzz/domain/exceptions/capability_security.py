"""
Enterprise FizzBuzz Platform - FizzCap — Capability-Based Security Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class CapabilitySecurityError(FizzBuzzError):
    """Base exception for all capability-based security failures.

    Raised when the FizzCap security model encounters a violation of
    its core invariants. All capability exceptions inherit from this
    class, forming a sub-hierarchy that mirrors the layered nature of
    the capability model itself: mint → attenuation → delegation →
    verification → confused deputy prevention.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-CAP00"),
            context=kwargs.pop("context", {}),
        )


class CapabilityVerificationError(CapabilitySecurityError):
    """Raised when a capability token fails verification.

    A capability has been presented that either has an invalid HMAC-SHA256
    signature, has been revoked, grants access to the wrong resource, or
    lacks the required operation. The confused deputy guard has done its
    job: it checked the REQUEST's capability, not the caller's ambient
    authority, and found it wanting.

    This is the security equivalent of presenting an expired coupon at
    a grocery store, except the coupon is for FizzBuzz evaluation rights
    and the grocery store is a mission-critical enterprise platform.
    """

    def __init__(self, cap_id: str, reason: str) -> None:
        super().__init__(
            f"Capability '{cap_id}' failed verification: {reason}",
            error_code="EFP-CAP01",
            context={"cap_id": cap_id, "reason": reason},
        )
        self.cap_id = cap_id
        self.reason = reason


class CapabilityAmplificationError(CapabilitySecurityError):
    """Raised when an attenuation attempt would broaden authority.

    The Second Law of Capability Thermodynamics has been violated:
    someone attempted to derive a capability with MORE authority than
    its parent. This is the capability equivalent of trying to withdraw
    more money than your account balance — except instead of money,
    it's the right to evaluate whether 15 is FizzBuzz.

    Attenuation is monotonic: authority can only DECREASE through
    delegation. Adding operations not present in the parent, or removing
    constraints that the parent enforces, constitutes amplification and
    is categorically forbidden.
    """

    def __init__(self, parent_cap_id: str, reason: str) -> None:
        super().__init__(
            f"Cannot amplify capability '{parent_cap_id}': {reason}",
            error_code="EFP-CAP02",
            context={"parent_cap_id": parent_cap_id, "reason": reason},
        )
        self.parent_cap_id = parent_cap_id
        self.reason = reason


class CapabilityRevocationError(CapabilitySecurityError):
    """Raised when a capability revocation operation fails.

    A cascade revocation through the delegation graph has encountered
    an inconsistency — perhaps a circular delegation (which should be
    impossible in a DAG, but enterprise software finds a way), or
    a node that cannot be located in the graph.

    When the revocation system itself fails, the security posture of
    the entire FizzBuzz platform is compromised. This is the capability
    equivalent of the fire alarm catching fire.
    """

    def __init__(self, cap_id: str, reason: str) -> None:
        super().__init__(
            f"Failed to revoke capability '{cap_id}': {reason}",
            error_code="EFP-CAP03",
            context={"cap_id": cap_id, "reason": reason},
        )
        self.cap_id = cap_id
        self.reason = reason

