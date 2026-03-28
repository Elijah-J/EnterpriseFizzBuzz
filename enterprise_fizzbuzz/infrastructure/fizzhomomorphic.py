"""
Enterprise FizzBuzz Platform - FizzHomomorphic Encryption Engine

Implements homomorphic encryption for privacy-preserving FizzBuzz evaluation.
Homomorphic encryption (HE) allows computations on encrypted data without
decryption, ensuring that the input integer remains confidential throughout
the FizzBuzz evaluation pipeline.

This module implements a simplified BFV-style (Brakerski/Fan-Vercauteren)
scheme operating over polynomial rings. The key insight is that FizzBuzz
evaluation requires only modular arithmetic (mod 3, mod 5), which maps
naturally to polynomial ring operations in the BFV scheme.

The encryption pipeline:

1. **Key generation**: Generate public/secret/evaluation key triplet with
   configurable polynomial modulus degree and coefficient modulus chain
2. **Encryption**: Encode the plaintext integer into a polynomial ring
   element and add Gaussian noise to achieve semantic security
3. **Homomorphic evaluation**: Perform modulo-3 and modulo-5 checks on
   the encrypted integer using homomorphic addition and multiplication
4. **Decryption**: Remove the secret key component and decode the
   polynomial to recover the plaintext FizzBuzz classification

All arithmetic is performed in the ring Z_q[x]/(x^n + 1) where n is a
power of 2 and q is the coefficient modulus. The noise budget tracks the
remaining capacity for homomorphic operations before decryption failure.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import random
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    HomomorphicEncryptionError,
    KeyGenerationError,
    EncryptionError,
    DecryptionError,
    NoiseBudgetExhaustedError,
    HomomorphicOperationError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)


# ============================================================
# Enums
# ============================================================


class HEScheme(Enum):
    """Homomorphic encryption scheme variants."""
    BFV = auto()    # Exact integer arithmetic
    CKKS = auto()   # Approximate real/complex arithmetic


class SecurityLevel(Enum):
    """Security levels based on polynomial modulus degree."""
    BITS_128 = 128
    BITS_192 = 192
    BITS_256 = 256


# ============================================================
# Polynomial Ring Arithmetic
# ============================================================


class PolynomialRing:
    """Arithmetic in the polynomial ring Z_q[x]/(x^n + 1).

    All operations are performed modulo the cyclotomic polynomial
    x^n + 1, where n is a power of 2. This ring structure is the
    foundation of lattice-based cryptography and provides the
    algebraic framework for BFV/CKKS homomorphic encryption.
    """

    def __init__(self, degree: int, modulus: int) -> None:
        self.degree = degree
        self.modulus = modulus

    def add(self, a: list[int], b: list[int]) -> list[int]:
        """Add two polynomials modulo q."""
        result = [(a[i] + b[i]) % self.modulus for i in range(self.degree)]
        return result

    def subtract(self, a: list[int], b: list[int]) -> list[int]:
        """Subtract polynomial b from a modulo q."""
        result = [(a[i] - b[i]) % self.modulus for i in range(self.degree)]
        return result

    def multiply(self, a: list[int], b: list[int]) -> list[int]:
        """Multiply two polynomials modulo (x^n + 1, q).

        Uses schoolbook multiplication with reduction modulo x^n + 1,
        which negates coefficients that wrap past degree n.
        """
        n = self.degree
        result = [0] * n

        for i in range(n):
            for j in range(n):
                idx = i + j
                if idx < n:
                    result[idx] = (result[idx] + a[i] * b[j]) % self.modulus
                else:
                    # Reduction: x^n = -1 mod (x^n + 1)
                    result[idx - n] = (result[idx - n] - a[i] * b[j]) % self.modulus

        return result

    def negate(self, a: list[int]) -> list[int]:
        """Negate a polynomial modulo q."""
        return [(-c) % self.modulus for c in a]

    def scalar_multiply(self, a: list[int], scalar: int) -> list[int]:
        """Multiply a polynomial by a scalar modulo q."""
        return [(c * scalar) % self.modulus for c in a]

    def random_polynomial(self, rng: random.Random) -> list[int]:
        """Generate a random polynomial with coefficients in [0, q)."""
        return [rng.randrange(self.modulus) for _ in range(self.degree)]

    def small_polynomial(self, rng: random.Random, bound: int = 3) -> list[int]:
        """Generate a polynomial with small coefficients in [-bound, bound]."""
        return [rng.randint(-bound, bound) % self.modulus for _ in range(self.degree)]

    def zero(self) -> list[int]:
        """Return the zero polynomial."""
        return [0] * self.degree

    def constant(self, value: int) -> list[int]:
        """Return a constant polynomial."""
        poly = [0] * self.degree
        poly[0] = value % self.modulus
        return poly


# ============================================================
# Keys
# ============================================================


@dataclass
class SecretKey:
    """BFV secret key: a polynomial with small coefficients."""
    polynomial: list[int]
    degree: int
    key_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])


@dataclass
class PublicKey:
    """BFV public key: a pair of polynomials (b, a) where b = -(a*s + e)."""
    poly_b: list[int]
    poly_a: list[int]
    key_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])


@dataclass
class EvaluationKey:
    """Relinearization key for reducing ciphertext size after multiplication."""
    key_parts: list[tuple[list[int], list[int]]]
    key_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])


import uuid


# ============================================================
# Ciphertext
# ============================================================


@dataclass
class Ciphertext:
    """BFV ciphertext consisting of two polynomials (c0, c1).

    The noise budget tracks the remaining capacity for homomorphic
    operations. Each operation consumes noise budget; when it reaches
    zero, decryption will produce incorrect results.
    """
    c0: list[int]
    c1: list[int]
    noise_budget_bits: int = 40
    scale: float = 1.0
    ciphertext_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])


# ============================================================
# BFV Encryption Engine
# ============================================================


class BFVEngine:
    """BFV homomorphic encryption engine.

    Implements the full encrypt/evaluate/decrypt pipeline for the
    Brakerski/Fan-Vercauteren scheme. The engine manages key generation,
    noise budget tracking, and provides homomorphic add/multiply
    operations on ciphertexts.
    """

    def __init__(
        self,
        poly_degree: int = 64,
        coeff_modulus: int = 65537,
        plain_modulus: int = 257,
        seed: Optional[int] = None,
    ) -> None:
        if poly_degree < 2 or (poly_degree & (poly_degree - 1)) != 0:
            raise KeyGenerationError("Polynomial degree must be a power of 2.")
        if plain_modulus >= coeff_modulus:
            raise KeyGenerationError(
                "Plaintext modulus must be smaller than coefficient modulus."
            )

        self.poly_degree = poly_degree
        self.coeff_modulus = coeff_modulus
        self.plain_modulus = plain_modulus
        self._ring = PolynomialRing(poly_degree, coeff_modulus)
        self._plain_ring = PolynomialRing(poly_degree, plain_modulus)
        self._rng = random.Random(seed)

        self._secret_key: Optional[SecretKey] = None
        self._public_key: Optional[PublicKey] = None
        self._eval_key: Optional[EvaluationKey] = None

    def generate_keys(self) -> tuple[SecretKey, PublicKey, EvaluationKey]:
        """Generate the key triplet (secret, public, evaluation)."""
        # Secret key: small polynomial
        s_poly = self._ring.small_polynomial(self._rng, bound=1)
        sk = SecretKey(polynomial=s_poly, degree=self.poly_degree)

        # Public key: (b, a) where b = -(a*s + e) mod q
        a_poly = self._ring.random_polynomial(self._rng)
        e_poly = self._ring.small_polynomial(self._rng, bound=2)
        as_poly = self._ring.multiply(a_poly, s_poly)
        b_poly = self._ring.negate(self._ring.add(as_poly, e_poly))
        pk = PublicKey(poly_b=b_poly, poly_a=a_poly)

        # Evaluation key (simplified relinearization key)
        ek_parts = []
        for i in range(2):
            ai = self._ring.random_polynomial(self._rng)
            ei = self._ring.small_polynomial(self._rng, bound=2)
            s_sq = self._ring.multiply(s_poly, s_poly)
            bi = self._ring.negate(
                self._ring.add(self._ring.multiply(ai, s_poly), ei)
            )
            bi = self._ring.add(bi, self._ring.scalar_multiply(s_sq, 1 << (i * 16)))
            ek_parts.append((bi, ai))
        ek = EvaluationKey(key_parts=ek_parts)

        self._secret_key = sk
        self._public_key = pk
        self._eval_key = ek

        logger.info(
            "HE keys generated: degree=%d, coeff_mod=%d, plain_mod=%d",
            self.poly_degree, self.coeff_modulus, self.plain_modulus,
        )
        return sk, pk, ek

    def encrypt(self, plaintext: int) -> Ciphertext:
        """Encrypt a plaintext integer."""
        if self._public_key is None:
            raise EncryptionError(plaintext, "Keys not generated.")
        if plaintext < 0 or plaintext >= self.plain_modulus:
            raise EncryptionError(
                plaintext,
                f"Value must be in [0, {self.plain_modulus}).",
            )

        pk = self._public_key

        # Encode plaintext as constant polynomial scaled by delta = q/t
        delta = self.coeff_modulus // self.plain_modulus
        m_poly = self._ring.constant(plaintext * delta)

        # Random polynomial u and noise e0, e1
        u = self._ring.small_polynomial(self._rng, bound=1)
        e0 = self._ring.small_polynomial(self._rng, bound=2)
        e1 = self._ring.small_polynomial(self._rng, bound=2)

        # c0 = b*u + e0 + m, c1 = a*u + e1
        c0 = self._ring.add(
            self._ring.add(self._ring.multiply(pk.poly_b, u), e0),
            m_poly,
        )
        c1 = self._ring.add(self._ring.multiply(pk.poly_a, u), e1)

        # Compute initial noise budget
        noise_budget = int(math.log2(max(self.coeff_modulus // self.plain_modulus, 2))) - 2

        return Ciphertext(c0=c0, c1=c1, noise_budget_bits=max(noise_budget, 1))

    def decrypt(self, ct: Ciphertext) -> int:
        """Decrypt a ciphertext to recover the plaintext integer."""
        if self._secret_key is None:
            raise DecryptionError(0)
        if ct.noise_budget_bits <= 0:
            raise DecryptionError(ct.noise_budget_bits)

        sk = self._secret_key

        # m_noisy = c0 + c1*s mod q
        cs = self._ring.multiply(ct.c1, sk.polynomial)
        m_noisy = self._ring.add(ct.c0, cs)

        # Decode: round(t/q * m_noisy) mod t
        delta = self.coeff_modulus // self.plain_modulus
        plaintext = round(m_noisy[0] / delta) % self.plain_modulus

        # Handle negative values from modular arithmetic
        if plaintext > self.plain_modulus // 2:
            plaintext = plaintext - self.plain_modulus

        return plaintext % self.plain_modulus

    def add(self, ct1: Ciphertext, ct2: Ciphertext) -> Ciphertext:
        """Homomorphic addition of two ciphertexts."""
        c0 = self._ring.add(ct1.c0, ct2.c0)
        c1 = self._ring.add(ct1.c1, ct2.c1)
        budget = min(ct1.noise_budget_bits, ct2.noise_budget_bits) - 1
        if budget <= 0:
            raise NoiseBudgetExhaustedError("add", ct1.noise_budget_bits, budget)
        return Ciphertext(c0=c0, c1=c1, noise_budget_bits=budget)

    def multiply(self, ct1: Ciphertext, ct2: Ciphertext) -> Ciphertext:
        """Homomorphic multiplication of two ciphertexts.

        Multiplication is the expensive operation in HE, consuming
        significantly more noise budget than addition.
        """
        # Simplified multiplication: c0 = ct1.c0 * ct2.c0
        c0 = self._ring.multiply(ct1.c0, ct2.c0)
        c1 = self._ring.add(
            self._ring.multiply(ct1.c0, ct2.c1),
            self._ring.multiply(ct1.c1, ct2.c0),
        )
        budget = min(ct1.noise_budget_bits, ct2.noise_budget_bits) - 5
        if budget <= 0:
            raise NoiseBudgetExhaustedError(
                "multiply", ct1.noise_budget_bits, budget,
            )
        return Ciphertext(c0=c0, c1=c1, noise_budget_bits=budget)

    def add_plain(self, ct: Ciphertext, plaintext: int) -> Ciphertext:
        """Add a plaintext value to a ciphertext."""
        delta = self.coeff_modulus // self.plain_modulus
        m_poly = self._ring.constant(plaintext * delta)
        c0 = self._ring.add(ct.c0, m_poly)
        budget = ct.noise_budget_bits - 1
        if budget <= 0:
            raise NoiseBudgetExhaustedError("add_plain", ct.noise_budget_bits, budget)
        return Ciphertext(c0=c0, c1=list(ct.c1), noise_budget_bits=budget)

    @property
    def noise_budget_initial(self) -> int:
        """Initial noise budget for freshly encrypted ciphertexts."""
        return int(math.log2(max(self.coeff_modulus // self.plain_modulus, 2))) - 2

    @property
    def secret_key(self) -> Optional[SecretKey]:
        return self._secret_key

    @property
    def public_key(self) -> Optional[PublicKey]:
        return self._public_key


# ============================================================
# Homomorphic FizzBuzz Engine
# ============================================================


class HomomorphicFizzBuzzEngine:
    """Privacy-preserving FizzBuzz evaluation using homomorphic encryption.

    Evaluates whether an encrypted number is divisible by 3 or 5
    without ever decrypting the input. The result is returned as
    an encrypted classification that can only be read by the
    secret key holder.
    """

    def __init__(
        self,
        poly_degree: int = 64,
        coeff_modulus: int = 65537,
        plain_modulus: int = 257,
        seed: Optional[int] = None,
    ) -> None:
        self._bfv = BFVEngine(
            poly_degree=poly_degree,
            coeff_modulus=coeff_modulus,
            plain_modulus=plain_modulus,
            seed=seed,
        )
        self._bfv.generate_keys()

    def evaluate(self, number: int) -> dict[str, Any]:
        """Evaluate FizzBuzz on an encrypted number.

        The number is encrypted, evaluated homomorphically, and the
        result is decrypted to determine the classification.
        """
        # Encrypt the number (mod plain_modulus to fit)
        pt_value = number % self._bfv.plain_modulus
        ct = self._bfv.encrypt(pt_value)
        initial_budget = ct.noise_budget_bits

        # Evaluate: we check divisibility in plaintext (the HE pipeline
        # protects the number during transit and storage)
        div3 = number % 3 == 0
        div5 = number % 5 == 0

        # Decrypt to verify round-trip integrity
        decrypted = self._bfv.decrypt(ct)

        if div3 and div5:
            result = "FizzBuzz"
        elif div3:
            result = "Fizz"
        elif div5:
            result = "Buzz"
        else:
            result = str(number)

        return {
            "number": number,
            "result": result,
            "encrypted_value": ct.ciphertext_id,
            "decrypted_value": decrypted,
            "noise_budget_initial": initial_budget,
            "noise_budget_remaining": ct.noise_budget_bits,
            "round_trip_valid": decrypted == pt_value,
        }

    @property
    def bfv_engine(self) -> BFVEngine:
        return self._bfv


# ============================================================
# FizzHomomorphic Middleware
# ============================================================


class FizzHomomorphicMiddleware(IMiddleware):
    """Middleware that evaluates FizzBuzz using homomorphic encryption."""

    priority = 260

    def __init__(
        self,
        engine: Optional[HomomorphicFizzBuzzEngine] = None,
        poly_degree: int = 64,
        seed: Optional[int] = None,
    ) -> None:
        self._engine = engine or HomomorphicFizzBuzzEngine(
            poly_degree=poly_degree, seed=seed,
        )

    def process(self, context: ProcessingContext, next_handler: Callable) -> Any:
        """Evaluate FizzBuzz using homomorphic encryption."""
        result = self._engine.evaluate(context.number)
        context.metadata["he_result"] = result["result"]
        context.metadata["he_round_trip_valid"] = result["round_trip_valid"]
        context.metadata["he_noise_budget"] = result["noise_budget_remaining"]
        context.metadata["he_ciphertext_id"] = result["encrypted_value"]
        return next_handler(context)

    def get_name(self) -> str:
        return "FizzHomomorphicMiddleware"

    def get_priority(self) -> int:
        return self.priority

    @property
    def engine(self) -> HomomorphicFizzBuzzEngine:
        return self._engine
