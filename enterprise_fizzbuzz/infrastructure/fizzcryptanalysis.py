"""
Enterprise FizzBuzz Platform - FizzCryptanalysis: Cipher Breaking Engine

Implements frequency analysis, the Kasiski examination, index of
coincidence computation, known-plaintext attacks, and differential
cryptanalysis for encrypted FizzBuzz output streams.

The FizzBuzz evaluation pipeline produces output strings that may be
intercepted by adversaries. To verify the integrity of encrypted
FizzBuzz transmissions, this module provides a suite of classical
and modern cryptanalytic tools that can recover plaintext from
ciphertext under various threat models.

Frequency analysis exploits the non-uniform letter distribution
inherent in FizzBuzz output (the letters F, I, Z, B, U appear with
specific frequencies determined by the divisibility pattern). The
Kasiski examination identifies polyalphabetic key lengths from
repeated trigrams. The index of coincidence distinguishes
monoalphabetic from polyalphabetic ciphers.

For block ciphers, differential cryptanalysis tracks the propagation
of XOR differences through substitution-permutation networks. The
engine maintains a differential trail probability table and
identifies high-probability characteristics that can be exploited
to recover round keys.

Physical justification: Ensuring that FizzBuzz output can be
securely transmitted requires periodic red-team exercises. The
cryptanalysis engine provides automated penetration testing against
the platform's encryption layer.
"""

from __future__ import annotations

import logging
import math
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ENGLISH_FREQUENCIES: dict[str, float] = {
    "A": 0.0817, "B": 0.0150, "C": 0.0278, "D": 0.0425,
    "E": 0.1270, "F": 0.0223, "G": 0.0202, "H": 0.0609,
    "I": 0.0697, "J": 0.0015, "K": 0.0077, "L": 0.0403,
    "M": 0.0241, "N": 0.0675, "O": 0.0751, "P": 0.0193,
    "Q": 0.0010, "R": 0.0599, "S": 0.0633, "T": 0.0906,
    "U": 0.0276, "V": 0.0098, "W": 0.0236, "X": 0.0015,
    "Y": 0.0197, "Z": 0.0007,
}

ENGLISH_IOC = 0.0667  # index of coincidence for English
RANDOM_IOC = 0.0385  # index of coincidence for uniform random
MIN_FREQUENCY_ANALYSIS_LENGTH = 50
TRIGRAM_MIN_LENGTH = 30
IOC_TOLERANCE = 0.005

# SPN (substitution-permutation network) parameters for differential analysis
SBOX_4BIT = [0xE, 0x4, 0xD, 0x1, 0x2, 0xF, 0xB, 0x8,
             0x3, 0xA, 0x6, 0xC, 0x5, 0x9, 0x0, 0x7]
SBOX_4BIT_INV = [0] * 16


def _init_sbox_inv() -> None:
    for i, v in enumerate(SBOX_4BIT):
        SBOX_4BIT_INV[v] = i

_init_sbox_inv()


# ---------------------------------------------------------------------------
# Cipher type classification
# ---------------------------------------------------------------------------

class CipherType(Enum):
    """Classification of cipher systems."""
    CAESAR = auto()
    MONOALPHABETIC = auto()
    VIGENERE = auto()
    PLAYFAIR = auto()
    TRANSPOSITION = auto()
    SPN = auto()
    UNKNOWN = auto()


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class FrequencyProfile:
    """Letter frequency distribution for a text."""
    counts: dict[str, int] = field(default_factory=dict)
    total: int = 0

    def frequency(self, letter: str) -> float:
        if self.total == 0:
            return 0.0
        return self.counts.get(letter.upper(), 0) / self.total

    def chi_squared(self, expected: dict[str, float]) -> float:
        """Chi-squared statistic against an expected frequency distribution."""
        chi2 = 0.0
        for letter, exp_freq in expected.items():
            observed = self.counts.get(letter, 0)
            expected_count = exp_freq * self.total
            if expected_count > 0:
                chi2 += (observed - expected_count) ** 2 / expected_count
        return chi2


@dataclass
class KasiskiResult:
    """Result of a Kasiski examination."""
    repeated_trigrams: dict[str, list[int]] = field(default_factory=dict)
    spacings: list[int] = field(default_factory=list)
    probable_key_length: int = 0


@dataclass
class DifferentialTrail:
    """A differential trail through an SPN cipher."""
    input_diff: int
    output_diff: int
    probability: float
    round_diffs: list[tuple[int, int]] = field(default_factory=list)

    @property
    def num_rounds(self) -> int:
        return len(self.round_diffs)


