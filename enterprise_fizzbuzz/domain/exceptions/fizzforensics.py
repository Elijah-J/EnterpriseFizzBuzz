"""
Enterprise FizzBuzz Platform - FizzForensics Exceptions (EFP-FOR00 through EFP-FOR09)
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzForensicsError(FizzBuzzError):
    """Base exception for the FizzForensics digital forensics subsystem.

    The FizzForensics engine provides forensic analysis capabilities for
    investigating FizzBuzz evaluation anomalies. Disk image analysis,
    file carving, hash verification, and timeline reconstruction enable
    post-incident investigation of divisibility disputes with evidentiary
    rigor suitable for legal proceedings.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-FOR00",
        context: dict | None = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class DiskImageError(FizzForensicsError):
    """Raised when a disk image cannot be parsed or is corrupted.

    Forensic disk images must contain a valid partition table and
    filesystem metadata. Images that fail structural validation cannot
    be reliably analyzed and may produce misleading evidence if
    processed without correction.
    """

    def __init__(self, image_id: str, reason: str) -> None:
        super().__init__(
            f"Disk image '{image_id}' analysis failed: {reason}",
            error_code="EFP-FOR01",
            context={"image_id": image_id, "reason": reason},
        )


class FileCarveError(FizzForensicsError):
    """Raised when file carving fails to recover a complete artifact.

    File carving extracts files from unallocated disk space using
    header/footer signatures. Incomplete carves occur when the file
    footer is missing (due to overwrite) or when the carved data
    fails integrity validation.
    """

    def __init__(self, offset: int, expected_type: str, reason: str) -> None:
        super().__init__(
            f"File carve failed at offset 0x{offset:08X} "
            f"(expected type '{expected_type}'): {reason}",
            error_code="EFP-FOR02",
            context={"offset": offset, "expected_type": expected_type, "reason": reason},
        )


class HashVerificationError(FizzForensicsError):
    """Raised when a cryptographic hash verification fails.

    Hash verification ensures that evidence has not been tampered with
    since acquisition. A hash mismatch between the computed and recorded
    values indicates either data corruption or unauthorized modification
    of the evidence.
    """

    def __init__(self, expected_hash: str, computed_hash: str, algorithm: str) -> None:
        super().__init__(
            f"Hash verification failed ({algorithm}): expected {expected_hash[:16]}... "
            f"but computed {computed_hash[:16]}...",
            error_code="EFP-FOR03",
            context={
                "expected_hash": expected_hash,
                "computed_hash": computed_hash,
                "algorithm": algorithm,
            },
        )


class TimelineError(FizzForensicsError):
    """Raised when timeline reconstruction encounters inconsistent timestamps.

    Forensic timeline analysis correlates timestamps from multiple sources
    (filesystem metadata, application logs, system events). Inconsistent
    timestamps may indicate clock manipulation or anti-forensic activity.
    """

    def __init__(self, event_id: str, reason: str) -> None:
        super().__init__(
            f"Timeline reconstruction error for event '{event_id}': {reason}",
            error_code="EFP-FOR04",
            context={"event_id": event_id, "reason": reason},
        )


class ChainOfCustodyError(FizzForensicsError):
    """Raised when the chain of custody for digital evidence is broken.

    The chain of custody documents every person who handled the evidence
    and every action performed on it. A break in the chain renders the
    evidence potentially inadmissible and compromises the integrity of
    the forensic investigation.
    """

    def __init__(self, evidence_id: str, missing_step: str) -> None:
        super().__init__(
            f"Chain of custody broken for evidence '{evidence_id}': "
            f"missing custody record for step '{missing_step}'",
            error_code="EFP-FOR05",
            context={"evidence_id": evidence_id, "missing_step": missing_step},
        )


class MetadataExtractionError(FizzForensicsError):
    """Raised when metadata extraction from a file fails."""

    def __init__(self, file_path: str, reason: str) -> None:
        super().__init__(
            f"Metadata extraction failed for '{file_path}': {reason}",
            error_code="EFP-FOR06",
            context={"file_path": file_path, "reason": reason},
        )


class ForensicsMiddlewareError(FizzForensicsError):
    """Raised when the FizzForensics middleware encounters a fault."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzForensics middleware error: {reason}",
            error_code="EFP-FOR07",
            context={"reason": reason},
        )
