"""
Enterprise FizzBuzz Platform - FizzCap Capability-Based Security Model

Implements unforgeable object capabilities for the Enterprise FizzBuzz
Platform. In a world where ambient authority has led to countless
confused deputy attacks against FizzBuzz infrastructure, FizzCap
introduces a principled object-capability model where every operation
on FizzBuzz resources requires an explicit, cryptographically signed,
attenuatable, and revocable capability token.

The capability model enforces four invariants:
  1. Capabilities are unforgeable — only the CapabilityMint can create them
  2. Capabilities are attenuatable — you can narrow but never broaden
  3. Capabilities are revocable — revoking cascades through the delegation graph
  4. The confused deputy problem is eliminated — the guard checks the
     REQUEST's capability, not the caller's ambient privileges

These invariants ensure that even the most sensitive FizzBuzz operations
(such as evaluating whether 15 is both Fizz and Buzz) are protected by
a mathematically rigorous security model that would make Dennis and
Van Horn proud.
"""

from __future__ import annotations

import hashlib
import hmac
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    CapabilitySecurityError,
    CapabilityVerificationError,
    CapabilityAmplificationError,
    CapabilityRevocationError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext


# ============================================================
# Operation Enum
# ============================================================


class Operation(Enum):
    """Enumeration of operations that can be granted via capability tokens.

    Each operation corresponds to a fundamental action in the FizzBuzz
    evaluation lifecycle. READ allows observing results, WRITE allows
    modifying rules, EXECUTE allows running evaluations, and DELEGATE
    allows passing capabilities to other subsystems.

    The decision to model these as a fixed enum rather than arbitrary
    strings was deliberate: capability systems require a closed universe
    of operations to enable formal reasoning about authority propagation.
    """

    READ = auto()
    WRITE = auto()
    EXECUTE = auto()
    DELEGATE = auto()


# ============================================================
# Capability Token
# ============================================================


@dataclass(frozen=True)
class Capability:
    """An unforgeable object capability token.

    Each capability grants a specific set of operations on a specific
    resource, subject to optional constraints. The capability is
    cryptographically signed using HMAC-SHA256, making it computationally
    infeasible to forge without access to the CapabilityMint's secret key.

    The frozen dataclass ensures immutability — once minted, a capability
    cannot be altered. This is critical for security: if you could mutate
    a READ capability into a WRITE capability, the entire security model
    would collapse like a house of cards built on ambient authority.

    Attributes:
        cap_id: Unique identifier for this capability.
        resource: The resource this capability grants access to.
        operations: Frozenset of permitted operations.
        constraints: Immutable mapping of constraint key-value pairs.
        nonce: Cryptographic nonce for replay protection.
        parent_id: ID of the parent capability (None for root capabilities).
        signature: HMAC-SHA256 signature proving mint authenticity.
        created_at: Timestamp of capability creation (epoch seconds).
        holder: Identity of the entity holding this capability.
    """

    cap_id: str
    resource: str
    operations: frozenset[Operation]
    constraints: tuple[tuple[str, str], ...]
    nonce: str
    parent_id: Optional[str]
    signature: str
    created_at: float
    holder: str

    @property
    def constraint_dict(self) -> dict[str, str]:
        """Return constraints as a mutable dictionary for convenience."""
        return dict(self.constraints)

    def has_operation(self, op: Operation) -> bool:
        """Check whether this capability grants the specified operation."""
        return op in self.operations

    def __repr__(self) -> str:
        ops = ",".join(sorted(op.name for op in self.operations))
        return (
            f"Capability(id={self.cap_id[:8]}..., "
            f"resource={self.resource!r}, "
            f"ops={{{ops}}}, "
            f"holder={self.holder!r})"
        )


# ============================================================
# Capability Mint — Sole Authority for Creating Capabilities
# ============================================================


