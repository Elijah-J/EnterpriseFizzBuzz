"""
Enterprise FizzBuzz Platform - FizzGit Version Control System Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class VCSError(FizzBuzzError):
    """Base exception for all FizzGit version control system errors.

    The FizzGit VCS provides content-addressable version control for
    FizzBuzz evaluation state. When operations on the commit DAG,
    object store, ref store, or merge engine fail, a VCSError or
    one of its subclasses is raised to indicate the precise failure
    mode within the version control subsystem.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.get("error_code", "EFP-VCS0"),
            context=kwargs.get("context", {}),
        )


class VCSObjectNotFoundError(VCSError):
    """Raised when a content-addressable object cannot be located in the store.

    Every object in the FizzGit store is keyed by its SHA-256 digest. If
    a requested hash is not present, the object has either never been
    created, has been garbage collected (not currently implemented, as
    FizzBuzz evaluation state is too valuable to discard), or the hash
    was corrupted in transit.
    """

    def __init__(self, object_hash: str) -> None:
        super().__init__(
            f"Object not found in FizzGit store: {object_hash[:16]}...",
            error_code="EFP-VCS1",
            context={"object_hash": object_hash},
        )
        self.object_hash = object_hash


class VCSMergeConflictError(VCSError):
    """Raised when a three-way merge encounters unresolvable conflicts.

    While the FizzGit merge engine applies domain-specific conflict
    resolution (FizzBuzz > Fizz > Buzz > number), there may be edge
    cases where the conflict cannot be automatically resolved — for
    instance, when two branches disagree on whether a number even
    exists, which would represent a fundamental ontological crisis
    in the FizzBuzz domain.
    """

    def __init__(self, branch: str, conflict_count: int) -> None:
        super().__init__(
            f"Merge of branch '{branch}' produced {conflict_count} conflict(s). "
            f"Domain-specific resolution applied where possible.",
            error_code="EFP-VCS2",
            context={"branch": branch, "conflict_count": conflict_count},
        )
        self.branch = branch
        self.conflict_count = conflict_count


class VCSBranchError(VCSError):
    """Raised when a branch operation fails.

    Branch operations can fail for several reasons: creating a branch
    that already exists, deleting the current branch, or attempting
    to check out a branch that does not exist. Each of these represents
    a violation of the ref store invariants that must be reported
    immediately.
    """

    def __init__(self, message: str, *, branch_name: str = "") -> None:
        super().__init__(
            message,
            error_code="EFP-VCS3",
            context={"branch_name": branch_name},
        )
        self.branch_name = branch_name


class VCSBisectError(VCSError):
    """Raised when a bisect operation encounters an error.

    Bisect errors occur when the binary search through commit history
    cannot proceed — either because no bisect is in progress, the
    good/bad commit range is invalid, or the commit DAG is malformed.
    """

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            error_code="EFP-VCS4",
            context={},
        )

