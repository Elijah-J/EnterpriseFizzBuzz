"""
Enterprise FizzBuzz Platform - FizzCryptanalysis Cipher Breaking Engine Test Suite

Comprehensive verification of the cryptanalytic pipeline, from frequency
analysis through differential cryptanalysis of SPN ciphers. A failure
in cipher breaking would leave FizzBuzz output encrypted and unverifiable,
violating the platform's transparency SLA.
"""

from __future__ import annotations

import math
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzcryptanalysis import (
    ENGLISH_FREQUENCIES,
    ENGLISH_IOC,
    MIN_FREQUENCY_ANALYSIS_LENGTH,
    RANDOM_IOC,
    SBOX_4BIT,
    SBOX_4BIT_INV,
    TRIGRAM_MIN_LENGTH,
    CipherType,
    CryptanalysisEngine,
    CryptanalysisMiddleware,
    CryptanalysisReport,
    DifferentialAnalyzer,
    DifferentialTrail,
    FrequencyAnalyzer,
    FrequencyProfile,
    KasiskiExaminer,
    KasiskiResult,
    KnownPlaintextAttacker,
    classify_by_ioc,
    index_of_coincidence,
)
from enterprise_fizzbuzz.domain.exceptions.fizzcryptanalysis import (
    CipherIdentificationError,
    CryptanalysisMiddlewareError,
    DifferentialCryptanalysisError,
    FizzCryptanalysisError,
    FrequencyAnalysisError,
    IndexOfCoincidenceError,
    KasiskiError,
    KnownPlaintextError,
)
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
)


# ===========================================================================
# Helpers
# ===========================================================================

def _make_context(number: int, output: str = "", is_fizz: bool = False, is_buzz: bool = False):
    ctx = ProcessingContext(number=number, session_id=str(uuid.uuid4()))
    result = FizzBuzzResult(number=number, output=output or str(number), matched_rules=[])
    result._is_fizz = is_fizz
    result._is_buzz = is_buzz
    ctx.results.append(result)
    return ctx


SAMPLE_ENGLISH = (
    "The quick brown fox jumps over the lazy dog and then proceeds to "
    "evaluate a fizzbuzz sequence with remarkable enthusiasm and vigor "
    "the enterprise platform has been carefully designed to handle all "
    "possible edge cases including numbers divisible by three and five "
    "the implementation follows clean architecture principles with a "
    "strict dependency rule that ensures infrastructure depends on the "
    "domain layer and never the other way around this separation of "
    "concerns enables independent testing and deployment of each layer"
)


# ===========================================================================
# Frequency Analyzer Tests
# ===========================================================================

class TestFrequencyAnalyzer:
    """Verification of letter frequency analysis."""

    def test_analyze_returns_profile(self):
        fa = FrequencyAnalyzer()
        profile = fa.analyze(SAMPLE_ENGLISH)
        assert profile.total > 0
        assert "E" in profile.counts or "e" in profile.counts

    def test_analyze_short_text_raises(self):
        fa = FrequencyAnalyzer()
        with pytest.raises(FrequencyAnalysisError):
            fa.analyze("abc")

    def test_caesar_shift_identity(self):
        fa = FrequencyAnalyzer()
        assert fa.caesar_shift("ABC", 0) == "ABC"

    def test_caesar_shift_by_one(self):
        fa = FrequencyAnalyzer()
        assert fa.caesar_shift("ABC", 1) == "BCD"

    def test_caesar_shift_wraps(self):
        fa = FrequencyAnalyzer()
        assert fa.caesar_shift("Z", 1) == "A"

    def test_break_caesar_recovers_shift(self):
        fa = FrequencyAnalyzer()
        plaintext = SAMPLE_ENGLISH
        encrypted = fa.caesar_shift(plaintext, 3)
        shift, _ = fa.break_caesar(encrypted)
        assert shift == 3


# ===========================================================================
# Index of Coincidence Tests
# ===========================================================================

class TestIndexOfCoincidence:
    """Verification of index of coincidence computation."""

    def test_english_ioc_near_expected(self):
        ioc = index_of_coincidence(SAMPLE_ENGLISH)
        assert abs(ioc - ENGLISH_IOC) < 0.02

    def test_uniform_ioc_lower(self):
        # A text with perfectly uniform distribution has lower IOC
        uniform = "ABCDEFGHIJKLMNOPQRSTUVWXYZ" * 10
        ioc = index_of_coincidence(uniform)
        assert ioc < ENGLISH_IOC

    def test_empty_text_returns_zero(self):
        ioc = index_of_coincidence("")
        assert ioc == 0.0

    def test_classify_monoalphabetic(self):
        ct = classify_by_ioc(0.067)
        assert ct == CipherType.MONOALPHABETIC