@dataclass
class CryptanalysisReport:
    """Complete cryptanalysis report for a ciphertext."""
    cipher_type: CipherType = CipherType.UNKNOWN
    ioc: float = 0.0
    probable_key_length: int = 0
    recovered_key: Optional[str] = None
    decrypted_sample: Optional[str] = None
    confidence: float = 0.0


# ---------------------------------------------------------------------------
# Frequency analyzer
# ---------------------------------------------------------------------------

class FrequencyAnalyzer:
    """Computes letter frequency distributions and identifies cipher types.

    Analyzes the statistical properties of ciphertext to determine
    whether it was produced by a monoalphabetic or polyalphabetic
    substitution cipher. The chi-squared test against known language
    frequencies provides a confidence measure.
    """

    def analyze(self, text: str) -> FrequencyProfile:
        """Compute the letter frequency profile of a text."""
        from enterprise_fizzbuzz.domain.exceptions.fizzcryptanalysis import (
            FrequencyAnalysisError,
        )

        alpha_only = [c.upper() for c in text if c.isalpha()]
        if len(alpha_only) < MIN_FREQUENCY_ANALYSIS_LENGTH:
            raise FrequencyAnalysisError(len(alpha_only), MIN_FREQUENCY_ANALYSIS_LENGTH)

        counts = Counter(alpha_only)
        return FrequencyProfile(counts=dict(counts), total=len(alpha_only))

    def caesar_shift(self, text: str, shift: int) -> str:
        """Apply a Caesar cipher shift to the text."""
        result = []
        for c in text:
            if c.isalpha():
                base = ord("A") if c.isupper() else ord("a")
                shifted = chr((ord(c) - base + shift) % 26 + base)
                result.append(shifted)
            else:
                result.append(c)
        return "".join(result)

    def break_caesar(self, ciphertext: str) -> tuple[int, str]:
        """Break a Caesar cipher by trying all 26 shifts.

        Returns the (shift, plaintext) pair with the lowest chi-squared
        statistic against English frequencies.
        """
        best_shift = 0
        best_chi2 = float("inf")
        best_plain = ciphertext

        for shift in range(26):
            candidate = self.caesar_shift(ciphertext, -shift)
            alpha = [c.upper() for c in candidate if c.isalpha()]
            if not alpha:
                continue
            counts = Counter(alpha)
            profile = FrequencyProfile(counts=dict(counts), total=len(alpha))
            chi2 = profile.chi_squared(ENGLISH_FREQUENCIES)
            if chi2 < best_chi2:
                best_chi2 = chi2
                best_shift = shift
                best_plain = candidate

        return best_shift, best_plain


# ---------------------------------------------------------------------------
# Kasiski examination
# ---------------------------------------------------------------------------

class KasiskiExaminer:
    """Performs the Kasiski examination to determine polyalphabetic key length.

    Identifies repeated trigrams in the ciphertext and computes the GCD
    of their spacings, which is likely to be the key length (or a
    multiple thereof).
    """

    def examine(self, ciphertext: str) -> KasiskiResult:
        """Perform the Kasiski examination on a ciphertext."""
        from enterprise_fizzbuzz.domain.exceptions.fizzcryptanalysis import KasiskiError

        clean = "".join(c.upper() for c in ciphertext if c.isalpha())

        if len(clean) < TRIGRAM_MIN_LENGTH:
            raise KasiskiError(len(clean))

        # Find repeated trigrams
        trigram_positions: dict[str, list[int]] = {}
        for i in range(len(clean) - 2):
            tri = clean[i:i + 3]
            if tri not in trigram_positions:
                trigram_positions[tri] = []
            trigram_positions[tri].append(i)

        repeated = {
            tri: positions
            for tri, positions in trigram_positions.items()
            if len(positions) > 1
        }

        if not repeated:
            raise KasiskiError(len(clean))

        # Compute spacings
        spacings = []
        for positions in repeated.values():
            for i in range(len(positions)):
                for j in range(i + 1, len(positions)):
                    spacings.append(positions[j] - positions[i])

        # GCD of all spacings
        if spacings:
            g = spacings[0]
            for s in spacings[1:]:
                g = math.gcd(g, s)
            key_length = max(g, 1)
        else:
            key_length = 1

        return KasiskiResult(
            repeated_trigrams=repeated,
            spacings=spacings,
            probable_key_length=key_length,
        )


