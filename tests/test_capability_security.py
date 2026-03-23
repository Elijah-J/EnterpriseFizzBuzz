"""
Tests for the FizzCap Capability-Based Security Model.

Validates the core invariants of the object-capability system:
  - Capabilities are unforgeable (HMAC-SHA256 signed)
  - Capabilities are attenuatable (monotonically narrowing)
  - Capabilities are revocable (cascade through delegation DAG)
  - The confused deputy problem is eliminated
"""

from __future__ import annotations

import time

import pytest

from enterprise_fizzbuzz.domain.exceptions import (
    CapabilityAmplificationError,
    CapabilitySecurityError,
    CapabilityVerificationError,
    CapabilityRevocationError,
)
from enterprise_fizzbuzz.infrastructure.capability_security import (
    AttenuationChain,
    Capability,
    CapabilityDashboard,
    CapabilityManager,
    CapabilityMiddleware,
    CapabilityMint,
    ConfusedDeputyGuard,
    DelegationGraph,
    Operation,
    _MintSingletonMeta,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset singleton state between tests."""
    _MintSingletonMeta.reset()
    yield
    _MintSingletonMeta.reset()


@pytest.fixture
def mint():
    return CapabilityMint(secret_key="test-secret-key")


@pytest.fixture
def manager():
    return CapabilityManager(secret_key="test-manager-key", mode="native")


# ============================================================
# Operation Enum Tests
# ============================================================


class TestOperation:
    def test_four_operations_exist(self):
        assert len(Operation) == 4

    def test_operation_names(self):
        names = {op.name for op in Operation}
        assert names == {"READ", "WRITE", "EXECUTE", "DELEGATE"}

    def test_operations_are_distinct(self):
        ops = list(Operation)
        for i, op1 in enumerate(ops):
            for op2 in ops[i + 1:]:
                assert op1 != op2


# ============================================================
# Capability Token Tests
# ============================================================


class TestCapability:
    def test_capability_is_frozen(self, mint):
        cap = mint.mint("res", frozenset({Operation.READ}), "holder")
        with pytest.raises(AttributeError):
            cap.resource = "other"

    def test_capability_has_operation(self, mint):
        cap = mint.mint("res", frozenset({Operation.READ, Operation.WRITE}), "holder")
        assert cap.has_operation(Operation.READ)
        assert cap.has_operation(Operation.WRITE)
        assert not cap.has_operation(Operation.EXECUTE)

    def test_capability_constraint_dict(self, mint):
        cap = mint.mint("res", frozenset({Operation.READ}), "holder", constraints={"a": "1", "b": "2"})
        d = cap.constraint_dict
        assert d == {"a": "1", "b": "2"}

    def test_capability_repr(self, mint):
        cap = mint.mint("res", frozenset({Operation.READ}), "holder")
        r = repr(cap)
        assert "Capability" in r
        assert "res" in r
        assert "READ" in r

    def test_capability_parent_id_none_for_root(self, mint):
        cap = mint.mint("res", frozenset({Operation.READ}), "holder")
        assert cap.parent_id is None

    def test_capability_parent_id_set_for_derived(self, mint):
        parent = mint.mint("res", frozenset({Operation.READ}), "parent")
        child = mint.mint("res", frozenset({Operation.READ}), "child", parent_id=parent.cap_id)
        assert child.parent_id == parent.cap_id


# ============================================================
# CapabilityMint Tests
# ============================================================


class TestCapabilityMint:
    def test_mint_creates_valid_capability(self, mint):
        cap = mint.mint("resource", frozenset({Operation.READ}), "holder")
        assert mint.verify(cap)

    def test_mint_is_singleton(self):
        m1 = CapabilityMint(secret_key="key1")
        m2 = CapabilityMint(secret_key="key2")
        assert m1 is m2

    def test_mint_unique_cap_ids(self, mint):
        cap1 = mint.mint("r", frozenset({Operation.READ}), "h1")
        cap2 = mint.mint("r", frozenset({Operation.READ}), "h2")
        assert cap1.cap_id != cap2.cap_id

    def test_mint_unique_nonces(self, mint):
        cap1 = mint.mint("r", frozenset({Operation.READ}), "h")
        cap2 = mint.mint("r", frozenset({Operation.READ}), "h")
        assert cap1.nonce != cap2.nonce

    def test_forged_capability_fails_verification(self, mint):
        forged = Capability(
            cap_id="forged-id",
            resource="resource",
            operations=frozenset({Operation.READ}),
            constraints=(),
            nonce="forged-nonce",
            parent_id=None,
            signature="definitely-not-a-valid-hmac",
            created_at=time.time(),
            holder="evil-holder",
        )
        assert not mint.verify(forged)

    def test_tampered_resource_fails_verification(self, mint):
        cap = mint.mint("original", frozenset({Operation.READ}), "holder")
        # Create a new capability with altered resource but same signature
        tampered = Capability(
            cap_id=cap.cap_id,
            resource="tampered",
            operations=cap.operations,
            constraints=cap.constraints,
            nonce=cap.nonce,
            parent_id=cap.parent_id,
            signature=cap.signature,
            created_at=cap.created_at,
            holder=cap.holder,
        )
        assert not mint.verify(tampered)

    def test_revoke_capability(self, mint):
        cap = mint.mint("r", frozenset({Operation.READ}), "h")
        assert mint.verify(cap)
        mint.revoke(cap.cap_id)
        assert not mint.verify(cap)

    def test_is_revoked(self, mint):
        cap = mint.mint("r", frozenset({Operation.READ}), "h")
        assert not mint.is_revoked(cap.cap_id)
        mint.revoke(cap.cap_id)
        assert mint.is_revoked(cap.cap_id)

    def test_active_capabilities(self, mint):
        cap1 = mint.mint("r1", frozenset({Operation.READ}), "h1")
        cap2 = mint.mint("r2", frozenset({Operation.WRITE}), "h2")
        assert len(mint.active_capabilities) == 2
        mint.revoke(cap1.cap_id)
        active = mint.active_capabilities
        assert len(active) == 1
        assert active[0].cap_id == cap2.cap_id

    def test_total_minted(self, mint):
        assert mint.total_minted == 0
        mint.mint("r", frozenset({Operation.READ}), "h")
        mint.mint("r", frozenset({Operation.WRITE}), "h")
        assert mint.total_minted == 2

    def test_revoked_count(self, mint):
        cap = mint.mint("r", frozenset({Operation.READ}), "h")
        assert mint.revoked_count == 0
        mint.revoke(cap.cap_id)
        assert mint.revoked_count == 1

    def test_mint_log_records_events(self, mint):
        cap = mint.mint("r", frozenset({Operation.READ}), "h")
        mint.revoke(cap.cap_id)
        log = mint.mint_log
        assert len(log) == 2
        assert log[0]["event"] == "mint"
        assert log[1]["event"] == "revoke"


# ============================================================
# AttenuationChain Tests
# ============================================================


class TestAttenuationChain:
    def test_valid_attenuation_subset_ops(self, mint):
        chain = AttenuationChain(mint)
        parent = mint.mint("r", frozenset({Operation.READ, Operation.WRITE, Operation.EXECUTE}), "parent")
        child = chain.attenuate(parent, frozenset({Operation.READ}), "child")
        assert child.operations == frozenset({Operation.READ})
        assert child.parent_id == parent.cap_id
        assert mint.verify(child)

    def test_attenuation_preserves_resource(self, mint):
        chain = AttenuationChain(mint)
        parent = mint.mint("my-resource", frozenset({Operation.READ, Operation.WRITE}), "parent")
        child = chain.attenuate(parent, frozenset({Operation.READ}), "child")
        assert child.resource == "my-resource"

    def test_attenuation_adds_constraints(self, mint):
        chain = AttenuationChain(mint)
        parent = mint.mint("r", frozenset({Operation.READ, Operation.WRITE}), "parent", constraints={"env": "prod"})
        child = chain.attenuate(parent, frozenset({Operation.READ}), "child", additional_constraints={"scope": "limited"})
        constraints = child.constraint_dict
        assert constraints["env"] == "prod"
        assert constraints["scope"] == "limited"

    def test_amplification_rejected_extra_ops(self, mint):
        chain = AttenuationChain(mint)
        parent = mint.mint("r", frozenset({Operation.READ}), "parent")
        with pytest.raises(CapabilityAmplificationError) as exc_info:
            chain.attenuate(parent, frozenset({Operation.READ, Operation.WRITE}), "child")
        assert "WRITE" in str(exc_info.value)

    def test_amplification_rejected_disjoint_ops(self, mint):
        chain = AttenuationChain(mint)
        parent = mint.mint("r", frozenset({Operation.READ}), "parent")
        with pytest.raises(CapabilityAmplificationError):
            chain.attenuate(parent, frozenset({Operation.EXECUTE}), "child")

    def test_amplification_rejected_empty_ops(self, mint):
        chain = AttenuationChain(mint)
        parent = mint.mint("r", frozenset({Operation.READ}), "parent")
        with pytest.raises(CapabilityAmplificationError):
            chain.attenuate(parent, frozenset(), "child")

    def test_attenuation_of_revoked_parent_fails(self, mint):
        chain = AttenuationChain(mint)
        parent = mint.mint("r", frozenset({Operation.READ, Operation.WRITE}), "parent")
        mint.revoke(parent.cap_id)
        with pytest.raises(CapabilityVerificationError):
            chain.attenuate(parent, frozenset({Operation.READ}), "child")

    def test_chain_log(self, mint):
        chain = AttenuationChain(mint)
        parent = mint.mint("r", frozenset({Operation.READ, Operation.WRITE}), "parent")
        chain.attenuate(parent, frozenset({Operation.READ}), "child")
        assert len(chain.chain_log) == 1
        assert chain.chain_log[0]["event"] == "attenuate"

    def test_multi_level_attenuation(self, mint):
        chain = AttenuationChain(mint)
        root = mint.mint("r", frozenset({Operation.READ, Operation.WRITE, Operation.EXECUTE, Operation.DELEGATE}), "root")
        level1 = chain.attenuate(root, frozenset({Operation.READ, Operation.WRITE, Operation.EXECUTE}), "l1")
        level2 = chain.attenuate(level1, frozenset({Operation.READ, Operation.WRITE}), "l2")
        level3 = chain.attenuate(level2, frozenset({Operation.READ}), "l3")
        assert level3.operations == frozenset({Operation.READ})
        assert mint.verify(level3)


# ============================================================
# DelegationGraph Tests
# ============================================================


class TestDelegationGraph:
    def test_add_delegation(self, mint):
        graph = DelegationGraph(mint)
        graph.add_delegation(None, "root")
        graph.add_delegation("root", "child1")
        assert graph.node_count == 2
        assert graph.edge_count == 1

    def test_get_children(self, mint):
        graph = DelegationGraph(mint)
        graph.add_delegation("root", "child1")
        graph.add_delegation("root", "child2")
        children = graph.get_children("root")
        assert set(children) == {"child1", "child2"}

    def test_get_descendants_bfs(self, mint):
        graph = DelegationGraph(mint)
        graph.add_delegation("root", "c1")
        graph.add_delegation("root", "c2")
        graph.add_delegation("c1", "gc1")
        graph.add_delegation("c1", "gc2")
        graph.add_delegation("c2", "gc3")
        descendants = graph.get_descendants("root")
        assert set(descendants) == {"c1", "c2", "gc1", "gc2", "gc3"}

    def test_cascade_revocation(self, mint):
        graph = DelegationGraph(mint)
        root = mint.mint("r", frozenset({Operation.READ}), "root")
        child = mint.mint("r", frozenset({Operation.READ}), "child", parent_id=root.cap_id)
        grandchild = mint.mint("r", frozenset({Operation.READ}), "gc", parent_id=child.cap_id)

        graph.add_delegation(None, root.cap_id)
        graph.add_delegation(root.cap_id, child.cap_id)
        graph.add_delegation(child.cap_id, grandchild.cap_id)

        revoked = graph.revoke_cascade(root.cap_id)
        assert len(revoked) == 3
        assert mint.is_revoked(root.cap_id)
        assert mint.is_revoked(child.cap_id)
        assert mint.is_revoked(grandchild.cap_id)

    def test_cascade_revocation_leaf_only(self, mint):
        graph = DelegationGraph(mint)
        root = mint.mint("r", frozenset({Operation.READ}), "root")
        child = mint.mint("r", frozenset({Operation.READ}), "child", parent_id=root.cap_id)

        graph.add_delegation(None, root.cap_id)
        graph.add_delegation(root.cap_id, child.cap_id)

        revoked = graph.revoke_cascade(child.cap_id)
        assert len(revoked) == 1
        assert mint.is_revoked(child.cap_id)
        assert not mint.is_revoked(root.cap_id)

    def test_delegation_depth(self, mint):
        graph = DelegationGraph(mint)
        graph.add_delegation(None, "root")
        graph.add_delegation("root", "c1")
        graph.add_delegation("c1", "c2")
        graph.add_delegation("c2", "c3")
        assert graph.get_delegation_depth("root") == 0
        assert graph.get_delegation_depth("c1") == 1
        assert graph.get_delegation_depth("c3") == 3

    def test_get_graph_edges(self, mint):
        graph = DelegationGraph(mint)
        graph.add_delegation("a", "b")
        graph.add_delegation("b", "c")
        edges = graph.get_graph_edges()
        assert ("a", "b") in edges
        assert ("b", "c") in edges

    def test_revocation_log(self, mint):
        graph = DelegationGraph(mint)
        cap = mint.mint("r", frozenset({Operation.READ}), "h")
        graph.add_delegation(None, cap.cap_id)
        graph.revoke_cascade(cap.cap_id)
        assert len(graph.revocation_log) == 1
        assert graph.revocation_log[0]["event"] == "cascade_revoke"


# ============================================================
# ConfusedDeputyGuard Tests
# ============================================================


class TestConfusedDeputyGuard:
    def test_valid_capability_accepted(self, mint):
        guard = ConfusedDeputyGuard(mint)
        cap = mint.mint("fizzbuzz:eval", frozenset({Operation.EXECUTE}), "engine")
        assert guard.check(cap, "fizzbuzz:eval", Operation.EXECUTE)

    def test_forged_capability_rejected(self, mint):
        guard = ConfusedDeputyGuard(mint)
        forged = Capability(
            cap_id="forged", resource="fizzbuzz:eval",
            operations=frozenset({Operation.EXECUTE}),
            constraints=(), nonce="nonce", parent_id=None,
            signature="bad-sig", created_at=time.time(), holder="evil",
        )
        with pytest.raises(CapabilityVerificationError):
            guard.check(forged, "fizzbuzz:eval", Operation.EXECUTE)

    def test_wrong_resource_rejected(self, mint):
        guard = ConfusedDeputyGuard(mint)
        cap = mint.mint("fizzbuzz:eval", frozenset({Operation.EXECUTE}), "engine")
        with pytest.raises(CapabilityVerificationError) as exc_info:
            guard.check(cap, "fizzbuzz:admin", Operation.EXECUTE)
        assert "resource" in str(exc_info.value).lower() or "Resource" in str(exc_info.value)

    def test_missing_operation_rejected(self, mint):
        guard = ConfusedDeputyGuard(mint)
        cap = mint.mint("fizzbuzz:eval", frozenset({Operation.READ}), "reader")
        with pytest.raises(CapabilityVerificationError):
            guard.check(cap, "fizzbuzz:eval", Operation.WRITE)

    def test_revoked_capability_rejected(self, mint):
        guard = ConfusedDeputyGuard(mint)
        cap = mint.mint("fizzbuzz:eval", frozenset({Operation.EXECUTE}), "engine")
        mint.revoke(cap.cap_id)
        with pytest.raises(CapabilityVerificationError):
            guard.check(cap, "fizzbuzz:eval", Operation.EXECUTE)

    def test_accept_count(self, mint):
        guard = ConfusedDeputyGuard(mint)
        cap = mint.mint("r", frozenset({Operation.READ}), "h")
        guard.check(cap, "r", Operation.READ)
        guard.check(cap, "r", Operation.READ)
        assert guard.accept_count == 2

    def test_reject_count(self, mint):
        guard = ConfusedDeputyGuard(mint)
        cap = mint.mint("r", frozenset({Operation.READ}), "h")
        try:
            guard.check(cap, "wrong", Operation.READ)
        except CapabilityVerificationError:
            pass
        assert guard.reject_count == 1

    def test_guard_log(self, mint):
        guard = ConfusedDeputyGuard(mint)
        cap = mint.mint("r", frozenset({Operation.READ}), "h")
        guard.check(cap, "r", Operation.READ)
        assert len(guard.guard_log) == 1
        assert guard.guard_log[0]["event"] == "guard_accept"


# ============================================================
# CapabilityMiddleware Tests
# ============================================================


class TestCapabilityMiddleware:
    def _make_context(self, number: int = 42, metadata: dict | None = None) -> ProcessingContext:
        ctx = ProcessingContext(number=number, session_id="test-session")
        if metadata:
            ctx.metadata.update(metadata)
        return ctx

    def _identity_handler(self, ctx: ProcessingContext) -> ProcessingContext:
        return ctx

    def test_native_mode_rejects_no_capability(self, mint):
        guard = ConfusedDeputyGuard(mint)
        mw = CapabilityMiddleware(mint, guard, mode="native")
        ctx = self._make_context()
        with pytest.raises(CapabilityVerificationError):
            mw.process(ctx, self._identity_handler)

    def test_native_mode_accepts_valid_capability(self, mint):
        guard = ConfusedDeputyGuard(mint)
        mw = CapabilityMiddleware(mint, guard, mode="native")
        cap = mint.mint("fizzbuzz:evaluation", frozenset({Operation.EXECUTE}), "test")
        ctx = self._make_context(metadata={"capability": cap})
        result = mw.process(ctx, self._identity_handler)
        assert result.metadata["cap_verified"] is True

    def test_bridge_mode_auto_issues_capability(self, mint):
        guard = ConfusedDeputyGuard(mint)
        mw = CapabilityMiddleware(mint, guard, mode="bridge")
        ctx = self._make_context()
        result = mw.process(ctx, self._identity_handler)
        assert "capability" in result.metadata
        assert result.metadata["cap_verified"] is True

    def test_audit_mode_allows_no_capability(self, mint):
        guard = ConfusedDeputyGuard(mint)
        mw = CapabilityMiddleware(mint, guard, mode="audit-only")
        ctx = self._make_context()
        result = mw.process(ctx, self._identity_handler)
        assert result.number == 42

    def test_audit_mode_allows_invalid_capability(self, mint):
        guard = ConfusedDeputyGuard(mint)
        mw = CapabilityMiddleware(mint, guard, mode="audit-only")
        forged = Capability(
            cap_id="forged", resource="fizzbuzz:evaluation",
            operations=frozenset({Operation.EXECUTE}),
            constraints=(), nonce="n", parent_id=None,
            signature="bad", created_at=time.time(), holder="evil",
        )
        ctx = self._make_context(metadata={"capability": forged})
        result = mw.process(ctx, self._identity_handler)
        assert result.number == 42

    def test_middleware_log(self, mint):
        guard = ConfusedDeputyGuard(mint)
        mw = CapabilityMiddleware(mint, guard, mode="bridge")
        ctx = self._make_context()
        mw.process(ctx, self._identity_handler)
        assert len(mw.middleware_log) >= 1


# ============================================================
# CapabilityManager Tests
# ============================================================


class TestCapabilityManager:
    def test_create_root_capability(self, manager):
        cap = manager.create_root_capability(
            "resource", frozenset({Operation.READ}), "root",
        )
        assert manager.mint.verify(cap)
        assert manager.graph.node_count >= 1

    def test_delegate_and_attenuate(self, manager):
        root = manager.create_root_capability(
            "r", frozenset({Operation.READ, Operation.WRITE}), "root",
        )
        child = manager.delegate(root, frozenset({Operation.READ}), "child")
        assert child.operations == frozenset({Operation.READ})
        assert manager.graph.edge_count == 1

    def test_revoke_cascades(self, manager):
        root = manager.create_root_capability(
            "r", frozenset({Operation.READ, Operation.WRITE}), "root",
        )
        child = manager.delegate(root, frozenset({Operation.READ}), "child")
        revoked = manager.revoke(root.cap_id)
        assert len(revoked) == 2
        assert manager.mint.is_revoked(child.cap_id)

    def test_check_access(self, manager):
        cap = manager.create_root_capability(
            "r", frozenset({Operation.READ}), "h",
        )
        assert manager.check_access(cap, "r", Operation.READ)

    def test_create_middleware(self, manager):
        mw = manager.create_middleware()
        assert isinstance(mw, CapabilityMiddleware)


# ============================================================
# CapabilityDashboard Tests
# ============================================================


class TestCapabilityDashboard:
    def test_dashboard_renders_string(self, manager):
        manager.create_root_capability("r", frozenset({Operation.READ}), "h")
        dashboard = CapabilityDashboard(manager)
        output = dashboard.render()
        assert isinstance(output, str)
        assert "FizzCap" in output

    def test_dashboard_shows_active_capabilities(self, manager):
        manager.create_root_capability("fizzbuzz:eval", frozenset({Operation.READ}), "engine")
        dashboard = CapabilityDashboard(manager)
        output = dashboard.render()
        assert "ACTIVE CAPABILITIES" in output
        assert "Active: 1" in output

    def test_dashboard_shows_delegation_graph(self, manager):
        root = manager.create_root_capability("r", frozenset({Operation.READ, Operation.WRITE}), "root")
        manager.delegate(root, frozenset({Operation.READ}), "child")
        dashboard = CapabilityDashboard(manager)
        output = dashboard.render()
        assert "DELEGATION GRAPH" in output
        assert "Edges: 1" in output

    def test_dashboard_shows_guard_activity(self, manager):
        cap = manager.create_root_capability("r", frozenset({Operation.READ}), "h")
        manager.check_access(cap, "r", Operation.READ)
        dashboard = CapabilityDashboard(manager)
        output = dashboard.render()
        assert "GUARD ACTIVITY" in output
        assert "Accepted: 1" in output

    def test_dashboard_shows_revocation_log(self, manager):
        root = manager.create_root_capability("r", frozenset({Operation.READ}), "root")
        manager.revoke(root.cap_id)
        dashboard = CapabilityDashboard(manager)
        output = dashboard.render()
        assert "REVOCATION LOG" in output

    def test_dashboard_custom_width(self, manager):
        dashboard = CapabilityDashboard(manager, width=80)
        output = dashboard.render()
        # Check the header line width
        first_line = output.split("\n")[0]
        assert len(first_line) == 80


# ============================================================
# Exception Hierarchy Tests
# ============================================================


class TestExceptions:
    def test_capability_security_error_base(self):
        err = CapabilitySecurityError("test")
        assert "EFP-CAP00" in str(err)

    def test_capability_verification_error(self):
        err = CapabilityVerificationError("cap-123", "bad signature")
        assert "EFP-CAP01" in str(err)
        assert err.cap_id == "cap-123"

    def test_capability_amplification_error(self):
        err = CapabilityAmplificationError("parent-456", "extra ops")
        assert "EFP-CAP02" in str(err)
        assert err.parent_cap_id == "parent-456"

    def test_capability_revocation_error(self):
        err = CapabilityRevocationError("cap-789", "graph error")
        assert "EFP-CAP03" in str(err)
        assert err.cap_id == "cap-789"

    def test_exception_hierarchy(self):
        assert issubclass(CapabilitySecurityError, Exception)
        assert issubclass(CapabilityVerificationError, CapabilitySecurityError)
        assert issubclass(CapabilityAmplificationError, CapabilitySecurityError)
        assert issubclass(CapabilityRevocationError, CapabilitySecurityError)


# ============================================================
# Integration / End-to-End Tests
# ============================================================


class TestIntegration:
    def test_full_lifecycle(self, manager):
        """Test the full capability lifecycle: create, delegate, verify, revoke."""
        # Create root
        root = manager.create_root_capability(
            "fizzbuzz:eval",
            frozenset({Operation.READ, Operation.WRITE, Operation.EXECUTE, Operation.DELEGATE}),
            "admin",
        )

        # Delegate to engine
        engine_cap = manager.delegate(
            root,
            frozenset({Operation.READ, Operation.EXECUTE}),
            "rule_engine",
        )

        # Delegate to formatter (further attenuated)
        fmt_cap = manager.delegate(
            engine_cap,
            frozenset({Operation.READ}),
            "formatter",
        )

        # All should verify
        assert manager.check_access(root, "fizzbuzz:eval", Operation.EXECUTE)
        assert manager.check_access(engine_cap, "fizzbuzz:eval", Operation.EXECUTE)
        assert manager.check_access(fmt_cap, "fizzbuzz:eval", Operation.READ)

        # Formatter cannot WRITE
        with pytest.raises(CapabilityVerificationError):
            manager.check_access(fmt_cap, "fizzbuzz:eval", Operation.WRITE)

        # Revoke engine -> cascades to formatter
        revoked = manager.revoke(engine_cap.cap_id)
        assert len(revoked) == 2
        assert manager.mint.is_revoked(engine_cap.cap_id)
        assert manager.mint.is_revoked(fmt_cap.cap_id)
        assert not manager.mint.is_revoked(root.cap_id)

    def test_confused_deputy_prevention(self, manager):
        """Ensure the guard checks the REQUEST's capability, not ambient authority."""
        # Create two capabilities for different resources
        eval_cap = manager.create_root_capability(
            "fizzbuzz:eval", frozenset({Operation.EXECUTE}), "engine",
        )
        admin_cap = manager.create_root_capability(
            "fizzbuzz:admin", frozenset({Operation.WRITE}), "admin",
        )

        # Engine capability cannot access admin resource
        with pytest.raises(CapabilityVerificationError):
            manager.check_access(eval_cap, "fizzbuzz:admin", Operation.WRITE)

        # Admin capability cannot execute evaluations
        with pytest.raises(CapabilityVerificationError):
            manager.check_access(admin_cap, "fizzbuzz:eval", Operation.EXECUTE)

    def test_deep_delegation_chain_cascade_revocation(self, manager):
        """Test cascade revocation through a deep delegation chain."""
        caps = []
        ops = frozenset({Operation.READ, Operation.WRITE, Operation.EXECUTE, Operation.DELEGATE})
        root = manager.create_root_capability("r", ops, "root")
        caps.append(root)

        current = root
        for i in range(5):
            remaining_ops = frozenset(list(ops)[:max(1, len(ops) - i)])
            child = manager.delegate(current, remaining_ops, f"level_{i}")
            caps.append(child)
            current = child

        # Revoke root -> all 6 should be revoked
        revoked = manager.revoke(root.cap_id)
        assert len(revoked) == 6
        for cap in caps:
            assert manager.mint.is_revoked(cap.cap_id)
