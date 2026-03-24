"""
Enterprise FizzBuzz Platform - FizzPM Package Manager Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class PackageManagerError(FizzBuzzError):
    """Base exception for all FizzPM Package Manager errors.

    When the FizzPM dependency resolution engine encounters a
    failure — whether it's a missing package, a version conflict
    that would make npm weep, or an integrity hash mismatch —
    this is the exception hierarchy that catches it. Think of
    this as the 'rm -rf node_modules' of exception classes.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-PK00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class DependencyResolutionError(PackageManagerError):
    """Raised when the DPLL SAT solver cannot find a satisfying assignment.

    The Boolean satisfiability solver has exhausted all possible variable
    assignments and determined that no combination of package versions
    can satisfy the dependency constraints. This is the NP-complete
    problem that keeps package manager authors up at night, except our
    registry has 8 packages and the solver finishes in microseconds.
    The drama is entirely manufactured.
    """

    def __init__(self, package: str, reason: str) -> None:
        super().__init__(
            f"Failed to resolve dependencies for '{package}': {reason}. "
            f"The SAT solver has spoken: your dependency graph is "
            f"unsatisfiable. Consider removing some of your 8 packages.",
            error_code="EFP-PK10",
            context={"package": package, "reason": reason},
        )
        self.package = package
        self.reason = reason


class PackageNotFoundError(PackageManagerError):
    """Raised when a requested package does not exist in the registry.

    The in-memory package registry (a Python dict with 8 entries)
    does not contain the requested package. In a real package manager,
    this might indicate a typo, a removed package, or a registry
    outage. Here, it means you asked for something that was never
    part of the FizzBuzz Extended Package Ecosystem, which is
    simultaneously impressive and deeply concerning.
    """

    def __init__(self, package_name: str) -> None:
        super().__init__(
            f"Package '{package_name}' not found in the FizzPM registry. "
            f"The registry contains exactly 8 packages, and somehow you "
            f"managed to request one that doesn't exist. This is actually "
            f"a statistically impressive miss rate.",
            error_code="EFP-PK11",
            context={"package_name": package_name},
        )
        self.package_name = package_name


class PackageIntegrityError(PackageManagerError):
    """Raised when a package fails integrity verification.

    The SHA-256 checksum of the package contents does not match the
    expected hash stored in the lockfile. In a real package manager,
    this would indicate supply-chain tampering, a corrupted download,
    or a man-in-the-middle attack. Here, it means someone modified
    the description string of a dataclass that exists only in RAM.
    The threat model is robust.
    """

    def __init__(self, package_name: str, expected: str, actual: str) -> None:
        super().__init__(
            f"Integrity check failed for '{package_name}': "
            f"expected SHA-256 {expected[:16]}..., got {actual[:16]}... "
            f"Your supply chain has been compromised. (The supply chain "
            f"is a Python dictionary. The compromise is imaginary.)",
            error_code="EFP-PK12",
            context={
                "package_name": package_name,
                "expected_hash": expected,
                "actual_hash": actual,
            },
        )
        self.package_name = package_name
        self.expected = expected
        self.actual = actual


class PackageVersionConflictError(PackageManagerError):
    """Raised when two packages require incompatible versions of a dependency.

    Two or more packages in the dependency graph require mutually exclusive
    version ranges of the same dependency. This is the classic diamond
    dependency problem, except our dependency diamond has approximately
    three facets and could be resolved by a human in seconds. We use
    a SAT solver anyway, because manual resolution is for amateurs.
    """

    def __init__(self, package: str, conflicts: list[str]) -> None:
        conflicts_str = ", ".join(conflicts)
        super().__init__(
            f"Version conflict for '{package}': incompatible constraints "
            f"from [{conflicts_str}]. The diamond dependency problem has "
            f"claimed another victim. Consider therapy.",
            error_code="EFP-PK13",
            context={"package": package, "conflicts": conflicts},
        )
        self.package = package
        self.conflicts = conflicts

