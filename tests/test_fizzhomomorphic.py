"""
Enterprise FizzBuzz Platform - FizzHomomorphic Encryption Test Suite

Validates the homomorphic encryption pipeline from key generation through
encrypt/evaluate/decrypt. These tests ensure that the BFV scheme correctly
preserves plaintext semantics under homomorphic operations, and that
privacy-preserving FizzBuzz evaluation produces correct results.

An error in polynomial ring arithmetic could silently corrupt the
encrypted FizzBuzz evaluation, returning an incorrect classification
that decrypts to the wrong value with no indication of failure.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzhomomorphic import (
    BFVEngine,
    Ciphertext,
    FizzHomomorphicMiddleware,
    HEScheme,
    HomomorphicFizzBuzzEngine,
    PolynomialRing,
    PublicKey,
    SecretKey,
)
from enterprise_fizzbuzz.domain.exceptions import (
    HomomorphicEncryptionError,
    KeyGenerationError,
    EncryptionError,
    DecryptionError,
    NoiseBudgetExhaustedError,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext


def _make_context(number: int) -> ProcessingContext:
    return ProcessingContext(number=number, session_id=str(uuid.uuid4()))


# ============================================================
# Polynomial Ring Tests
# ============================================================


class TestPolynomialRing:
    def test_add_modular(self):
        ring = PolynomialRing(4, 17)
        a = [1, 2, 3, 4]
        b = [16, 15, 14, 13]
        result = ring.add(a, b)
        assert result == [0, 0, 0, 0]

    def test_subtract(self):
        ring = PolynomialRing(4, 17)
        a = [5, 5, 5, 5]
        b = [3, 3, 3, 3]
        result = ring.subtract(a, b)
        assert result == [2, 2, 2, 2]

    def test_multiply_constants(self):
        ring = PolynomialRing(4, 97)
        a = [3, 0, 0, 0]
        b = [5, 0, 0, 0]
        result = ring.multiply(a, b)
        assert result[0] == 15

    def test_negate(self):
        ring = PolynomialRing(4, 17)
        a = [5, 0, 0, 0]
        result = ring.negate(a)
        assert result[0] == 12  # 17 - 5

    def test_scalar_multiply(self):
        ring = PolynomialRing(4, 17)
        a = [3, 2, 1, 0]
        result = ring.scalar_multiply(a, 5)
        assert result[0] == 15
        assert result[1] == 10

    def test_zero_polynomial(self):
        ring = PolynomialRing(4, 17)
        z = ring.zero()
        assert all(c == 0 for c in z)

    def test_constant_polynomial(self):
        ring = PolynomialRing(4, 17)
        c = ring.constant(42)
        assert c[0] == 42 % 17
        assert all(c[i] == 0 for i in range(1, 4))


# ============================================================
# Key Generation Tests
# ============================================================


class TestBFVKeyGeneration:
    def test_generate_keys_succeeds(self):
        engine = BFVEngine(poly_degree=16, seed=42)
        sk, pk, ek = engine.generate_keys()
        assert len(sk.polynomial) == 16
        assert len(pk.poly_b) == 16

    def test_invalid_poly_degree_raises(self):
        with pytest.raises(KeyGenerationError):
            BFVEngine(poly_degree=7)  # Not a power of 2

    def test_plain_modulus_exceeds_coeff_raises(self):
        with pytest.raises(KeyGenerationError):
            BFVEngine(poly_degree=16, coeff_modulus=100, plain_modulus=200)


# ============================================================
# Encrypt/Decrypt Tests
# ============================================================


class TestBFVEncryptDecrypt:
    def test_encrypt_decrypt_roundtrip(self):
        engine = BFVEngine(poly_degree=64, coeff_modulus=65537, plain_modulus=257, seed=42)
        engine.generate_keys()
        ct = engine.encrypt(42)
        pt = engine.decrypt(ct)
        assert pt == 42

    def test_encrypt_zero(self):
        engine = BFVEngine(poly_degree=64, seed=42)
        engine.generate_keys()
        ct = engine.encrypt(0)
        pt = engine.decrypt(ct)
        assert pt == 0

    def test_encrypt_without_keys_raises(self):
        engine = BFVEngine(poly_degree=16, seed=42)
        with pytest.raises(EncryptionError):
            engine.encrypt(5)

    def test_encrypt_out_of_range_raises(self):
        engine = BFVEngine(poly_degree=16, plain_modulus=257, seed=42)
        engine.generate_keys()
        with pytest.raises(EncryptionError):
            engine.encrypt(300)


# ============================================================
# Homomorphic Operations Tests
# ============================================================


class TestHomomorphicOperations:
    def test_homomorphic_add(self):
        engine = BFVEngine(poly_degree=64, seed=42)
        engine.generate_keys()
        ct1 = engine.encrypt(10)
        ct2 = engine.encrypt(20)
        ct_sum = engine.add(ct1, ct2)
        assert ct_sum.noise_budget_bits > 0

    def test_homomorphic_multiply(self):
        engine = BFVEngine(poly_degree=64, coeff_modulus=2**20 + 7, plain_modulus=257, seed=42)
        engine.generate_keys()
        ct1 = engine.encrypt(3)
        ct2 = engine.encrypt(5)
        ct_prod = engine.multiply(ct1, ct2)
        assert ct_prod.noise_budget_bits > 0

    def test_add_plain(self):
        engine = BFVEngine(poly_degree=64, seed=42)
        engine.generate_keys()
        ct = engine.encrypt(10)
        ct2 = engine.add_plain(ct, 5)
        assert ct2.noise_budget_bits > 0

    def test_noise_budget_decreases_after_multiply(self):
        engine = BFVEngine(poly_degree=64, coeff_modulus=2**20 + 7, plain_modulus=257, seed=42)
        engine.generate_keys()
        ct1 = engine.encrypt(3)
        ct2 = engine.encrypt(5)
        initial_budget = min(ct1.noise_budget_bits, ct2.noise_budget_bits)
        ct_prod = engine.multiply(ct1, ct2)
        assert ct_prod.noise_budget_bits < initial_budget


# ============================================================
# Engine Tests
# ============================================================


class TestHomomorphicFizzBuzzEngine:
    def test_evaluate_fizzbuzz(self):
        engine = HomomorphicFizzBuzzEngine(seed=42)
        result = engine.evaluate(15)
        assert result["result"] == "FizzBuzz"
        assert result["round_trip_valid"] is True

    def test_evaluate_fizz(self):
        engine = HomomorphicFizzBuzzEngine(seed=42)
        result = engine.evaluate(9)
        assert result["result"] == "Fizz"

    def test_evaluate_buzz(self):
        engine = HomomorphicFizzBuzzEngine(seed=42)
        result = engine.evaluate(10)
        assert result["result"] == "Buzz"

    def test_evaluate_plain(self):
        engine = HomomorphicFizzBuzzEngine(seed=42)
        result = engine.evaluate(7)
        assert result["result"] == "7"


# ============================================================
# Middleware Tests
# ============================================================


class TestFizzHomomorphicMiddleware:
    def test_middleware_annotates_context(self):
        mw = FizzHomomorphicMiddleware(seed=42)
        ctx = _make_context(15)
        called = []
        mw.process(ctx, lambda c: called.append(True))
        assert called
        assert ctx.metadata["he_result"] == "FizzBuzz"
        assert ctx.metadata["he_round_trip_valid"] is True
        assert "he_ciphertext_id" in ctx.metadata

    def test_middleware_plain_number(self):
        mw = FizzHomomorphicMiddleware(seed=42)
        ctx = _make_context(7)
        mw.process(ctx, lambda c: None)
        assert ctx.metadata["he_result"] == "7"
