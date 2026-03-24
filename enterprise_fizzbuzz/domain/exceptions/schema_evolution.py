"""
Enterprise FizzBuzz Platform - FizzSchema — Consensus-Based Schema Evolution Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class SchemaEvolutionError(FizzBuzzError):
    """Base exception for all schema evolution subsystem failures.

    Schema evolution is a mission-critical capability for any
    enterprise platform that takes data contracts seriously.
    Without rigorous schema versioning, backward compatibility
    enforcement, and consensus-based approval workflows, your
    FizzBuzz evaluation results could silently change shape
    between releases — an unacceptable violation of the Data
    Contract Governance Policy (DCGP-2024-Rev3).
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-SE00"),
            context=kwargs.pop("context", {}),
        )


class SchemaCompatibilityError(SchemaEvolutionError):
    """Raised when a schema change violates the active compatibility mode.

    Compatibility violations are the schema evolution equivalent of
    a Geneva Convention breach. If you're adding a required field
    without a default value under BACKWARD compatibility mode, you
    are effectively declaring war on every downstream consumer that
    trusted your data contract. This exception ensures such acts of
    aggression are intercepted before they reach production.
    """

    def __init__(self, schema_name: str, from_version: int, to_version: int, violations: list[str]) -> None:
        self.schema_name = schema_name
        self.from_version = from_version
        self.to_version = to_version
        self.violations = violations
        super().__init__(
            f"Schema '{schema_name}' v{from_version}->v{to_version} compatibility check failed: "
            f"{len(violations)} violation(s) detected. "
            f"First violation: {violations[0] if violations else 'unknown'}",
            error_code="EFP-SE01",
            context={
                "schema_name": schema_name,
                "from_version": from_version,
                "to_version": to_version,
                "violations": violations,
            },
        )


class SchemaRegistrationError(SchemaEvolutionError):
    """Raised when a schema cannot be registered in the schema registry.

    The schema registry is the single source of truth for all data
    contracts in the enterprise. Registration failures can occur due
    to duplicate fingerprints, version conflicts, or consensus
    rejection by the Paxos approval committee. Each failure mode
    represents a distinct governance violation that must be
    investigated by the Schema Review Board before proceeding.
    """

    def __init__(self, schema_name: str, version: int, reason: str) -> None:
        self.schema_name = schema_name
        self.version = version
        self.reason = reason
        super().__init__(
            f"Failed to register schema '{schema_name}' v{version}: {reason}",
            error_code="EFP-SE02",
            context={
                "schema_name": schema_name,
                "version": version,
                "reason": reason,
            },
        )


class SchemaConsensusError(SchemaEvolutionError):
    """Raised when the Paxos consensus cluster fails to approve a schema change.

    Schema changes in the Enterprise FizzBuzz Platform are not
    unilateral decisions. They require majority approval from a
    5-node Paxos cluster, each node independently verifying
    compatibility constraints. If quorum cannot be reached —
    whether due to node failures, compatibility disagreements,
    or Byzantine behavior — the schema change is rejected.
    Democracy is non-negotiable, even for data contracts.
    """

    def __init__(self, schema_name: str, approvals: int, required: int, detail: str) -> None:
        self.schema_name = schema_name
        self.approvals = approvals
        self.required = required
        self.detail = detail
        super().__init__(
            f"Consensus failed for schema '{schema_name}': "
            f"{approvals}/{required} approvals (quorum not reached). {detail}",
            error_code="EFP-SE03",
            context={
                "schema_name": schema_name,
                "approvals": approvals,
                "required": required,
                "detail": detail,
            },
        )