# ---------------------------------------------------------------------------
# Index of coincidence
# ---------------------------------------------------------------------------

def index_of_coincidence(text: str) -> float:
    """Compute the index of coincidence for a text.

    IC = sum(n_i * (n_i - 1)) / (N * (N - 1))

    where n_i is the count of the i-th letter and N is the total
    number of letters.
    """
    clean = [c.upper() for c in text if c.isalpha()]
    n = len(clean)
    if n < 2:
        return 0.0

    counts = Counter(clean)
    numerator = sum(c * (c - 1) for c in counts.values())
    denominator = n * (n - 1)
    return numerator / denominator


def classify_by_ioc(ioc_value: float) -> CipherType:
    """Classify the cipher type based on the index of coincidence.

    IC near 0.0667 suggests monoalphabetic substitution.
    IC near 0.0385 suggests polyalphabetic or transposition.
    """
    if abs(ioc_value - ENGLISH_IOC) < IOC_TOLERANCE:
        return CipherType.MONOALPHABETIC
    elif ioc_value < RANDOM_IOC + IOC_TOLERANCE:
        return CipherType.VIGENERE  # polyalphabetic
    else:
        return CipherType.UNKNOWN


# ---------------------------------------------------------------------------
# Known-plaintext attack
# ---------------------------------------------------------------------------

class KnownPlaintextAttacker:
    """Recovers substitution cipher keys from known plaintext-ciphertext pairs.

    Given a known segment of plaintext and its corresponding ciphertext,
    deduces the substitution mapping. For polyalphabetic ciphers, this
    requires multiple known segments at different key positions.
    """

    def attack(
        self,
        plaintext: str,
        ciphertext: str,
    ) -> dict[str, str]:
        """Recover the substitution mapping from a known pair.

        Returns a dict mapping ciphertext letters to plaintext letters.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzcryptanalysis import (
            KnownPlaintextError,
        )

        p_alpha = [c.upper() for c in plaintext if c.isalpha()]
        c_alpha = [c.upper() for c in ciphertext if c.isalpha()]

        if len(p_alpha) != len(c_alpha):
            raise KnownPlaintextError(
                len(p_alpha),
                26,
            )

        mapping: dict[str, str] = {}
        for p, c in zip(p_alpha, c_alpha):
            if c in mapping and mapping[c] != p:
                # Contradiction — not a simple substitution
                raise KnownPlaintextError(len(p_alpha), 26)
            mapping[c] = p

        return mapping

    def apply_mapping(self, ciphertext: str, mapping: dict[str, str]) -> str:
        """Apply a substitution mapping to decrypt ciphertext."""
        result = []
        for c in ciphertext:
            if c.upper() in mapping:
                decrypted = mapping[c.upper()]
                result.append(decrypted.lower() if c.islower() else decrypted)
            else:
                result.append(c)
        return "".join(result)


# ---------------------------------------------------------------------------
# Differential cryptanalysis (simplified SPN)
# ---------------------------------------------------------------------------

class DifferentialAnalyzer:
    """Performs differential cryptanalysis on a simplified SPN cipher.

    The target cipher is a 4-bit SPN with a known S-box. The analyzer
    computes the difference distribution table (DDT) and identifies
    high-probability differential trails that can be used to recover
    round keys.
    """

    def __init__(self, sbox: Optional[list[int]] = None) -> None:
        self.sbox = sbox or SBOX_4BIT
        self.sbox_size = len(self.sbox)
        self.ddt = self._compute_ddt()

    def _compute_ddt(self) -> list[list[int]]:
        """Compute the difference distribution table for the S-box.

        DDT[dx][dy] = number of input pairs with XOR difference dx
        that produce output XOR difference dy.
        """
        n = self.sbox_size
        ddt = [[0] * n for _ in range(n)]
        for x in range(n):
            for dx in range(n):
                x_prime = x ^ dx
                dy = self.sbox[x] ^ self.sbox[x_prime]
                ddt[dx][dy] += 1
        return ddt

    def best_differential(self) -> DifferentialTrail:
        """Find the highest-probability single-round differential.

        Excludes the trivial (0, 0) differential.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzcryptanalysis import (
            DifferentialCryptanalysisError,
        )

        n = self.sbox_size
        best_prob = 0.0
        best_dx = 0
        best_dy = 0

        for dx in range(1, n):
            for dy in range(n):
                prob = self.ddt[dx][dy] / n
                if prob > best_prob:
                    best_prob = prob
                    best_dx = dx
                    best_dy = dy

        if best_prob < 1.0 / n:
            raise DifferentialCryptanalysisError(1, best_prob)

        return DifferentialTrail(
            input_diff=best_dx,
            output_diff=best_dy,
            probability=best_prob,
            round_diffs=[(best_dx, best_dy)],
        )

    def max_probability(self) -> float:
        """Return the maximum non-trivial differential probability."""
        n = self.sbox_size
        max_p = 0.0
        for dx in range(1, n):
            for dy in range(n):
                p = self.ddt[dx][dy] / n
                if p > max_p:
                    max_p = p
        return max_p


