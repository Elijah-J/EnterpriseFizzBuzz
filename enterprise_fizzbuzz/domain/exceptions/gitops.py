"""
Enterprise FizzBuzz Platform - GitOps Configuration-as-Code Simulator Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class GitOpsError(FizzBuzzError):
    """Base exception for the GitOps Configuration-as-Code Simulator.

    When your version-controlled YAML configuration for a FizzBuzz
    platform encounters a merge conflict, you know the industry has
    achieved peak enterprise. These exceptions cover everything from
    branch not found to policy violations to the existential question
    of why a single-process CLI application needs a change approval
    pipeline with dry-run simulation and blast radius estimation.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-G000"),
            context=kwargs.pop("context", {}),
        )


class GitOpsBranchNotFoundError(GitOpsError):
    """Raised when a referenced branch does not exist in the config repository.

    You attempted to checkout, merge, or otherwise interact with a branch
    that simply isn't there. Perhaps it was deleted, perhaps it was never
    created, or perhaps you're confusing this in-memory git simulator with
    actual git. Either way, the branch is as fictional as this entire
    version control system.
    """

    def __init__(self, branch_name: str) -> None:
        super().__init__(
            f"Branch '{branch_name}' not found in the configuration repository. "
            f"Available branches may be listed with --gitops-log. "
            f"Consider creating the branch first, or accepting that some branches "
            f"were never meant to exist.",
            error_code="EFP-G001",
            context={"branch_name": branch_name},
        )
        self.branch_name = branch_name


class GitOpsMergeConflictError(GitOpsError):
    """Raised when a three-way merge encounters conflicting changes.

    Two branches have modified the same configuration key in incompatible
    ways. In real git, you would open your editor, stare at conflict markers,
    question your career choices, and eventually pick one side. Here, we
    just raise an exception, which is arguably more honest.
    """

    def __init__(self, source_branch: str, target_branch: str, conflicts: list[str]) -> None:
        conflicts_str = ", ".join(conflicts[:5])
        suffix = f" (and {len(conflicts) - 5} more)" if len(conflicts) > 5 else ""
        super().__init__(
            f"Merge conflict between '{source_branch}' and '{target_branch}': "
            f"conflicting keys: {conflicts_str}{suffix}. "
            f"Automatic resolution has failed. Manual intervention required, "
            f"but since this is an in-memory simulator, that means restarting.",
            error_code="EFP-G002",
            context={
                "source_branch": source_branch,
                "target_branch": target_branch,
                "conflicts": conflicts,
            },
        )
        self.conflicts = conflicts


class GitOpsPolicyViolationError(GitOpsError):
    """Raised when a configuration change violates a policy rule.

    The PolicyEngine has examined your proposed configuration change and
    found it wanting. Perhaps you tried to set the range end to a negative
    number, or perhaps you attempted to disable both Fizz and Buzz rules
    simultaneously, which would reduce the Enterprise FizzBuzz Platform
    to merely an Enterprise Platform — and that is a policy violation of
    the highest order.
    """

    def __init__(self, rule_name: str, reason: str) -> None:
        super().__init__(
            f"Policy violation: rule '{rule_name}' rejected the change: {reason}. "
            f"The change has been blocked by the policy engine, which exists "
            f"to prevent you from shooting yourself in the foot with YAML.",
            error_code="EFP-G003",
            context={"rule_name": rule_name, "reason": reason},
        )
        self.rule_name = rule_name


class GitOpsProposalRejectedError(GitOpsError):
    """Raised when a change proposal fails to pass the approval pipeline.

    Your proposed configuration change has been reviewed by the automated
    approval pipeline (which, in single-operator mode, means you reviewed
    your own work and still found it lacking). The proposal was rejected
    at one of the five gates: validation, policy, dry-run, approval, or
    apply. Better luck next time.
    """

    def __init__(self, proposal_id: str, gate: str, reason: str) -> None:
        super().__init__(
            f"Change proposal '{proposal_id}' rejected at gate '{gate}': {reason}. "
            f"The pipeline has spoken. Your change is not worthy.",
            error_code="EFP-G004",
            context={"proposal_id": proposal_id, "gate": gate, "reason": reason},
        )
        self.proposal_id = proposal_id
        self.gate = gate


class GitOpsDriftDetectedError(GitOpsError):
    """Raised when configuration drift is detected between committed and running state.

    The running configuration has diverged from the committed configuration,
    which means someone (or something) has been modifying the config at
    runtime without going through the proper GitOps pipeline. This is the
    configuration management equivalent of finding out someone has been
    editing production directly via SSH — except here, it's a dict in RAM.
    """

    def __init__(self, drift_count: int, drifted_keys: list[str]) -> None:
        keys_str = ", ".join(drifted_keys[:5])
        suffix = f" (and {len(drifted_keys) - 5} more)" if len(drifted_keys) > 5 else ""
        super().__init__(
            f"Configuration drift detected: {drift_count} key(s) have diverged "
            f"from committed state: {keys_str}{suffix}. "
            f"Reconciliation is recommended before the drift becomes sentient.",
            error_code="EFP-G005",
            context={"drift_count": drift_count, "drifted_keys": drifted_keys},
        )
        self.drift_count = drift_count
        self.drifted_keys = drifted_keys


class GitOpsCommitNotFoundError(GitOpsError):
    """Raised when a referenced commit SHA does not exist in the repository.

    You asked for a commit that the repository has no record of. Perhaps
    it was garbage collected, perhaps it existed in a parallel universe
    where configuration management is simpler, or perhaps you just
    mistyped the SHA-256 hash. All 64 characters must match exactly.
    """

    def __init__(self, commit_sha: str) -> None:
        short_sha = commit_sha[:12] if len(commit_sha) > 12 else commit_sha
        super().__init__(
            f"Commit '{short_sha}...' not found in the configuration repository. "
            f"The commit may have been lost to the sands of in-memory time.",
            error_code="EFP-G006",
            context={"commit_sha": commit_sha},
        )