# ===========================================================================
# Kasiski Examination Tests
# ===========================================================================

class TestKasiskiExaminer:
    """Verification of the Kasiski examination."""

    def test_short_text_raises(self):
        ke = KasiskiExaminer()
        with pytest.raises(KasiskiError):
            ke.examine("abc")

    def test_repeated_trigrams_detected(self):
        # Vigenere with key "KEY" encrypting repeated text
        text = "THEQUICKBROWNFOXJUMPSOVERTHEQUICKBROWNFOX"
        ke = KasiskiExaminer()
        result = ke.examine(text)
        assert len(result.repeated_trigrams) > 0

    def test_key_length_positive(self):
        text = "ABCDEFABCDEFABCDEFABCDEFABCDEFABCDEF"
        ke = KasiskiExaminer()
        result = ke.examine(text)
        assert result.probable_key_length >= 1


# ===========================================================================
# Known-Plaintext Attack Tests
# ===========================================================================

class TestKnownPlaintextAttacker:
    """Verification of known-plaintext attack capability."""

    def test_recover_mapping(self):
        kpa = KnownPlaintextAttacker()
        mapping = kpa.attack("ABC", "DEF")
        assert mapping["D"] == "A"
        assert mapping["E"] == "B"
        assert mapping["F"] == "C"

    def test_apply_mapping(self):
        kpa = KnownPlaintextAttacker()
        mapping = {"D": "A", "E": "B", "F": "C"}
        result = kpa.apply_mapping("DEF", mapping)
        assert result == "ABC"

    def test_contradiction_raises(self):
        kpa = KnownPlaintextAttacker()
        with pytest.raises(KnownPlaintextError):
            kpa.attack("AB", "AA")  # A maps to both A and B


# ===========================================================================
# Differential Cryptanalysis Tests
# ===========================================================================

class TestDifferentialAnalyzer:
    """Verification of differential cryptanalysis."""

    def test_ddt_dimensions(self):
        da = DifferentialAnalyzer()
        assert len(da.ddt) == 16
        assert len(da.ddt[0]) == 16

    def test_ddt_row_sums_correct(self):
        da = DifferentialAnalyzer()
        for row in da.ddt:
            assert sum(row) == 16

    def test_best_differential_found(self):
        da = DifferentialAnalyzer()
        trail = da.best_differential()
        assert trail.probability > 0.0
        assert trail.input_diff > 0

    def test_max_probability_positive(self):
        da = DifferentialAnalyzer()
        assert da.max_probability() > 0.0

    def test_sbox_invertible(self):
        for i in range(16):
            assert SBOX_4BIT_INV[SBOX_4BIT[i]] == i


# ===========================================================================
# Cryptanalysis Engine Tests
# ===========================================================================

class TestCryptanalysisEngine:
    """Verification of the integrated cryptanalysis engine."""

    def test_encrypt_fizzbuzz(self):
        engine = CryptanalysisEngine()
        encrypted = engine.encrypt_fizzbuzz("FizzBuzz", 3)
        assert encrypted != "FizzBuzz"

    def test_analyze_returns_report(self):
        engine = CryptanalysisEngine()
        encrypted = engine.encrypt_fizzbuzz(SAMPLE_ENGLISH, 5)
        report = engine.analyze(encrypted)
        assert isinstance(report, CryptanalysisReport)
        assert report.ioc > 0.0


# ===========================================================================
# Middleware Tests
# ===========================================================================

class TestCryptanalysisMiddleware:
    """Verification of the FizzCryptanalysis middleware integration."""

    def test_middleware_name(self):
        mw = CryptanalysisMiddleware()
        assert mw.get_name() == "CryptanalysisMiddleware"

    def test_middleware_priority(self):
        mw = CryptanalysisMiddleware()
        assert mw.get_priority() == 289

    def test_middleware_attaches_metadata(self):
        mw = CryptanalysisMiddleware()
        ctx = _make_context(3, "Fizz", is_fizz=True)
        result = mw.process(ctx, lambda c: c)
        assert "crypto_cipher_type" in result.metadata

    def test_middleware_increments_evaluations(self):
        mw = CryptanalysisMiddleware()
        ctx = _make_context(1, "1")
        mw.process(ctx, lambda c: c)
        assert mw.evaluations == 1
