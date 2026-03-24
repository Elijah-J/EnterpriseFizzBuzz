"""GitOps Configuration-as-Code Simulator events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("GITOPS_COMMIT_CREATED")
EventType.register("GITOPS_BRANCH_CREATED")
EventType.register("GITOPS_MERGE_COMPLETED")
EventType.register("GITOPS_PROPOSAL_SUBMITTED")
EventType.register("GITOPS_DRIFT_DETECTED")
EventType.register("GITOPS_RECONCILIATION_COMPLETED")
EventType.register("GITOPS_DASHBOARD_RENDERED")
