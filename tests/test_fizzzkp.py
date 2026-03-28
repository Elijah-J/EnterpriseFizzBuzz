"""
Enterprise FizzBuzz Platform - FizzZKP Zero-Knowledge Proof Test Suite

Validates the zero-knowledge proof system from group parameter generation
through Schnorr proof creation/verification, Pedersen commitments, and
the Fiat-Shamir transform. These tests ensure that FizzBuzz divisibility
proofs are sound (cannot be forged) and complete (always verify for
correct witnesses).

A broken proof system would allow a malicious prover to claim divisibility
by 3 for a number that is not divisible by 3, compromising the integrity
of the entire FizzBuzz audit trail.
"""

from __future__ import annotations

import random
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzzkp import (
    FizzBuzzDivisibilityProof,
    FizzZKPMiddleware,
    GroupParams,
    PedersenCommitment,
    ProofProtocol,
    ProofTranscript,
    SchnorrProof,
    SchnorrProver,
    SchnorrVerifier,
    VerificationResult,
    ZKPFizzBuzzEngine,
    default_group_params,
)
from enterprise_fizzbuzz.domain.exceptions import (
    ZeroKnowledgeProofError,
    ProofGenerationError,
    ProofVerificationError,
    FiatShamirError,
    GroupParameterError,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext


def _make_context(number: int) -> ProcessingContext:
    return ProcessingContext(number=number, session_id=str(uuid.uuid4()))


# ============================================================
# Group Parameter Tests
# ============================================================


class TestGroupParams:
    def test_default_params_valid(self):
        params = default_group_params()
        params.validate()  # Should not raise
        assert pow(params.g, params.q, params.p) == 1

    def test_invalid_p_raises(self):
        with pytest.raises(GroupParameterError):
            GroupParams(p=1, q=5, g=2).validate()

    def test_invalid_generator_raises(self):
        params = default_group_params()
        bad_params = GroupParams(p=params.p, q=params.q, g=1)
        with pytest.raises(GroupParameterError):
            bad_params.validate()

    def test_generator_wrong_order_raises(self):
        params = default_group_params()
        # g=2 with wrong order will likely fail
        bad = GroupParams(p=params.p, q=params.q - 1, g=params.g)
        with pytest.raises(GroupParameterError):
            bad.validate()


# ============================================================
# Transcript Tests
# ============================================================


class TestProofTranscript:
    def test_append_and_digest(self):
        t = ProofTranscript()
        t.append("label", "value")
        assert len(t.messages) == 1
        assert len(t.digest) == 64  # SHA-256 hex

    def test_challenge_from_empty_raises(self):
        t = ProofTranscript()
        with pytest.raises(FiatShamirError):
            t.challenge(100)

    def test_challenge_deterministic(self):
        t1 = ProofTranscript()
        t1.append("x", 42)
        c1 = t1.challenge(1000)

        t2 = ProofTranscript()
        t2.append("x", 42)
        c2 = t2.challenge(1000)
        assert c1 == c2

    def test_integrity_check(self):
        t = ProofTranscript()
        t.append("a", 1)
        t.append("b", 2)
        assert t.verify_integrity() is True


# ============================================================
# Pedersen Commitment Tests
# ============================================================


class TestPedersenCommitment:
    def test_commit_and_verify(self):
        params = default_group_params()
        pc = PedersenCommitment(params)
        c = pc.commit(42, 99)
        assert pc.verify(c, 42, 99)

    def test_different_message_fails(self):
        params = default_group_params()
        pc = PedersenCommitment(params)
        c = pc.commit(42, 99)
        assert not pc.verify(c, 43, 99)

    def test_different_randomness_fails(self):
        params = default_group_params()
        pc = PedersenCommitment(params)
        c = pc.commit(42, 99)
        assert not pc.verify(c, 42, 100)

    def test_hiding_different_randomness_different_commitment(self):
        params = default_group_params()
        pc = PedersenCommitment(params)
        c1 = pc.commit(42, 10)
        c2 = pc.commit(42, 20)
        assert c1 != c2  # Same message, different randomness


# ============================================================
# Schnorr Proof Tests
# ============================================================


class TestSchnorrProof:
    def test_valid_proof_verifies(self):
        params = default_group_params()
        secret = 12345 % params.q
        public = pow(params.g, secret, params.p)

        prover = SchnorrProver(params, rng=random.Random(42))
        proof = prover.prove(secret, public)

        verifier = SchnorrVerifier(params)
        result = verifier.verify(proof, public)
        assert result == VerificationResult.ACCEPT

    def test_wrong_public_value_rejects(self):
        params = default_group_params()
        secret = 12345 % params.q
        public = pow(params.g, secret, params.p)

        prover = SchnorrProver(params, rng=random.Random(42))
        proof = prover.prove(secret, public)

        verifier = SchnorrVerifier(params)
        wrong_public = pow(params.g, (secret + 1) % params.q, params.p)
        result = verifier.verify(proof, wrong_public)
        assert result == VerificationResult.REJECT

    def test_tampered_response_rejects(self):
        params = default_group_params()
        secret = 9999 % params.q
        public = pow(params.g, secret, params.p)

        prover = SchnorrProver(params, rng=random.Random(42))
        proof = prover.prove(secret, public)

        tampered = SchnorrProof(
            commitment=proof.commitment,
            challenge=proof.challenge,
            response=(proof.response + 1) % params.q,
        )
        verifier = SchnorrVerifier(params)
        result = verifier.verify(tampered, public)
        assert result == VerificationResult.REJECT


# ============================================================
# Divisibility Proof Tests
# ============================================================


class TestFizzBuzzDivisibilityProof:
    def test_prove_divisible_by_3(self):
        dp = FizzBuzzDivisibilityProof()
        proof = dp.prove_divisibility(9, 3)
        assert proof["divisor"] == 3

    def test_prove_not_divisible_raises(self):
        dp = FizzBuzzDivisibilityProof()
        with pytest.raises(ProofGenerationError):
            dp.prove_divisibility(7, 3)

    def test_prove_divisible_by_5(self):
        dp = FizzBuzzDivisibilityProof()
        proof = dp.prove_divisibility(10, 5)
        assert proof["divisor"] == 5

    def test_prove_divisible_by_15(self):
        dp = FizzBuzzDivisibilityProof()
        proof = dp.prove_divisibility(15, 3)
        assert proof is not None


# ============================================================
# Engine Tests
# ============================================================


class TestZKPFizzBuzzEngine:
    def test_evaluate_fizzbuzz(self):
        engine = ZKPFizzBuzzEngine(seed=42)
        result = engine.evaluate(15)
        assert result["result"] == "FizzBuzz"
        assert result["schnorr_verified"] is True

    def test_evaluate_fizz(self):
        engine = ZKPFizzBuzzEngine(seed=42)
        result = engine.evaluate(9)
        assert result["result"] == "Fizz"

    def test_evaluate_buzz(self):
        engine = ZKPFizzBuzzEngine(seed=42)
        result = engine.evaluate(10)
        assert result["result"] == "Buzz"

    def test_evaluate_plain(self):
        engine = ZKPFizzBuzzEngine(seed=42)
        result = engine.evaluate(7)
        assert result["result"] == "7"
        assert result["proof_count"] == 0

    def test_proof_log_accumulates(self):
        engine = ZKPFizzBuzzEngine(seed=42)
        engine.evaluate(3)
        engine.evaluate(5)
        engine.evaluate(7)
        assert len(engine.proof_log) == 3


# ============================================================
# Middleware Tests
# ============================================================


class TestFizzZKPMiddleware:
    def test_middleware_annotates_context(self):
        mw = FizzZKPMiddleware(seed=42)
        ctx = _make_context(15)
        called = []
        mw.process(ctx, lambda c: called.append(True))
        assert called
        assert ctx.metadata["zkp_result"] == "FizzBuzz"
        assert ctx.metadata["zkp_verified"] is True
        assert "zkp_commitment" in ctx.metadata
