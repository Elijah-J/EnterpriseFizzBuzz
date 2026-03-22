"""
Enterprise FizzBuzz Platform - Compliance & Regulatory Framework

Implements SOX (Sarbanes-Oxley), GDPR (General Data Protection Regulation),
and HIPAA (Health Insurance Portability and Accountability Act) compliance
for the Enterprise FizzBuzz Platform.

Because the only thing standing between your FizzBuzz output and a
regulatory enforcement action is this module. Features include:

- SOX Segregation of Duties: No single virtual employee can both evaluate
  Fizz AND evaluate Buzz. That would be a conflict of interest.
- GDPR Consent & Right-to-Erasure: Every number is a data subject. Every
  FizzBuzz result is personally identifiable information. THE COMPLIANCE
  PARADOX occurs when erasure requests hit the append-only event store
  and immutable blockchain.
- HIPAA Minimum Necessary Rule: FizzBuzz results are Protected Health
  Information. Access is restricted. "Encryption" is base64. It's
  military-grade RFC 4648 encoding.
- Bob McFizzington: Chief Compliance Officer. Stress level: 94.7% and
  rising. Availability: never. Certifications: many. Usefulness: debatable.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    ComplianceError,
    ComplianceFrameworkNotEnabledError,
    ComplianceOfficerUnavailableError,
    GDPRConsentRequiredError,
    GDPRErasureParadoxError,
    HIPAAMinimumNecessaryError,
    HIPAAPrivacyViolationError,
    SOXSegregationViolationError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    ComplianceCheckResult,
    ComplianceRegime,
    ComplianceVerdict,
    DataClassificationLevel,
    DataDeletionCertificate,
    Event,
    EventType,
    FizzBuzzResult,
    GDPRErasureStatus,
    HIPAAMinimumNecessaryLevel,
    ProcessingContext,
)

logger = logging.getLogger(__name__)


# ================================================================
# Data Classification Engine
# ================================================================


class DataClassificationEngine:
    """Classifies FizzBuzz results by data sensitivity level.

    Every piece of FizzBuzz output must be classified according to its
    sensitivity before it can be processed, stored, transmitted, or
    even thought about too hard. Plain numbers are PUBLIC, individual
    Fizz or Buzz results are INTERNAL, FizzBuzz results are CONFIDENTIAL
    (trade secrets!), and anything involving ML confidence below 0.9 is
    SECRET because uncertainty is classified.

    TOP_SECRET_FIZZBUZZ is reserved for results verified by multiple
    independent evaluation strategies. If you're reading this, you
    probably don't have clearance.
    """

    # Classification rules: output pattern -> classification level
    _CLASSIFICATION_MAP = {
        "FizzBuzz": DataClassificationLevel.CONFIDENTIAL,
        "Fizz": DataClassificationLevel.INTERNAL,
        "Buzz": DataClassificationLevel.INTERNAL,
    }

    def __init__(self, event_bus: Any = None) -> None:
        self._event_bus = event_bus
        self._classification_count = 0
        self._classifications: dict[DataClassificationLevel, int] = {
            level: 0 for level in DataClassificationLevel
        }

    def classify(self, result: FizzBuzzResult) -> DataClassificationLevel:
        """Classify a FizzBuzz result by its data sensitivity level.

        The classification algorithm considers:
        1. The output string (Fizz, Buzz, FizzBuzz, or plain number)
        2. ML confidence metadata (if present)
        3. Whether multiple strategies verified the result
        4. The phase of the moon (just kidding, but we considered it)

        Args:
            result: The FizzBuzz result to classify.

        Returns:
            The appropriate DataClassificationLevel.
        """
        self._classification_count += 1

        # Check for multi-strategy verification (TOP_SECRET_FIZZBUZZ)
        strategies_used = result.metadata.get("strategies_verified", 0)
        if strategies_used >= 2 and result.output == "FizzBuzz":
            level = DataClassificationLevel.TOP_SECRET_FIZZBUZZ
            self._classifications[level] += 1
            self._emit_event(result, level)
            return level

        # Check for low ML confidence (SECRET)
        ml_confidence = result.metadata.get("ml_confidence", None)
        if ml_confidence is not None and ml_confidence < 0.9:
            level = DataClassificationLevel.SECRET
            self._classifications[level] += 1
            self._emit_event(result, level)
            return level

        # Standard classification based on output
        level = self._CLASSIFICATION_MAP.get(
            result.output,
            DataClassificationLevel.PUBLIC,
        )
        self._classifications[level] += 1
        self._emit_event(result, level)
        return level

    def _emit_event(self, result: FizzBuzzResult, level: DataClassificationLevel) -> None:
        """Emit a classification event to the event bus."""
        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=EventType.COMPLIANCE_DATA_CLASSIFIED,
                payload={
                    "number": result.number,
                    "output": result.output,
                    "classification": level.name,
                },
                source="DataClassificationEngine",
            ))

    def get_statistics(self) -> dict[str, Any]:
        """Return classification statistics."""
        return {
            "total_classified": self._classification_count,
            "by_level": {
                level.name: count
                for level, count in self._classifications.items()
            },
        }


# ================================================================
# SOX Auditor — Segregation of Duties
# ================================================================


@dataclass
class PersonnelAssignment:
    """A virtual personnel assignment for SOX segregation of duties.

    Attributes:
        name: The employee's name.
        title: Their impressively long job title.
        clearance: Their security clearance level.
        assigned_role: The role they've been assigned for this evaluation.
    """

    name: str
    title: str
    clearance: str
    assigned_role: str = ""


class SOXAuditor:
    """Sarbanes-Oxley compliance auditor for FizzBuzz operations.

    Implements Section 404 internal controls by enforcing segregation
    of duties across the FizzBuzz evaluation pipeline. Specifically:

    - The person who evaluates Fizz (divisibility by 3) MUST NOT be
      the same person who evaluates Buzz (divisibility by 5).
    - The person who formats the output MUST NOT be the person who
      evaluated any of the rules.
    - The person who audits the result MUST NOT be any of the above.

    This is achieved by maintaining a virtual personnel roster and
    assigning roles from it using a deterministic hash-based algorithm.
    The roster ships with 5 virtual employees, each with their own
    security clearance and impressively meaningless job title.

    All assignments are logged to an audit trail that must be retained
    for 7 years (2,555 days) as required by SOX Section 802, even though
    the application typically runs for less than 7 seconds.
    """

    # SOX roles that must be segregated
    ROLES = ["FIZZ_EVALUATOR", "BUZZ_EVALUATOR", "FORMATTER", "AUDITOR"]

    def __init__(
        self,
        personnel_roster: list[dict[str, str]],
        strict_mode: bool = True,
        event_bus: Any = None,
    ) -> None:
        self._roster = [
            PersonnelAssignment(
                name=p.get("name", "Unknown"),
                title=p.get("title", "Untitled"),
                clearance=p.get("clearance", "NONE"),
            )
            for p in personnel_roster
        ]
        self._strict_mode = strict_mode
        self._event_bus = event_bus
        self._audit_trail: list[dict[str, Any]] = []
        self._violations: list[str] = []
        self._assignments_made = 0

    def assign_duties(self, number: int) -> dict[str, PersonnelAssignment]:
        """Assign segregated duties for a FizzBuzz evaluation.

        Uses a deterministic hash-based algorithm to assign personnel
        to roles, ensuring that no person holds incompatible roles.
        The algorithm is deterministic so that audit trails are
        reproducible — because reproducibility in personnel assignment
        for modulo arithmetic is apparently important.

        Args:
            number: The number being evaluated (used as hash seed).

        Returns:
            A dict mapping role names to PersonnelAssignment objects.

        Raises:
            SOXSegregationViolationError: If strict mode is on and
                segregation cannot be achieved (roster too small).
        """
        if len(self._roster) < len(self.ROLES):
            if self._strict_mode:
                raise SOXSegregationViolationError(
                    "ROSTER",
                    "ALL",
                    "ALL — insufficient personnel for segregation "
                    f"(need {len(self.ROLES)}, have {len(self._roster)})",
                )
            # Non-strict: allow overlap with a warning
            logger.warning(
                "SOX: Personnel roster too small for full segregation. "
                "Some duties will be shared. The SEC frowns upon this."
            )

        assignments: dict[str, PersonnelAssignment] = {}
        used_indices: set[int] = set()

        for i, role in enumerate(self.ROLES):
            # Deterministic assignment based on number + role index
            hash_input = f"{number}:{role}:{i}".encode()
            hash_val = int(hashlib.sha256(hash_input).hexdigest(), 16)

            # Find an unused personnel member
            roster_size = len(self._roster)
            start_idx = hash_val % roster_size
            assigned_idx = start_idx

            attempts = 0
            while assigned_idx in used_indices and attempts < roster_size:
                assigned_idx = (assigned_idx + 1) % roster_size
                attempts += 1

            if assigned_idx in used_indices:
                # All personnel used — check strict mode
                if self._strict_mode:
                    existing_role = next(
                        (r for r, a in assignments.items()
                         if self._roster.index(a) == assigned_idx),
                        "UNKNOWN",
                    )
                    raise SOXSegregationViolationError(
                        self._roster[assigned_idx].name,
                        existing_role,
                        role,
                    )
                # Non-strict: reuse with warning
                assigned_idx = start_idx

            person = PersonnelAssignment(
                name=self._roster[assigned_idx].name,
                title=self._roster[assigned_idx].title,
                clearance=self._roster[assigned_idx].clearance,
                assigned_role=role,
            )
            assignments[role] = person
            used_indices.add(assigned_idx)

        self._assignments_made += 1

        # Record to audit trail
        trail_entry = {
            "number": number,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "assignments": {
                role: {
                    "name": person.name,
                    "title": person.title,
                    "clearance": person.clearance,
                }
                for role, person in assignments.items()
            },
            "segregation_satisfied": self._verify_segregation(assignments),
        }
        self._audit_trail.append(trail_entry)

        # Emit event
        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=EventType.SOX_SEGREGATION_ENFORCED,
                payload=trail_entry,
                source="SOXAuditor",
            ))

        return assignments

    def _verify_segregation(self, assignments: dict[str, PersonnelAssignment]) -> bool:
        """Verify that all assignments satisfy segregation of duties.

        Returns True if no person holds multiple roles, False otherwise.
        """
        names = [a.name for a in assignments.values()]
        unique_names = set(names)
        is_segregated = len(names) == len(unique_names)

        if not is_segregated:
            # Find the violating pairs
            from collections import Counter
            counts = Counter(names)
            for name, count in counts.items():
                if count > 1:
                    roles = [r for r, a in assignments.items() if a.name == name]
                    violation = (
                        f"SOX VIOLATION: {name} holds {count} roles: "
                        f"{', '.join(roles)}"
                    )
                    self._violations.append(violation)
                    logger.warning(violation)

                    if self._event_bus is not None:
                        self._event_bus.publish(Event(
                            event_type=EventType.SOX_SEGREGATION_VIOLATION,
                            payload={
                                "personnel": name,
                                "roles": roles,
                            },
                            source="SOXAuditor",
                        ))

        return is_segregated

    def get_audit_trail(self) -> list[dict[str, Any]]:
        """Return the complete SOX audit trail."""
        return list(self._audit_trail)

    def get_violations(self) -> list[str]:
        """Return all detected segregation violations."""
        return list(self._violations)

    @property
    def assignments_made(self) -> int:
        """Total number of duty assignments made."""
        return self._assignments_made

    @property
    def violation_count(self) -> int:
        """Total number of segregation violations detected."""
        return len(self._violations)


# ================================================================
# GDPR Controller — Consent Management & Right-to-Erasure
# ================================================================


class GDPRController:
    """GDPR compliance controller for FizzBuzz operations.

    Manages consent for FizzBuzz evaluation (because every number is a
    data subject) and handles right-to-erasure requests. The erasure
    functionality is where THE COMPLIANCE PARADOX lives:

    THE COMPLIANCE PARADOX:
    ========================
    When a data subject (number) exercises their Article 17 right to
    erasure, the system must delete all their data. However:

    1. The Event Store is append-only. Deleting events would violate
       the fundamental guarantee of event sourcing: that the event
       stream is an immutable, ordered log of everything that happened.
       You can't un-happen a FizzBuzz evaluation.

    2. The Blockchain is immutable. Deleting a block would invalidate
       the cryptographic hash chain, making every subsequent block's
       previous_hash incorrect. The integrity of the entire FizzBuzz
       audit ledger would collapse.

    3. The Compliance Audit Trail itself now contains records of the
       data that was supposed to be deleted, because SOX requires
       retaining audit trails for 7 years.

    4. This very erasure certificate documents what was erased, thereby
       partially un-erasing it.

    The result: GDPR says delete. Architecture says can't. SOX says
    keep. The erasure certificate says "here's what we deleted" while
    simultaneously containing the deleted information. Bob McFizzington's
    stress level increases. The universe does not divide by zero, but
    it gets uncomfortably close.
    """

    def __init__(
        self,
        auto_consent: bool = True,
        erasure_enabled: bool = True,
        event_bus: Any = None,
    ) -> None:
        self._auto_consent = auto_consent
        self._erasure_enabled = erasure_enabled
        self._event_bus = event_bus
        self._consent_registry: dict[int, dict[str, Any]] = {}
        self._erasure_requests: list[DataDeletionCertificate] = []
        self._paradox_count = 0
        self._consent_count = 0
        self._denial_count = 0

    def request_consent(self, number: int) -> bool:
        """Request consent to process a number under GDPR.

        Under GDPR Article 6, all processing of personal data requires
        a lawful basis. Since we've decided that numbers are personal
        data (they could be someone's age!), we need consent.

        If auto_consent is True (the default), consent is automatically
        granted because asking each number individually would make
        FizzBuzz unacceptably slow, and we have SLOs to meet.

        Args:
            number: The data subject (number) to request consent from.

        Returns:
            True if consent was granted, False otherwise.
        """
        if self._auto_consent:
            self._consent_registry[number] = {
                "granted": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "basis": "legitimate_interest_in_modulo_arithmetic",
                "method": "auto_consent",
            }
            self._consent_count += 1

            if self._event_bus is not None:
                self._event_bus.publish(Event(
                    event_type=EventType.GDPR_CONSENT_GRANTED,
                    payload={
                        "data_subject": number,
                        "method": "auto_consent",
                        "basis": "legitimate_interest_in_modulo_arithmetic",
                    },
                    source="GDPRController",
                ))
            return True

        # Manual consent mode — deny by default (the safe option)
        self._denial_count += 1
        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=EventType.GDPR_CONSENT_DENIED,
                payload={"data_subject": number, "reason": "manual_consent_required"},
                source="GDPRController",
            ))
        return False

    def has_consent(self, number: int) -> bool:
        """Check if consent has been granted for a number."""
        entry = self._consent_registry.get(number)
        return entry is not None and entry.get("granted", False)

    def request_erasure(self, number: int) -> DataDeletionCertificate:
        """Process a GDPR right-to-erasure request.

        THIS IS WHERE THE COMPLIANCE PARADOX HAPPENS.

        The data subject (number) has exercised their Article 17 right
        to be forgotten. We will now attempt to erase their data from
        all stores, discover that most stores are immutable, issue a
        certificate documenting our failure, and increase Bob's stress
        level. It's a beautiful, tragic, utterly predictable process.

        Args:
            number: The data subject requesting erasure.

        Returns:
            A DataDeletionCertificate documenting the attempt.

        Raises:
            GDPRErasureParadoxError: Always. That's the joke.
        """
        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=EventType.GDPR_ERASURE_REQUESTED,
                payload={"data_subject": number},
                source="GDPRController",
            ))

        # Step 1: Identify all data stores
        stores_checked = [
            "In-Memory Processing Context",
            "FizzBuzz Result Cache",
            "Append-Only Event Store",
            "Immutable Blockchain Audit Ledger",
            "SOX Compliance Audit Trail",
            "HIPAA PHI Access Log",
            "This Very Erasure Request Log",
        ]

        # Step 2: Attempt erasure from each store
        stores_erased = [
            "In-Memory Processing Context",
            "FizzBuzz Result Cache",
        ]

        stores_refused = [
            "Append-Only Event Store (REFUSED: immutability guarantee)",
            "Immutable Blockchain Audit Ledger (REFUSED: hash chain integrity)",
            "SOX Compliance Audit Trail (REFUSED: 7-year retention requirement)",
            "HIPAA PHI Access Log (REFUSED: regulatory retention mandate)",
            "This Very Erasure Request Log (REFUSED: recursive paradox)",
        ]

        # Step 3: THE COMPLIANCE PARADOX
        self._paradox_count += 1

        paradox_explanation = (
            f"COMPLIANCE PARADOX DETECTED for data subject {number}.\n"
            f"\n"
            f"The following irreconcilable conflicts have been identified:\n"
            f"\n"
            f"  1. GDPR Article 17 REQUIRES erasure of all personal data.\n"
            f"  2. The Append-Only Event Store CANNOT delete events without\n"
            f"     violating its fundamental immutability guarantee. Events\n"
            f"     are facts. You cannot un-fact a fact.\n"
            f"  3. The Immutable Blockchain CANNOT remove blocks without\n"
            f"     invalidating the cryptographic hash chain. Each block's\n"
            f"     hash depends on the previous block. Remove one, and the\n"
            f"     entire chain collapses like a house of SHA-256 cards.\n"
            f"  4. SOX Section 802 REQUIRES retention of audit trails for\n"
            f"     7 years (2,555 days). Deleting them would be a federal\n"
            f"     offense. Not deleting them violates GDPR.\n"
            f"  5. HIPAA retention rules REQUIRE maintaining PHI access\n"
            f"     logs for 6 years.\n"
            f"  6. This erasure certificate itself contains enough metadata\n"
            f"     to identify what was erased, thereby partially un-erasing\n"
            f"     it. The certificate is its own paradox.\n"
            f"\n"
            f"Resolution: NONE. The paradox is irreconcilable. A formal\n"
            f"exception has been filed with the International Court of\n"
            f"FizzBuzz Data Protection. Estimated resolution: heat death\n"
            f"of the universe, plus or minus a few billion years.\n"
            f"\n"
            f"Bob McFizzington's stress level has been updated accordingly."
        )

        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=EventType.GDPR_ERASURE_PARADOX_DETECTED,
                payload={
                    "data_subject": number,
                    "stores_refused": stores_refused,
                    "paradox_count": self._paradox_count,
                    "explanation": "Cannot comply with erasure without violating immutability guarantees",
                },
                source="GDPRController",
            ))

        # Step 4: Issue the certificate (the irony is not lost on us)
        certificate = DataDeletionCertificate(
            data_subject=number,
            status=GDPRErasureStatus.PARADOX_ENCOUNTERED,
            stores_checked=tuple(stores_checked),
            stores_erased=tuple(stores_erased),
            stores_refused=tuple(stores_refused),
            paradox_explanation=paradox_explanation,
        )

        self._erasure_requests.append(certificate)

        # Remove consent (at least we can do that)
        if number in self._consent_registry:
            del self._consent_registry[number]

        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=EventType.GDPR_ERASURE_CERTIFICATE_ISSUED,
                payload={
                    "certificate_id": certificate.certificate_id,
                    "data_subject": number,
                    "status": certificate.status.name,
                },
                source="GDPRController",
            ))

        return certificate

    def get_erasure_certificates(self) -> list[DataDeletionCertificate]:
        """Return all issued erasure certificates."""
        return list(self._erasure_requests)

    @property
    def paradox_count(self) -> int:
        """Total number of compliance paradoxes encountered."""
        return self._paradox_count

    @property
    def consent_count(self) -> int:
        """Total number of consents granted."""
        return self._consent_count

    @property
    def denial_count(self) -> int:
        """Total number of consents denied."""
        return self._denial_count

    def get_statistics(self) -> dict[str, Any]:
        """Return GDPR statistics."""
        return {
            "consents_granted": self._consent_count,
            "consents_denied": self._denial_count,
            "erasure_requests": len(self._erasure_requests),
            "paradoxes_encountered": self._paradox_count,
            "active_consents": sum(
                1 for c in self._consent_registry.values()
                if c.get("granted", False)
            ),
        }


# ================================================================
# HIPAA Guard — Minimum Necessary Rule & "Encryption"
# ================================================================


class HIPAAGuard:
    """HIPAA compliance guard for FizzBuzz operations.

    Implements two key HIPAA requirements:

    1. **Minimum Necessary Rule**: Access to Protected Health Information
       (PHI) — which FizzBuzz results absolutely are, if you squint —
       must be limited to the minimum amount necessary to accomplish
       the intended purpose. If you only need aggregate stats, you
       don't get to see individual FizzBuzz results.

    2. **"Encryption"**: HIPAA requires encryption of PHI at rest and
       in transit. This module implements military-grade RFC 4648
       encoding, more commonly known as base64. It provides the same
       level of security as ROT13 applied twice, which is to say,
       none whatsoever. But it looks encrypted, and in compliance
       theatre, appearance is everything.
    """

    def __init__(
        self,
        minimum_necessary_level: str = "OPERATIONS",
        encryption_algorithm: str = "military_grade_base64",
        event_bus: Any = None,
    ) -> None:
        level_map = {
            "FULL_ACCESS": HIPAAMinimumNecessaryLevel.FULL_ACCESS,
            "TREATMENT": HIPAAMinimumNecessaryLevel.TREATMENT,
            "OPERATIONS": HIPAAMinimumNecessaryLevel.OPERATIONS,
            "RESEARCH": HIPAAMinimumNecessaryLevel.RESEARCH,
        }
        self._default_level = level_map.get(
            minimum_necessary_level.upper(),
            HIPAAMinimumNecessaryLevel.OPERATIONS,
        )
        self._encryption_algorithm = encryption_algorithm
        self._event_bus = event_bus
        self._phi_access_log: list[dict[str, Any]] = []
        self._encryption_count = 0
        self._redaction_count = 0

    def encrypt_phi(self, data: str) -> str:
        """Encrypt Protected Health Information using military-grade base64.

        This is not real encryption. base64 is an encoding, not an
        encryption algorithm. It provides zero confidentiality guarantees.
        A determined adversary (or anyone with a terminal) can decode it
        instantly. But HIPAA says "encrypt," and base64 technically
        transforms the data into an unreadable format, which is close
        enough for compliance theatre.

        The algorithm is logged as "military-grade RFC 4648 encoding"
        because "we base64'd it" doesn't inspire confidence in auditors.

        Args:
            data: The PHI to "encrypt".

        Returns:
            The base64-encoded data, prefixed with a marker.
        """
        self._encryption_count += 1

        encoded = base64.b64encode(data.encode("utf-8")).decode("utf-8")
        result = f"[HIPAA-ENCRYPTED:{self._encryption_algorithm}]{encoded}"

        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=EventType.HIPAA_PHI_ENCRYPTED,
                payload={
                    "algorithm": self._encryption_algorithm,
                    "algorithm_description": "Military-grade RFC 4648 encoding",
                    "original_length": len(data),
                    "encrypted_length": len(result),
                    "security_level": "Maximum (in theory)",
                    "actual_security_level": "None (in practice)",
                },
                source="HIPAAGuard",
            ))

        logger.debug(
            "PHI encrypted using military-grade RFC 4648 encoding. "
            "Data is now approximately 33%% larger and 0%% more secure."
        )

        return result

    def decrypt_phi(self, encrypted: str) -> str:
        """Decrypt PHI that was "encrypted" with military-grade base64.

        Args:
            encrypted: The "encrypted" data string.

        Returns:
            The original data.
        """
        prefix = f"[HIPAA-ENCRYPTED:{self._encryption_algorithm}]"
        if encrypted.startswith(prefix):
            encoded = encrypted[len(prefix):]
        else:
            encoded = encrypted

        return base64.b64decode(encoded.encode("utf-8")).decode("utf-8")

    def apply_minimum_necessary(
        self,
        result: FizzBuzzResult,
        access_level: Optional[HIPAAMinimumNecessaryLevel] = None,
    ) -> dict[str, Any]:
        """Apply the HIPAA Minimum Necessary Rule to a FizzBuzz result.

        Redacts fields based on the access level:
        - FULL_ACCESS: Everything visible. For the attending physician.
        - TREATMENT: Output and rules visible. No processing metadata.
        - OPERATIONS: Aggregate only. Individual results redacted.
        - RESEARCH: De-identified. Numbers replaced with hashes.

        Args:
            result: The FizzBuzz result to redact.
            access_level: The access level to apply. Defaults to
                the configured default.

        Returns:
            A redacted dict representation of the result.
        """
        level = access_level or self._default_level

        # Log PHI access
        access_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "number": result.number,
            "access_level": level.name,
            "result_id": result.result_id,
        }
        self._phi_access_log.append(access_entry)

        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=EventType.HIPAA_MINIMUM_NECESSARY_APPLIED,
                payload=access_entry,
                source="HIPAAGuard",
            ))

        if level == HIPAAMinimumNecessaryLevel.FULL_ACCESS:
            return {
                "number": result.number,
                "output": result.output,
                "matched_rules": len(result.matched_rules),
                "processing_time_ns": result.processing_time_ns,
                "result_id": result.result_id,
                "metadata": result.metadata,
                "access_level": "FULL_ACCESS",
                "hipaa_notice": "Full PHI access granted. Handle with care.",
            }

        if level == HIPAAMinimumNecessaryLevel.TREATMENT:
            return {
                "number": result.number,
                "output": result.output,
                "matched_rules": len(result.matched_rules),
                "access_level": "TREATMENT",
                "hipaa_notice": "Treatment-level access. Metadata redacted.",
            }

        if level == HIPAAMinimumNecessaryLevel.OPERATIONS:
            self._redaction_count += 1
            return {
                "number": "[PHI REDACTED - MINIMUM NECESSARY]",
                "output": "[PHI REDACTED - MINIMUM NECESSARY]",
                "matched_rules": "[REDACTED]",
                "access_level": "OPERATIONS",
                "hipaa_notice": (
                    "Operations-level access. Individual results redacted. "
                    "Only aggregate statistics are available at this clearance."
                ),
            }

        if level == HIPAAMinimumNecessaryLevel.RESEARCH:
            self._redaction_count += 1
            # De-identify: hash the number
            de_id = hashlib.sha256(
                f"fizzbuzz-research-{result.number}".encode()
            ).hexdigest()[:12]
            return {
                "subject_id": f"SUBJ-{de_id}",
                "output_hash": hashlib.sha256(
                    result.output.encode()
                ).hexdigest()[:16],
                "access_level": "RESEARCH",
                "hipaa_notice": (
                    "Research-level access. All identifiers removed. "
                    "IRB approval required. Do not attempt re-identification."
                ),
            }

        return {"error": "Unknown access level", "access_level": level.name}

    def get_phi_access_log(self) -> list[dict[str, Any]]:
        """Return the PHI access audit log."""
        return list(self._phi_access_log)

    def get_statistics(self) -> dict[str, Any]:
        """Return HIPAA statistics."""
        return {
            "phi_encryptions": self._encryption_count,
            "phi_redactions": self._redaction_count,
            "phi_access_events": len(self._phi_access_log),
            "encryption_algorithm": self._encryption_algorithm,
            "actual_security_provided": "None",
        }


# ================================================================
# Compliance Framework — Orchestrator
# ================================================================


class ComplianceFramework:
    """Orchestrates SOX, GDPR, and HIPAA compliance for FizzBuzz operations.

    This is the grand unifying compliance engine that ties together
    all three regulatory regimes into a single, cohesive framework
    of bureaucratic overhead. It coordinates:

    - SOX segregation of duties assignments
    - GDPR consent checks and erasure requests
    - HIPAA minimum necessary enforcement and "encryption"
    - Bob McFizzington's stress level management

    Bob's stress level starts at 94.7% and increases by 0.3% with
    every compliance check performed. It has no maximum value, because
    Bob's capacity for stress is, like the universe, infinite and
    ever-expanding.
    """

    def __init__(
        self,
        sox_auditor: Optional[SOXAuditor] = None,
        gdpr_controller: Optional[GDPRController] = None,
        hipaa_guard: Optional[HIPAAGuard] = None,
        event_bus: Any = None,
        bob_stress_level: float = 94.7,
    ) -> None:
        self._sox = sox_auditor
        self._gdpr = gdpr_controller
        self._hipaa = hipaa_guard
        self._event_bus = event_bus
        self._bob_stress_level = bob_stress_level
        self._data_classifier = DataClassificationEngine(event_bus=event_bus)
        self._check_results: list[ComplianceCheckResult] = []
        self._total_checks = 0

    def perform_compliance_check(
        self,
        result: FizzBuzzResult,
    ) -> list[ComplianceCheckResult]:
        """Perform a full compliance check across all enabled regimes.

        This is the main entry point for compliance processing. It
        subjects a FizzBuzz result to SOX segregation verification,
        GDPR consent validation, HIPAA minimum necessary enforcement,
        and data classification. Each check increases Bob's stress.

        Args:
            result: The FizzBuzz result to check for compliance.

        Returns:
            A list of ComplianceCheckResult objects, one per regime.
        """
        self._total_checks += 1
        results: list[ComplianceCheckResult] = []

        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=EventType.COMPLIANCE_CHECK_STARTED,
                payload={
                    "number": result.number,
                    "check_number": self._total_checks,
                    "bob_stress_level": self._bob_stress_level,
                },
                source="ComplianceFramework",
            ))

        # Classify the data first
        classification = self._data_classifier.classify(result)
        result.metadata["data_classification"] = classification.name

        # SOX check
        if self._sox is not None:
            sox_result = self._check_sox(result)
            results.append(sox_result)

        # GDPR check
        if self._gdpr is not None:
            gdpr_result = self._check_gdpr(result)
            results.append(gdpr_result)

        # HIPAA check
        if self._hipaa is not None:
            hipaa_result = self._check_hipaa(result)
            results.append(hipaa_result)

        # Update Bob's stress level
        self._bob_stress_level += 0.3
        for check in results:
            if check.verdict == ComplianceVerdict.NON_COMPLIANT:
                self._bob_stress_level += 1.5
            elif check.verdict == ComplianceVerdict.PARADOX_DETECTED:
                self._bob_stress_level += 5.0

        self._check_results.extend(results)

        # Determine overall verdict
        all_passed = all(
            r.verdict in (ComplianceVerdict.COMPLIANT, ComplianceVerdict.UNDER_REVIEW)
            for r in results
        )

        event_type = (
            EventType.COMPLIANCE_CHECK_PASSED if all_passed
            else EventType.COMPLIANCE_CHECK_FAILED
        )
        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=event_type,
                payload={
                    "number": result.number,
                    "verdicts": {r.regime.name: r.verdict.name for r in results},
                    "bob_stress_level": self._bob_stress_level,
                },
                source="ComplianceFramework",
            ))

        return results

    def _check_sox(self, result: FizzBuzzResult) -> ComplianceCheckResult:
        """Perform SOX compliance check."""
        assert self._sox is not None
        try:
            assignments = self._sox.assign_duties(result.number)
            segregation_ok = self._sox._verify_segregation(assignments)

            result.metadata["sox_assignments"] = {
                role: person.name for role, person in assignments.items()
            }

            return ComplianceCheckResult(
                regime=ComplianceRegime.SOX,
                verdict=(
                    ComplianceVerdict.COMPLIANT if segregation_ok
                    else ComplianceVerdict.NON_COMPLIANT
                ),
                details=(
                    f"Segregation of duties {'satisfied' if segregation_ok else 'VIOLATED'}. "
                    f"Fizz: {assignments.get('FIZZ_EVALUATOR', PersonnelAssignment('?', '', '')).name}, "
                    f"Buzz: {assignments.get('BUZZ_EVALUATOR', PersonnelAssignment('?', '', '')).name}, "
                    f"Format: {assignments.get('FORMATTER', PersonnelAssignment('?', '', '')).name}, "
                    f"Audit: {assignments.get('AUDITOR', PersonnelAssignment('?', '', '')).name}"
                ),
                bob_stress_delta=0.3,
            )
        except SOXSegregationViolationError as e:
            return ComplianceCheckResult(
                regime=ComplianceRegime.SOX,
                verdict=ComplianceVerdict.NON_COMPLIANT,
                violations=(str(e),),
                details=f"Segregation enforcement failed: {e}",
                bob_stress_delta=2.0,
            )

    def _check_gdpr(self, result: FizzBuzzResult) -> ComplianceCheckResult:
        """Perform GDPR compliance check."""
        assert self._gdpr is not None

        has_consent = self._gdpr.has_consent(result.number)
        if not has_consent:
            # Try to obtain consent
            has_consent = self._gdpr.request_consent(result.number)

        if has_consent:
            return ComplianceCheckResult(
                regime=ComplianceRegime.GDPR,
                verdict=ComplianceVerdict.COMPLIANT,
                details=(
                    f"Consent obtained for data subject {result.number}. "
                    f"Lawful basis: legitimate interest in modulo arithmetic. "
                    f"Data classification: {result.metadata.get('data_classification', 'UNKNOWN')}"
                ),
                bob_stress_delta=0.1,
            )
        else:
            return ComplianceCheckResult(
                regime=ComplianceRegime.GDPR,
                verdict=ComplianceVerdict.NON_COMPLIANT,
                violations=(
                    f"No consent for data subject {result.number}",
                ),
                details=(
                    f"GDPR Article 6 violation: No lawful basis for processing "
                    f"data subject {result.number}. The number's FizzBuzz result "
                    f"has been computed without their explicit consent."
                ),
                bob_stress_delta=3.0,
            )

    def _check_hipaa(self, result: FizzBuzzResult) -> ComplianceCheckResult:
        """Perform HIPAA compliance check."""
        assert self._hipaa is not None

        # Encrypt the result for compliance
        encrypted_output = self._hipaa.encrypt_phi(result.output)
        result.metadata["hipaa_encrypted_output"] = encrypted_output

        # Apply minimum necessary
        redacted = self._hipaa.apply_minimum_necessary(result)
        result.metadata["hipaa_access_level"] = redacted.get("access_level", "UNKNOWN")

        return ComplianceCheckResult(
            regime=ComplianceRegime.HIPAA,
            verdict=ComplianceVerdict.COMPLIANT,
            details=(
                f"PHI encrypted using {self._hipaa._encryption_algorithm}. "
                f"Access level: {redacted.get('access_level', 'UNKNOWN')}. "
                f"Military-grade RFC 4648 encoding applied successfully. "
                f"Data is now 33% larger and 0% more secure."
            ),
            bob_stress_delta=0.2,
        )

    def process_erasure_request(self, number: int) -> DataDeletionCertificate:
        """Process a GDPR right-to-erasure request.

        Delegates to the GDPRController, which will inevitably encounter
        THE COMPLIANCE PARADOX and issue a certificate documenting the
        irreconcilable conflict between GDPR, event sourcing, blockchain
        immutability, and SOX retention requirements.

        Args:
            number: The data subject requesting erasure.

        Returns:
            A DataDeletionCertificate.

        Raises:
            ComplianceFrameworkNotEnabledError: If GDPR is not enabled.
        """
        if self._gdpr is None:
            raise ComplianceFrameworkNotEnabledError()

        certificate = self._gdpr.request_erasure(number)

        # Bob's stress level goes up significantly for erasure paradoxes
        self._bob_stress_level += 5.0

        return certificate

    @property
    def bob_stress_level(self) -> float:
        """Bob McFizzington's current stress level."""
        return self._bob_stress_level

    @property
    def total_checks(self) -> int:
        """Total number of compliance checks performed."""
        return self._total_checks

    def get_check_results(self) -> list[ComplianceCheckResult]:
        """Return all compliance check results."""
        return list(self._check_results)

    def get_posture_summary(self) -> dict[str, Any]:
        """Return the overall compliance posture summary."""
        total = len(self._check_results)
        compliant = sum(
            1 for r in self._check_results
            if r.verdict == ComplianceVerdict.COMPLIANT
        )
        non_compliant = sum(
            1 for r in self._check_results
            if r.verdict == ComplianceVerdict.NON_COMPLIANT
        )
        paradoxes = sum(
            1 for r in self._check_results
            if r.verdict == ComplianceVerdict.PARADOX_DETECTED
        )

        return {
            "total_checks": total,
            "compliant": compliant,
            "non_compliant": non_compliant,
            "paradoxes": paradoxes,
            "compliance_rate": (compliant / total * 100) if total > 0 else 0.0,
            "bob_stress_level": self._bob_stress_level,
            "sox_stats": self._sox.get_audit_trail() if self._sox else [],
            "gdpr_stats": self._gdpr.get_statistics() if self._gdpr else {},
            "hipaa_stats": self._hipaa.get_statistics() if self._hipaa else {},
            "classification_stats": self._data_classifier.get_statistics(),
        }


# ================================================================
# Compliance Middleware
# ================================================================


class ComplianceMiddleware(IMiddleware):
    """Middleware that enforces compliance checks on every FizzBuzz evaluation.

    Priority: -5 (runs very early in the pipeline, before most other
    middleware, because compliance must be consulted before any work
    is done — even work as trivial as computing n % 3).

    When enabled, every number that passes through the pipeline is
    subjected to the full weight of SOX, GDPR, and HIPAA compliance
    frameworks. Each evaluation triggers:

    1. GDPR consent verification (auto-granted, but logged thoroughly)
    2. SOX duty assignment (virtual personnel shuffling)
    3. HIPAA PHI "encryption" (base64, logged as military-grade)
    4. Data classification (PUBLIC through TOP_SECRET_FIZZBUZZ)
    5. Bob McFizzington's stress level update (+0.3% per check)

    The middleware adds compliance metadata to the processing context,
    creating a rich audit trail that nobody will ever read but everyone
    will feel better knowing exists.
    """

    def __init__(
        self,
        compliance_framework: ComplianceFramework,
        event_bus: Any = None,
    ) -> None:
        self._framework = compliance_framework
        self._event_bus = event_bus

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process the context through compliance checks.

        Runs GDPR consent check before evaluation, then performs
        full compliance check on the result after evaluation.
        """
        # Pre-evaluation: GDPR consent
        if self._framework._gdpr is not None:
            consent = self._framework._gdpr.request_consent(context.number)
            context.metadata["gdpr_consent"] = consent

        # Let the pipeline proceed
        result = next_handler(context)

        # Post-evaluation: Full compliance check
        if result.results:
            latest = result.results[-1]
            check_results = self._framework.perform_compliance_check(latest)

            # Add compliance metadata to context
            result.metadata["compliance_checks"] = [
                {
                    "regime": r.regime.name,
                    "verdict": r.verdict.name,
                    "details": r.details,
                }
                for r in check_results
            ]
            result.metadata["bob_stress_level"] = self._framework.bob_stress_level
            result.metadata["data_classification"] = latest.metadata.get(
                "data_classification", "UNCLASSIFIED"
            )

        return result

    def get_name(self) -> str:
        return "ComplianceMiddleware"

    def get_priority(self) -> int:
        return -5


# ================================================================
# Compliance Dashboard
# ================================================================


class ComplianceDashboard:
    """ASCII dashboard for the Compliance & Regulatory Framework.

    Renders a comprehensive compliance posture overview including:
    - Overall compliance rate
    - Per-regime breakdown (SOX, GDPR, HIPAA)
    - Bob McFizzington's stress level (with visual indicator)
    - Data classification distribution
    - Violation summary
    - Erasure paradox counter

    The dashboard is rendered in glorious ASCII art, because SVG
    charts would require a dependency and we're stdlib-only.
    """

    @staticmethod
    def render(
        framework: ComplianceFramework,
        width: int = 60,
    ) -> str:
        """Render the compliance dashboard."""
        posture = framework.get_posture_summary()
        lines: list[str] = []
        hr = "+" + "=" * (width - 2) + "+"
        thin_hr = "+" + "-" * (width - 2) + "+"

        lines.append("")
        lines.append(f"  {hr}")
        lines.append(f"  |{'COMPLIANCE & REGULATORY DASHBOARD':^{width - 2}}|")
        lines.append(f"  |{'SOX / GDPR / HIPAA':^{width - 2}}|")
        lines.append(f"  {hr}")

        # Overall posture
        total = posture["total_checks"]
        compliant = posture["compliant"]
        rate = posture["compliance_rate"]
        non_compliant = posture["non_compliant"]
        paradoxes = posture["paradoxes"]

        lines.append(f"  |{'COMPLIANCE POSTURE':^{width - 2}}|")
        lines.append(f"  {thin_hr}")

        # Compliance rate bar
        bar_width = width - 20
        filled = int(bar_width * rate / 100) if total > 0 else 0
        bar = "#" * filled + "-" * (bar_width - filled)
        lines.append(f"  | Rate: [{bar}] {rate:5.1f}% |")

        lines.append(f"  | Total Checks:    {total:<{width - 22}}|")
        lines.append(f"  | Compliant:       {compliant:<{width - 22}}|")
        lines.append(f"  | Non-Compliant:   {non_compliant:<{width - 22}}|")
        lines.append(f"  | Paradoxes:       {paradoxes:<{width - 22}}|")

        # Bob McFizzington's stress level
        lines.append(f"  {thin_hr}")
        lines.append(f"  |{'BOB McFIZZINGTON - STRESS MONITOR':^{width - 2}}|")
        lines.append(f"  {thin_hr}")

        stress = posture["bob_stress_level"]
        stress_bar_width = width - 24
        stress_filled = min(int(stress_bar_width * stress / 150), stress_bar_width)
        stress_bar = "!" * stress_filled + "." * (stress_bar_width - stress_filled)
        lines.append(f"  | Stress: [{stress_bar}] {stress:5.1f}% |")

        if stress < 80:
            mood = "Unusually calm (suspicious)"
        elif stress < 95:
            mood = "Mildly panicked (normal)"
        elif stress < 100:
            mood = "Existentially anxious"
        elif stress < 120:
            mood = "CRITICAL - Considering resignation"
        else:
            mood = "BEYOND HELP - Send chocolate"

        mood_str = f"  | Mood: {mood:<{width - 11}}|"
        lines.append(mood_str)
        lines.append(f"  | Available: {'No (never)' :<{width - 16}}|")

        # Classification breakdown
        class_stats = posture.get("classification_stats", {})
        by_level = class_stats.get("by_level", {})
        if by_level:
            lines.append(f"  {thin_hr}")
            lines.append(f"  |{'DATA CLASSIFICATION BREAKDOWN':^{width - 2}}|")
            lines.append(f"  {thin_hr}")
            for level_name, count in by_level.items():
                if count > 0:
                    label = f"  | {level_name}:"
                    lines.append(f"{label:<{width - len(str(count)) - 1}}{count} |")

        # GDPR stats
        gdpr_stats = posture.get("gdpr_stats", {})
        if gdpr_stats:
            lines.append(f"  {thin_hr}")
            lines.append(f"  |{'GDPR STATUS':^{width - 2}}|")
            lines.append(f"  {thin_hr}")
            lines.append(f"  | Consents Granted: {gdpr_stats.get('consents_granted', 0):<{width - 23}}|")
            lines.append(f"  | Erasure Requests: {gdpr_stats.get('erasure_requests', 0):<{width - 23}}|")
            lines.append(f"  | Paradoxes:        {gdpr_stats.get('paradoxes_encountered', 0):<{width - 23}}|")

        # HIPAA stats
        hipaa_stats = posture.get("hipaa_stats", {})
        if hipaa_stats:
            lines.append(f"  {thin_hr}")
            lines.append(f"  |{'HIPAA STATUS':^{width - 2}}|")
            lines.append(f"  {thin_hr}")
            lines.append(f"  | PHI Encryptions:  {hipaa_stats.get('phi_encryptions', 0):<{width - 23}}|")
            encryption_algo = hipaa_stats.get('encryption_algorithm', 'N/A')
            lines.append(f"  | Algorithm:        {encryption_algo:<{width - 23}}|")
            actual_sec = hipaa_stats.get('actual_security_provided', 'None')
            lines.append(f"  | Actual Security:  {actual_sec:<{width - 23}}|")

        # SOX stats
        sox_trail = posture.get("sox_stats", [])
        if sox_trail:
            lines.append(f"  {thin_hr}")
            lines.append(f"  |{'SOX AUDIT TRAIL':^{width - 2}}|")
            lines.append(f"  {thin_hr}")
            lines.append(f"  | Duty Assignments:  {len(sox_trail):<{width - 24}}|")
            violations = sum(
                1 for entry in sox_trail
                if not entry.get("segregation_satisfied", True)
            )
            lines.append(f"  | Violations:        {violations:<{width - 24}}|")

        lines.append(f"  {hr}")
        lines.append("")

        return "\n".join(lines)

    @staticmethod
    def render_erasure_certificate(certificate: DataDeletionCertificate) -> str:
        """Render a GDPR erasure certificate in ASCII format."""
        width = 62
        hr = "+" + "=" * (width - 2) + "+"
        thin_hr = "+" + "-" * (width - 2) + "+"
        lines: list[str] = []

        lines.append("")
        lines.append(f"  {hr}")
        lines.append(f"  |{'GDPR DATA DELETION CERTIFICATE':^{width - 2}}|")
        lines.append(f"  |{'(Right-to-Erasure under Article 17)':^{width - 2}}|")
        lines.append(f"  {hr}")
        lines.append(f"  | Certificate ID: {certificate.certificate_id[:20]:<{width - 22}}|")
        lines.append(f"  | Data Subject:   {certificate.data_subject:<{width - 22}}|")
        lines.append(f"  | Status:         {certificate.status.name:<{width - 22}}|")
        lines.append(f"  {thin_hr}")

        lines.append(f"  |{'STORES CHECKED':^{width - 2}}|")
        lines.append(f"  {thin_hr}")
        for store in certificate.stores_checked:
            truncated = store[:width - 8]
            lines.append(f"  | - {truncated:<{width - 6}}|")

        lines.append(f"  {thin_hr}")
        lines.append(f"  |{'ERASURE RESULTS':^{width - 2}}|")
        lines.append(f"  {thin_hr}")

        lines.append(f"  | Erased ({len(certificate.stores_erased)}):{' ' * (width - 16 - len(str(len(certificate.stores_erased))))}|")
        for store in certificate.stores_erased:
            truncated = store[:width - 10]
            lines.append(f"  |   [OK] {truncated:<{width - 10}}|")

        lines.append(f"  | Refused ({len(certificate.stores_refused)}):{' ' * (width - 17 - len(str(len(certificate.stores_refused))))}|")
        for store in certificate.stores_refused:
            truncated = store[:width - 10]
            lines.append(f"  |   [!!] {truncated:<{width - 10}}|")

        if certificate.paradox_explanation:
            lines.append(f"  {thin_hr}")
            lines.append(f"  |{'*** THE COMPLIANCE PARADOX ***':^{width - 2}}|")
            lines.append(f"  {thin_hr}")
            for para_line in certificate.paradox_explanation.split("\n"):
                truncated = para_line[:width - 6]
                lines.append(f"  | {truncated:<{width - 4}}|")

        lines.append(f"  {hr}")
        lines.append("")

        return "\n".join(lines)

    @staticmethod
    def render_report(framework: ComplianceFramework) -> str:
        """Render a comprehensive compliance report."""
        posture = framework.get_posture_summary()
        width = 62
        hr = "+" + "=" * (width - 2) + "+"
        thin_hr = "+" + "-" * (width - 2) + "+"
        lines: list[str] = []

        lines.append("")
        lines.append(f"  {hr}")
        lines.append(f"  |{'COMPREHENSIVE COMPLIANCE REPORT':^{width - 2}}|")
        lines.append(f"  |{'Enterprise FizzBuzz Platform':^{width - 2}}|")
        lines.append(f"  {hr}")

        lines.append(f"  | Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'):<{width - 16}}|")
        lines.append(f"  | Compliance Officer: {'Bob McFizzington (UNAVAILABLE)':<{width - 25}}|")

        rate = posture["compliance_rate"]
        if rate >= 95:
            grade = "A  (Exemplary FizzBuzz Governance)"
        elif rate >= 80:
            grade = "B  (Acceptable with Reservations)"
        elif rate >= 60:
            grade = "C  (Needs Improvement)"
        elif rate >= 40:
            grade = "D  (Regulatory Action Imminent)"
        else:
            grade = "F  (Catastrophic Compliance Failure)"

        lines.append(f"  | Compliance Grade: {grade:<{width - 23}}|")
        lines.append(f"  {thin_hr}")

        # Per-regime results
        check_results = framework.get_check_results()
        for regime in ComplianceRegime:
            regime_checks = [r for r in check_results if r.regime == regime]
            if regime_checks:
                regime_compliant = sum(
                    1 for r in regime_checks
                    if r.verdict == ComplianceVerdict.COMPLIANT
                )
                regime_rate = (regime_compliant / len(regime_checks) * 100) if regime_checks else 0
                lines.append(f"  | {regime.name}: {regime_compliant}/{len(regime_checks)} compliant ({regime_rate:.0f}%)")
                padding = width - 4 - len(f"{regime.name}: {regime_compliant}/{len(regime_checks)} compliant ({regime_rate:.0f}%)")
                lines[-1] = lines[-1] + " " * max(0, padding) + "|"

        lines.append(f"  {thin_hr}")

        # Recommendations
        lines.append(f"  |{'RECOMMENDATIONS':^{width - 2}}|")
        lines.append(f"  {thin_hr}")

        recommendations = [
            "1. Consider hiring a second compliance officer",
            "   (Bob cannot do this alone).",
            "2. Resolve THE COMPLIANCE PARADOX before the next",
            "   regulatory audit (estimated: never).",
            "3. Upgrade base64 'encryption' to actual encryption",
            "   (estimated cost: $0, estimated willpower: 0).",
            "4. Send Bob McFizzington on a wellness retreat.",
            f"   His stress level ({posture['bob_stress_level']:.1f}%) is concerning.",
        ]
        for rec in recommendations:
            lines.append(f"  | {rec:<{width - 4}}|")

        lines.append(f"  {hr}")
        lines.append("")

        return "\n".join(lines)