# ---------------------------------------------------------------------------
# Cryptanalysis engine (composition root)
# ---------------------------------------------------------------------------

class CryptanalysisEngine:
    """Integrates all cryptanalytic tools into a unified analysis engine.

    Given FizzBuzz output that has been encrypted, the engine determines
    the cipher type, estimates key parameters, and attempts decryption.
    """

    def __init__(self) -> None:
        self.freq_analyzer = FrequencyAnalyzer()
        self.kasiski = KasiskiExaminer()
        self.kpa = KnownPlaintextAttacker()
        self.differential = DifferentialAnalyzer()
        self._reports: list[CryptanalysisReport] = []

    def analyze(self, ciphertext: str) -> CryptanalysisReport:
        """Perform full cryptanalysis on a ciphertext."""
        report = CryptanalysisReport()

        # Step 1: Index of coincidence
        ioc = index_of_coincidence(ciphertext)
        report.ioc = ioc
        report.cipher_type = classify_by_ioc(ioc)

        # Step 2: Kasiski examination (if polyalphabetic)
        if report.cipher_type == CipherType.VIGENERE:
            try:
                kasiski_result = self.kasiski.examine(ciphertext)
                report.probable_key_length = kasiski_result.probable_key_length
            except Exception:
                pass

        # Step 3: Attempt Caesar break (simplest case)
        if report.cipher_type == CipherType.MONOALPHABETIC:
            try:
                shift, plaintext = self.freq_analyzer.break_caesar(ciphertext)
                report.recovered_key = str(shift)
                report.decrypted_sample = plaintext[:50]
                report.confidence = 0.8
            except Exception:
                pass

        self._reports.append(report)
        return report

    def encrypt_fizzbuzz(self, output: str, number: int) -> str:
        """Encrypt a FizzBuzz output string using a number-derived key.

        This simulates the encryption that the cryptanalysis engine
        is designed to break. The cipher is a simple Caesar shift
        keyed by the number modulo 26.
        """
        shift = number % 26
        return self.freq_analyzer.caesar_shift(output, shift)

    @property
    def reports(self) -> list[CryptanalysisReport]:
        return list(self._reports)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class CryptanalysisMiddleware(IMiddleware):
    """Middleware that performs cryptanalysis on FizzBuzz output strings.

    Each evaluation's output is encrypted with a number-derived key
    and then subjected to automated cryptanalysis. The engine attempts
    to recover the original output, providing a continuous
    red-team validation of the platform's encryption resilience.

    Priority 289 positions this in the security analysis tier.
    """

    def __init__(self) -> None:
        self._engine = CryptanalysisEngine()
        self._evaluations = 0
        self._successful_breaks = 0

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        result = next_handler(context)

        number = context.number
        output_str = ""
        if result.results:
            output_str = result.results[-1].output

        try:
            # Encrypt then attempt to break
            encrypted = self._engine.encrypt_fizzbuzz(output_str, number)
            report = self._engine.analyze(encrypted)
            self._evaluations += 1

            if report.confidence > 0.5:
                self._successful_breaks += 1

            result.metadata["crypto_cipher_type"] = report.cipher_type.name
            result.metadata["crypto_ioc"] = report.ioc
            result.metadata["crypto_confidence"] = report.confidence
            result.metadata["crypto_key_length"] = report.probable_key_length
        except Exception as e:
            logger.warning("Cryptanalysis failed for number %d: %s", number, e)
            result.metadata["crypto_error"] = str(e)

        return result

    def get_name(self) -> str:
        return "CryptanalysisMiddleware"

    def get_priority(self) -> int:
        return 289

    @property
    def engine(self) -> CryptanalysisEngine:
        return self._engine

    @property
    def evaluations(self) -> int:
        return self._evaluations

    @property
    def successful_breaks(self) -> int:
        return self._successful_breaks