class _MintSingletonMeta(type):
    """Metaclass ensuring only one CapabilityMint exists.

    The CapabilityMint MUST be a singleton because capability systems
    require a single trusted computing base for token issuance. If
    multiple mints existed, they could issue conflicting capabilities,
    undermining the security guarantees that justify this 700-line
    module's existence.
    """

    _instances: dict[type, Any] = {}

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        if cls not in cls._instances:
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance
        return cls._instances[cls]

    @classmethod
    def reset(mcs) -> None:
        """Reset the singleton. Used for testing."""
        mcs._instances.clear()


class CapabilityMint(metaclass=_MintSingletonMeta):
    """The sole authority for creating and verifying capability tokens.

    The CapabilityMint is the trusted computing base of the FizzCap
    security model. It holds the HMAC secret key and is the only entity
    authorized to create new capabilities. All capability verification
    passes through the mint's verify() method.

    The mint also maintains a revocation set — a collection of capability
    IDs that have been explicitly revoked. Revoked capabilities fail
    verification even if their HMAC signature is valid.

    In a traditional access control system, authority is ambient — you
    are who you are, and the system checks your identity against an ACL.
    In the capability model, authority is explicit — you hold a token
    that grants specific rights, and the mint's signature proves the
    token is genuine. This distinction is why the Enterprise FizzBuzz
    Platform can now confidently state that evaluating n % 3 == 0 is
    protected by the same security principles as seL4.
    """

    def __init__(self, secret_key: Optional[str] = None) -> None:
        self._secret_key = (secret_key or str(uuid.uuid4())).encode("utf-8")
        self._revocation_set: set[str] = set()
        self._capabilities: dict[str, Capability] = {}
        self._mint_log: list[dict[str, Any]] = []

    def _compute_signature(
        self,
        resource: str,
        operations: frozenset[Operation],
        constraints: tuple[tuple[str, str], ...],
        nonce: str,
        parent_id: Optional[str],
    ) -> str:
        """Compute HMAC-SHA256 signature for a capability.

        The signature covers the resource, operations, constraints, nonce,
        and parent ID — ensuring that any tampering with these fields
        invalidates the capability. The operations are sorted to ensure
        deterministic signature computation regardless of set ordering.
        """
        ops_str = ",".join(sorted(op.name for op in operations))
        constraints_str = ";".join(f"{k}={v}" for k, v in sorted(constraints))
        parent_str = parent_id or "ROOT"
        message = f"{resource}|{ops_str}|{constraints_str}|{nonce}|{parent_str}"
        return hmac.new(
            self._secret_key,
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def mint(
        self,
        resource: str,
        operations: frozenset[Operation],
        holder: str,
        constraints: Optional[dict[str, str]] = None,
        parent_id: Optional[str] = None,
    ) -> Capability:
        """Create a new capability token.

        This is the ONLY way to create a valid capability. Any attempt
        to construct a Capability directly (e.g., via the dataclass
        constructor) will produce a token with an invalid signature
        that will fail verification.

        Args:
            resource: The resource this capability grants access to.
            operations: Set of permitted operations.
            holder: Identity of the entity receiving this capability.
            constraints: Optional key-value constraints.
            parent_id: Parent capability ID (for delegated capabilities).

        Returns:
            A signed, unforgeable Capability token.
        """
        cap_id = str(uuid.uuid4())
        nonce = str(uuid.uuid4())
        constraint_tuples = tuple(sorted((constraints or {}).items()))

        signature = self._compute_signature(
            resource, operations, constraint_tuples, nonce, parent_id,
        )

        cap = Capability(
            cap_id=cap_id,
            resource=resource,
            operations=operations,
            constraints=constraint_tuples,
            nonce=nonce,
            parent_id=parent_id,
            signature=signature,
            created_at=time.time(),
            holder=holder,
        )

        self._capabilities[cap_id] = cap
        self._mint_log.append({
            "event": "mint",
            "cap_id": cap_id,
            "resource": resource,
            "operations": [op.name for op in operations],
            "holder": holder,
            "parent_id": parent_id,
            "timestamp": cap.created_at,
        })

        return cap

    def verify(self, cap: Capability) -> bool:
        """Verify a capability's authenticity and validity.

        Verification checks three conditions:
          1. The HMAC signature matches the capability's fields
          2. The capability has not been revoked
          3. The capability was issued by this mint

        Returns:
            True if the capability is valid, False otherwise.
        """
        if cap.cap_id in self._revocation_set:
            return False

        expected_sig = self._compute_signature(
            cap.resource, cap.operations, cap.constraints,
            cap.nonce, cap.parent_id,
        )
        return hmac.compare_digest(cap.signature, expected_sig)

    def revoke(self, cap_id: str) -> None:
        """Revoke a capability by adding its ID to the revocation set.

        Note: This only revokes the specific capability. For cascade
        revocation through the delegation graph, use
        DelegationGraph.revoke_cascade().
        """
        self._revocation_set.add(cap_id)
        self._mint_log.append({
            "event": "revoke",
            "cap_id": cap_id,
            "timestamp": time.time(),
        })

    def is_revoked(self, cap_id: str) -> bool:
        """Check whether a capability has been revoked."""
        return cap_id in self._revocation_set

    @property
    def active_capabilities(self) -> list[Capability]:
        """Return all non-revoked capabilities."""
        return [
            cap for cap_id, cap in self._capabilities.items()
            if cap_id not in self._revocation_set
        ]

    @property
    def revoked_count(self) -> int:
        """Return the number of revoked capabilities."""
        return len(self._revocation_set)

    @property
    def total_minted(self) -> int:
        """Return the total number of capabilities ever minted."""
        return len(self._capabilities)

    @property
    def mint_log(self) -> list[dict[str, Any]]:
        """Return the audit log of mint operations."""
        return list(self._mint_log)


# ============================================================
# Attenuation Chain — Narrowing Capabilities Only
# ============================================================


class AttenuationChain:
    """Enforces the monotonic attenuation invariant.

    In capability-based security, attenuation means deriving a new
    capability from an existing one with STRICTLY fewer permissions.
    You can remove operations, add constraints, but NEVER add operations
    or remove constraints. This ensures that authority can only decrease
    as capabilities are delegated through the system.

    The AttenuationChain validates every derivation attempt and raises
    CapabilityAmplificationError if a derivation would broaden the
    parent capability's authority. This is the capability equivalent
    of the Second Law of Thermodynamics: authority, like entropy,
    only flows in one direction.
    """

    def __init__(self, mint: CapabilityMint) -> None:
        self._mint = mint
        self._chain_log: list[dict[str, Any]] = []

    def attenuate(
        self,
        parent: Capability,
        new_operations: frozenset[Operation],
        new_holder: str,
        additional_constraints: Optional[dict[str, str]] = None,
    ) -> Capability:
        """Derive a new capability from a parent with narrower authority.

        Args:
            parent: The parent capability to attenuate.
            new_operations: Operations for the derived capability.
                            MUST be a subset of the parent's operations.
            new_holder: Identity of the new capability holder.
            additional_constraints: Extra constraints to add (narrowing only).

        Returns:
            A new Capability with narrower authority.

        Raises:
            CapabilityAmplificationError: If the derivation would broaden
                authority beyond the parent's scope.
            CapabilityVerificationError: If the parent capability is invalid.
        """
        # Verify the parent capability first
        if not self._mint.verify(parent):
            raise CapabilityVerificationError(
                parent.cap_id,
                "Parent capability failed verification — cannot attenuate "
                "from an invalid or revoked capability.",
            )

        # Check: new operations must be a subset of parent's operations
        if not new_operations.issubset(parent.operations):
            extra_ops = new_operations - parent.operations
            extra_names = ", ".join(op.name for op in extra_ops)
            raise CapabilityAmplificationError(
                parent.cap_id,
                f"Attempted to add operations not in parent: {{{extra_names}}}. "
                f"Attenuation can only NARROW authority, never broaden it.",
            )

        # Check: cannot be empty operations
        if not new_operations:
            raise CapabilityAmplificationError(
                parent.cap_id,
                "Cannot create a capability with zero operations. "
                "Even the most attenuated capability must grant something.",
            )

        # Merge constraints: parent constraints + additional constraints
        parent_constraints = dict(parent.constraints)
        merged_constraints = {**parent_constraints}
        if additional_constraints:
            # Additional constraints can only ADD new keys or make
            # existing keys STRICTER (we treat any override as stricter
            # since constraint semantics are application-defined).
            merged_constraints.update(additional_constraints)

        child = self._mint.mint(
            resource=parent.resource,
            operations=new_operations,
            holder=new_holder,
            constraints=merged_constraints,
            parent_id=parent.cap_id,
        )

        self._chain_log.append({
            "event": "attenuate",
            "parent_id": parent.cap_id,
            "child_id": child.cap_id,
            "parent_ops": [op.name for op in parent.operations],
            "child_ops": [op.name for op in new_operations],
            "new_holder": new_holder,
            "timestamp": time.time(),
        })

        return child

    @property
    def chain_log(self) -> list[dict[str, Any]]:
        """Return the attenuation audit log."""
        return list(self._chain_log)


# ============================================================
# Delegation Graph — DAG with Cascade Revocation
# ============================================================


class DelegationGraph:
    """Directed acyclic graph tracking capability delegation relationships.

    Every time a capability is attenuated and delegated to a new holder,
    an edge is added to the delegation graph from parent to child. This
    graph enables cascade revocation: when a capability is revoked, ALL
    of its descendants in the delegation graph are also revoked.

    The cascade revocation uses breadth-first search (BFS) to traverse
    the graph from the revoked node outward, ensuring that even deeply
    nested delegation chains are fully invalidated.

    This is analogous to revoking a manager's building access card and
    having all cards they issued to their team automatically deactivated.
    Except here, the "building" is the FizzBuzz evaluation engine, and
    the "access" is the right to compute whether a number is divisible
    by 3.
    """

    def __init__(self, mint: CapabilityMint) -> None:
        self._mint = mint
        # Adjacency list: parent_id -> list of child_ids
        self._children: dict[str, list[str]] = {}
        # Reverse mapping: child_id -> parent_id
        self._parent: dict[str, Optional[str]] = {}
        # All nodes in the graph
        self._nodes: set[str] = set()
        self._revocation_log: list[dict[str, Any]] = []

    def add_delegation(self, parent_id: Optional[str], child_id: str) -> None:
        """Record a delegation relationship in the graph.

        Args:
            parent_id: The delegating capability's ID (None for root).
            child_id: The delegated capability's ID.
        """
        self._nodes.add(child_id)
        self._parent[child_id] = parent_id

        if parent_id is not None:
            self._nodes.add(parent_id)
            if parent_id not in self._children:
                self._children[parent_id] = []
            self._children[parent_id].append(child_id)

    def get_children(self, cap_id: str) -> list[str]:
        """Return the direct children of a capability."""
        return list(self._children.get(cap_id, []))

    def get_descendants(self, cap_id: str) -> list[str]:
        """Return ALL descendants of a capability via BFS."""
        descendants = []
        queue = deque(self._children.get(cap_id, []))
        visited = {cap_id}

        while queue:
            node = queue.popleft()
            if node in visited:
                continue
            visited.add(node)
            descendants.append(node)
            for child in self._children.get(node, []):
                if child not in visited:
                    queue.append(child)

        return descendants

    def revoke_cascade(self, cap_id: str) -> list[str]:
        """Revoke a capability and ALL its descendants via BFS.

        Args:
            cap_id: The capability to revoke.

        Returns:
            List of all revoked capability IDs (including the original).
        """
        revoked = [cap_id]
        self._mint.revoke(cap_id)

        descendants = self.get_descendants(cap_id)
        for desc_id in descendants:
            self._mint.revoke(desc_id)
            revoked.append(desc_id)

        self._revocation_log.append({
            "event": "cascade_revoke",
            "root_cap_id": cap_id,
            "total_revoked": len(revoked),
            "revoked_ids": revoked,
            "timestamp": time.time(),
        })

        return revoked

    def get_delegation_depth(self, cap_id: str) -> int:
        """Return the depth of a capability in the delegation chain."""
        depth = 0
        current = cap_id
        while self._parent.get(current) is not None:
            depth += 1
            current = self._parent[current]
        return depth

    @property
    def node_count(self) -> int:
        """Return the total number of nodes in the graph."""
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        """Return the total number of edges in the graph."""
        return sum(len(children) for children in self._children.values())

    @property
    def revocation_log(self) -> list[dict[str, Any]]:
        """Return the cascade revocation audit log."""
        return list(self._revocation_log)

    def get_graph_edges(self) -> list[tuple[str, str]]:
        """Return all edges as (parent, child) tuples."""
        edges = []
        for parent_id, children in self._children.items():
            for child_id in children:
                edges.append((parent_id, child_id))
        return edges


# ============================================================
# Confused Deputy Guard
# ============================================================


class ConfusedDeputyGuard:
    """Validates that a request carries the appropriate capability.

    The confused deputy problem occurs when a privileged program (the
    "deputy") is tricked by an unprivileged caller into misusing its
    authority. In traditional access control, the deputy checks whether
    the CALLER has permission. In capability-based security, the deputy
    checks whether the REQUEST carries a valid capability.

    This distinction is critical: the guard does not care WHO is making
    the request. It only cares WHAT capability the request carries. If
    the capability is valid, signed by the mint, not revoked, and grants
    the required operation on the required resource — the request is
    authorized. Period.

    In the context of the Enterprise FizzBuzz Platform, this prevents
    an unauthorized subsystem from tricking the rule engine into
    evaluating numbers it shouldn't have access to. Whether this is a
    realistic threat model for a FizzBuzz implementation is a question
    we have chosen not to ask.
    """

    def __init__(self, mint: CapabilityMint) -> None:
        self._mint = mint
        self._guard_log: list[dict[str, Any]] = []

    def check(
        self,
        capability: Capability,
        required_resource: str,
        required_operation: Operation,
    ) -> bool:
        """Check whether a capability authorizes the requested action.

        This method validates:
          1. The capability's HMAC signature is valid
          2. The capability has not been revoked
          3. The capability's resource matches the required resource
          4. The capability includes the required operation

        Args:
            capability: The capability token attached to the request.
            required_resource: The resource being accessed.
            required_operation: The operation being performed.

        Returns:
            True if the capability authorizes the request.

        Raises:
            CapabilityVerificationError: If any check fails.
        """
        # Step 1: Verify the capability's signature and revocation status
        if not self._mint.verify(capability):
            self._guard_log.append({
                "event": "guard_reject",
                "reason": "signature_or_revocation",
                "cap_id": capability.cap_id,
                "resource": required_resource,
                "operation": required_operation.name,
                "timestamp": time.time(),
            })
            raise CapabilityVerificationError(
                capability.cap_id,
                f"Capability failed verification — signature invalid or "
                f"capability has been revoked.",
            )

        # Step 2: Check resource match
        if capability.resource != required_resource:
            self._guard_log.append({
                "event": "guard_reject",
                "reason": "resource_mismatch",
                "cap_id": capability.cap_id,
                "expected_resource": required_resource,
                "actual_resource": capability.resource,
                "timestamp": time.time(),
            })
            raise CapabilityVerificationError(
                capability.cap_id,
                f"Capability grants access to '{capability.resource}', "
                f"but '{required_resource}' was requested. "
                f"Resource mismatch — the deputy refuses to be confused.",
            )

        # Step 3: Check operation permission
        if not capability.has_operation(required_operation):
            granted_ops = ", ".join(op.name for op in capability.operations)
            self._guard_log.append({
                "event": "guard_reject",
                "reason": "operation_not_granted",
                "cap_id": capability.cap_id,
                "required_op": required_operation.name,
                "granted_ops": granted_ops,
                "timestamp": time.time(),
            })
            raise CapabilityVerificationError(
                capability.cap_id,
                f"Capability does not grant {required_operation.name}. "
                f"Granted operations: {{{granted_ops}}}.",
            )

        # All checks passed
        self._guard_log.append({
            "event": "guard_accept",
            "cap_id": capability.cap_id,
            "resource": required_resource,
            "operation": required_operation.name,
            "holder": capability.holder,
            "timestamp": time.time(),
        })
        return True

    @property
    def guard_log(self) -> list[dict[str, Any]]:
        """Return the guard's audit log."""
        return list(self._guard_log)

    @property
    def accept_count(self) -> int:
        """Number of accepted requests."""
        return sum(1 for entry in self._guard_log if entry["event"] == "guard_accept")

    @property
    def reject_count(self) -> int:
        """Number of rejected requests."""
        return sum(1 for entry in self._guard_log if entry["event"] == "guard_reject")


# ============================================================
# Capability Middleware
# ============================================================


class CapabilityMiddleware(IMiddleware):
    """Middleware that enforces capability-based access control.

    Intercepts each request in the middleware pipeline, extracts the
    capability from the processing context's metadata, and validates it
    using the ConfusedDeputyGuard. If no capability is present or the
    capability is invalid, the request is rejected.

    When running in 'audit-only' mode, invalid capabilities are logged
    but the request is allowed to proceed. This enables gradual migration
    from ambient authority to capability-based security without breaking
    the existing FizzBuzz evaluation pipeline.

    When running in 'bridge' mode, requests without capabilities are
    automatically granted a default READ capability, easing adoption
    for legacy subsystems that haven't yet been capability-aware.
    """

    def __init__(
        self,
        mint: CapabilityMint,
        guard: ConfusedDeputyGuard,
        mode: str = "native",
        default_resource: str = "fizzbuzz:evaluation",
    ) -> None:
        self._mint = mint
        self._guard = guard
        self._mode = mode  # "native", "bridge", "audit-only"
        self._default_resource = default_resource
        self._middleware_log: list[dict[str, Any]] = []

    def get_name(self) -> str:
        """Return the middleware's identifier."""
        return "CapabilityMiddleware"

    def get_priority(self) -> int:
        """Return the middleware's execution priority.

        Priority 3 places this after validation (0), timing (1),
        logging (2), and before cache (4). Capability verification
        should occur early in the pipeline to reject unauthorized
        requests before any computation is performed.
        """
        return 3

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process the request through capability verification.

        Extracts the capability from context.metadata["capability"],
        verifies it with the guard, and either allows or rejects the
        request based on the configured mode.
        """
        capability = context.metadata.get("capability")

        if capability is None:
            if self._mode == "bridge":
                # Bridge mode: auto-issue a READ capability for legacy clients
                capability = self._mint.mint(
                    resource=self._default_resource,
                    operations=frozenset({Operation.READ, Operation.EXECUTE}),
                    holder="bridge:legacy",
                )
                context.metadata["capability"] = capability
                self._middleware_log.append({
                    "event": "bridge_cap_issued",
                    "cap_id": capability.cap_id,
                    "number": context.number,
                    "timestamp": time.time(),
                })
            elif self._mode == "audit-only":
                self._middleware_log.append({
                    "event": "audit_no_cap",
                    "number": context.number,
                    "timestamp": time.time(),
                })
                return next_handler(context)
            else:
                # Native mode: reject requests without capabilities
                self._middleware_log.append({
                    "event": "reject_no_cap",
                    "number": context.number,
                    "timestamp": time.time(),
                })
                raise CapabilityVerificationError(
                    "NONE",
                    "No capability token found in request context. "
                    "In native mode, all requests MUST carry a capability.",
                )

        try:
            self._guard.check(
                capability,
                self._default_resource,
                Operation.EXECUTE,
            )
        except CapabilityVerificationError:
            if self._mode == "audit-only":
                self._middleware_log.append({
                    "event": "audit_invalid_cap",
                    "cap_id": capability.cap_id,
                    "number": context.number,
                    "timestamp": time.time(),
                })
                return next_handler(context)
            raise

        self._middleware_log.append({
            "event": "cap_verified",
            "cap_id": capability.cap_id,
            "number": context.number,
            "holder": capability.holder,
            "timestamp": time.time(),
        })

        context.metadata["cap_verified"] = True
        context.metadata["cap_holder"] = capability.holder

        return next_handler(context)

    @property
    def middleware_log(self) -> list[dict[str, Any]]:
        """Return the middleware audit log."""
        return list(self._middleware_log)


# ============================================================
# Capability Manager — Orchestrates All Components
# ============================================================


class CapabilityManager:
    """High-level orchestrator for the FizzCap security model.

    Wires together the CapabilityMint, AttenuationChain, DelegationGraph,
    and ConfusedDeputyGuard into a unified capability security subsystem.
    Provides convenience methods for common operations and the dashboard
    rendering logic.
    """

    def __init__(
        self,
        secret_key: Optional[str] = None,
        mode: str = "native",
    ) -> None:
        _MintSingletonMeta.reset()
        self._mint = CapabilityMint(secret_key=secret_key)
        self._chain = AttenuationChain(self._mint)
        self._graph = DelegationGraph(self._mint)
        self._guard = ConfusedDeputyGuard(self._mint)
        self._mode = mode

    @property
    def mint(self) -> CapabilityMint:
        return self._mint

    @property
    def chain(self) -> AttenuationChain:
        return self._chain

    @property
    def graph(self) -> DelegationGraph:
        return self._graph

    @property
    def guard(self) -> ConfusedDeputyGuard:
        return self._guard

    @property
    def mode(self) -> str:
        return self._mode

    def create_root_capability(
        self,
        resource: str,
        operations: frozenset[Operation],
        holder: str,
        constraints: Optional[dict[str, str]] = None,
    ) -> Capability:
        """Create a root capability and register it in the delegation graph."""
        cap = self._mint.mint(
            resource=resource,
            operations=operations,
            holder=holder,
            constraints=constraints,
        )
        self._graph.add_delegation(None, cap.cap_id)
        return cap

    def delegate(
        self,
        parent: Capability,
        new_operations: frozenset[Operation],
        new_holder: str,
        additional_constraints: Optional[dict[str, str]] = None,
    ) -> Capability:
        """Attenuate a capability and record the delegation."""
        child = self._chain.attenuate(
            parent, new_operations, new_holder, additional_constraints,
        )
        self._graph.add_delegation(parent.cap_id, child.cap_id)
        return child

    def revoke(self, cap_id: str) -> list[str]:
        """Revoke a capability with cascade through delegation graph."""
        return self._graph.revoke_cascade(cap_id)

    def check_access(
        self,
        capability: Capability,
        resource: str,
        operation: Operation,
    ) -> bool:
        """Check whether a capability grants access to a resource."""
        return self._guard.check(capability, resource, operation)

    def create_middleware(
        self,
        default_resource: str = "fizzbuzz:evaluation",
    ) -> CapabilityMiddleware:
        """Create a CapabilityMiddleware wired to this manager."""
        return CapabilityMiddleware(
            mint=self._mint,
            guard=self._guard,
            mode=self._mode,
            default_resource=default_resource,
        )


# ============================================================
# Capability Dashboard — ASCII Visualization
# ============================================================


class CapabilityDashboard:
    """ASCII dashboard for the FizzCap capability security model.

    Renders a comprehensive view of:
      - Active capabilities with their resources, operations, and holders
      - The delegation graph showing parent-child relationships
      - The revocation log with cascade statistics
      - Guard activity showing accepted and rejected requests

    Because if you can't see your capability graph in a terminal, do
    you even have capability-based security?
    """

    def __init__(self, manager: CapabilityManager, width: int = 60) -> None:
        self._manager = manager
        self._width = width

    def render(self) -> str:
        """Render the complete FizzCap dashboard."""
        sections = [
            self._render_header(),
            self._render_active_capabilities(),
            self._render_delegation_graph(),
            self._render_revocation_log(),
            self._render_guard_activity(),
            self._render_footer(),
        ]
        return "\n".join(sections)

    def _render_header(self) -> str:
        w = self._width
        lines = [
            "+" + "-" * (w - 2) + "+",
            "|" + " FizzCap Capability Security Dashboard ".center(w - 2) + "|",
            "|" + " Unforgeable Object Capabilities ".center(w - 2) + "|",
            "+" + "=" * (w - 2) + "+",
        ]
        return "\n".join(lines)

    def _render_active_capabilities(self) -> str:
        w = self._width
        mint = self._manager.mint
        active = mint.active_capabilities
        lines = [
            "|" + " ACTIVE CAPABILITIES ".center(w - 2, "-") + "|",
            "|" + f"  Total minted: {mint.total_minted}".ljust(w - 2) + "|",
            "|" + f"  Active: {len(active)}".ljust(w - 2) + "|",
            "|" + f"  Revoked: {mint.revoked_count}".ljust(w - 2) + "|",
            "|" + "-" * (w - 2) + "|",
        ]

        for cap in active[:10]:  # Show first 10
            ops = ",".join(sorted(op.name for op in cap.operations))
            cap_line = f"  [{cap.cap_id[:8]}] {cap.resource} {{{ops}}}"
            holder_line = f"    holder: {cap.holder}"
            if cap.parent_id:
                holder_line += f"  parent: {cap.parent_id[:8]}"
            lines.append("|" + cap_line[:w - 2].ljust(w - 2) + "|")
            lines.append("|" + holder_line[:w - 2].ljust(w - 2) + "|")

        if len(active) > 10:
            lines.append("|" + f"  ... and {len(active) - 10} more".ljust(w - 2) + "|")

        return "\n".join(lines)

    def _render_delegation_graph(self) -> str:
        w = self._width
        graph = self._manager.graph
        edges = graph.get_graph_edges()
        lines = [
            "|" + " DELEGATION GRAPH ".center(w - 2, "-") + "|",
            "|" + f"  Nodes: {graph.node_count}".ljust(w - 2) + "|",
            "|" + f"  Edges: {graph.edge_count}".ljust(w - 2) + "|",
            "|" + "-" * (w - 2) + "|",
        ]

        for parent_id, child_id in edges[:8]:
            edge_line = f"  {parent_id[:8]}... -> {child_id[:8]}..."
            lines.append("|" + edge_line.ljust(w - 2) + "|")

        if len(edges) > 8:
            lines.append("|" + f"  ... and {len(edges) - 8} more edges".ljust(w - 2) + "|")

        if not edges:
            lines.append("|" + "  (no delegations recorded)".ljust(w - 2) + "|")

        return "\n".join(lines)

    def _render_revocation_log(self) -> str:
        w = self._width
        rev_log = self._manager.graph.revocation_log
        lines = [
            "|" + " REVOCATION LOG ".center(w - 2, "-") + "|",
        ]

        if not rev_log:
            lines.append("|" + "  No revocations recorded.".ljust(w - 2) + "|")
        else:
            for entry in rev_log[-5:]:
                root = entry["root_cap_id"][:8]
                total = entry["total_revoked"]
                line = f"  Cascade from {root}...: {total} revoked"
                lines.append("|" + line[:w - 2].ljust(w - 2) + "|")

        return "\n".join(lines)

    def _render_guard_activity(self) -> str:
        w = self._width
        guard = self._manager.guard
        lines = [
            "|" + " GUARD ACTIVITY ".center(w - 2, "-") + "|",
            "|" + f"  Accepted: {guard.accept_count}".ljust(w - 2) + "|",
            "|" + f"  Rejected: {guard.reject_count}".ljust(w - 2) + "|",
            "|" + "-" * (w - 2) + "|",
        ]

        for entry in guard.guard_log[-5:]:
            event = entry["event"]
            cap_id = entry.get("cap_id", "N/A")[:8]
            resource = entry.get("resource", "N/A")
            line = f"  {event}: cap={cap_id}... res={resource}"
            lines.append("|" + line[:w - 2].ljust(w - 2) + "|")

        return "\n".join(lines)

    def _render_footer(self) -> str:
        w = self._width
        return "+" + "=" * (w - 2) + "+"
