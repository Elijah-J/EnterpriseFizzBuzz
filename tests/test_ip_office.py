"""
Enterprise FizzBuzz Platform - IP Office Test Suite

Comprehensive tests for the FizzBuzz Intellectual Property Office,
including phonetic similarity (Soundex + Metaphone), trademark
registration, patent examination, copyright registration, license
management, dispute resolution, and the IP dashboard. Because
protecting the intellectual property rights of "Fizz" is serious
business that demands serious testing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.ip_office import (
    CopyrightRegistry,
    CopyrightStatus,
    DisputeCase,
    DisputeVerdict,
    IPDisputeTribunal,
    IPOfficeDashboard,
    License,
    LicenseManager,
    LicenseType,
    PatentApplication,
    PatentExaminer,
    PatentStatus,
    PhoneticSimilarity,
    TrademarkApplication,
    TrademarkRegistry,
    TrademarkStatus,
    levenshtein_distance,
    levenshtein_similarity,
)
from enterprise_fizzbuzz.domain.exceptions import (
    CopyrightInfringementError,
    IPOfficeError,
    PatentInfringementError,
    TrademarkViolationError,
)


# ============================================================
# PhoneticSimilarity Tests
# ============================================================


class TestSoundex:
    """Tests for the Soundex algorithm implementation."""

    def test_empty_string(self):
        assert PhoneticSimilarity.soundex("") == "0000"

    def test_single_letter(self):
        assert PhoneticSimilarity.soundex("A") == "A000"

    def test_robert(self):
        assert PhoneticSimilarity.soundex("Robert") == "R163"

    def test_rupert(self):
        assert PhoneticSimilarity.soundex("Rupert") == "R163"

    def test_fizz(self):
        code = PhoneticSimilarity.soundex("Fizz")
        assert code[0] == "F"
        assert len(code) == 4

    def test_buzz(self):
        code = PhoneticSimilarity.soundex("Buzz")
        assert code[0] == "B"
        assert len(code) == 4

    def test_fizz_and_fhyzz_same_first_letter(self):
        """Fhyzz should have same Soundex first letter as Fizz."""
        code1 = PhoneticSimilarity.soundex("Fizz")
        code2 = PhoneticSimilarity.soundex("Fhyzz")
        assert code1[0] == code2[0]  # Both start with F

    def test_padding_to_four_chars(self):
        code = PhoneticSimilarity.soundex("Al")
        assert len(code) == 4

    def test_truncation_to_four_chars(self):
        code = PhoneticSimilarity.soundex("Schwarzenegger")
        assert len(code) == 4


class TestMetaphone:
    """Tests for the Metaphone algorithm implementation."""

    def test_empty_string(self):
        assert PhoneticSimilarity.metaphone("") == ""

    def test_ph_to_f(self):
        """PH should be encoded as F."""
        result = PhoneticSimilarity.metaphone("Phone")
        assert "F" in result

    def test_sh_to_x(self):
        """SH should be encoded as X."""
        result = PhoneticSimilarity.metaphone("Ship")
        assert "X" in result

    def test_silent_k_before_n(self):
        """K should be dropped before N."""
        result = PhoneticSimilarity.metaphone("Knight")
        assert result[0] == "N"

    def test_c_before_e(self):
        """C before E/I/Y should become S."""
        result = PhoneticSimilarity.metaphone("Cent")
        assert "S" in result

    def test_c_before_a(self):
        """C before A/O/U should become K."""
        result = PhoneticSimilarity.metaphone("Cat")
        assert "K" in result

    def test_fizz_encoding(self):
        result = PhoneticSimilarity.metaphone("Fizz")
        assert len(result) > 0

    def test_buzz_encoding(self):
        result = PhoneticSimilarity.metaphone("Buzz")
        assert len(result) > 0

    def test_initial_wr_drops_w(self):
        """WR at start should drop the W."""
        result = PhoneticSimilarity.metaphone("Write")
        assert result[0] == "R"

    def test_g_before_e(self):
        """G before E/I/Y should become J."""
        result = PhoneticSimilarity.metaphone("Gem")
        assert "J" in result


class TestPhoneticSimilarity:
    """Tests for the combined phonetic similarity scoring."""

    def test_identical_words(self):
        assert PhoneticSimilarity.similarity("Fizz", "Fizz") == 1.0

    def test_case_insensitive(self):
        assert PhoneticSimilarity.similarity("FIZZ", "fizz") == 1.0

    def test_empty_strings(self):
        assert PhoneticSimilarity.similarity("", "") == 0.0

    def test_one_empty(self):
        assert PhoneticSimilarity.similarity("Fizz", "") == 0.0

    def test_fhyzz_similar_to_fizz(self):
        """Fhyzz should be detected as confusingly similar to Fizz."""
        score = PhoneticSimilarity.similarity("Fhyzz", "Fizz")
        assert score >= 0.7, f"Expected >= 0.7, got {score}"

    def test_completely_different(self):
        score = PhoneticSimilarity.similarity("Abc", "Xyz")
        assert score < 0.5

    def test_buzz_vs_fuzz(self):
        score = PhoneticSimilarity.similarity("Buzz", "Fuzz")
        assert 0.0 < score < 1.0

    def test_symmetry(self):
        s1 = PhoneticSimilarity.similarity("Fizz", "Fuzz")
        s2 = PhoneticSimilarity.similarity("Fuzz", "Fizz")
        assert abs(s1 - s2) < 0.001


# ============================================================
# Levenshtein Distance Tests
# ============================================================


class TestLevenshtein:
    """Tests for Levenshtein distance and similarity."""

    def test_identical(self):
        assert levenshtein_distance("Fizz", "Fizz") == 0

    def test_one_insertion(self):
        assert levenshtein_distance("Fiz", "Fizz") == 1

    def test_one_deletion(self):
        assert levenshtein_distance("Fizz", "Fiz") == 1

    def test_one_substitution(self):
        assert levenshtein_distance("Fizz", "Fuzz") == 1

    def test_empty_strings(self):
        assert levenshtein_distance("", "") == 0

    def test_one_empty(self):
        assert levenshtein_distance("abc", "") == 3

    def test_similarity_identical(self):
        assert levenshtein_similarity("abc", "abc") == 0.0

    def test_similarity_completely_different(self):
        sim = levenshtein_similarity("abc", "xyz")
        assert sim == 1.0


# ============================================================
# TrademarkRegistry Tests
# ============================================================


class TestTrademarkRegistry:
    """Tests for the trademark registration system."""

    def test_canonical_marks_seeded(self):
        registry = TrademarkRegistry()
        fizz = registry.get("FIZZ")
        assert fizz is not None
        assert fizz.status == TrademarkStatus.REGISTERED

    def test_all_canonical_marks(self):
        registry = TrademarkRegistry()
        assert registry.get("BUZZ") is not None
        assert registry.get("FIZZBUZZ") is not None

    def test_apply_new_mark(self):
        registry = TrademarkRegistry()
        result = registry.apply("WUZZ", "Test Corp", "A new label")
        assert result.status == TrademarkStatus.REGISTERED

    def test_apply_conflicting_mark(self):
        """Applying for a mark similar to Fizz should be opposed."""
        registry = TrademarkRegistry()
        result = registry.apply("FHYZZ", "Evil Corp", "Confusingly similar to Fizz")
        assert result.status == TrademarkStatus.OPPOSED

    def test_apply_exact_duplicate(self):
        registry = TrademarkRegistry()
        result = registry.apply("FIZZ", "Competitor", "Exact copy")
        assert result.status == TrademarkStatus.OPPOSED

    def test_search_similar(self):
        registry = TrademarkRegistry()
        results = registry.search_similar("FIZZ")
        assert len(results) >= 1
        assert any(mark == "FIZZ" for mark, _ in results)

    def test_renew_trademark(self):
        registry = TrademarkRegistry()
        result = registry.renew("FIZZ")
        assert result is not None
        assert result.renewal_count >= 1

    def test_renew_nonexistent(self):
        registry = TrademarkRegistry()
        result = registry.renew("NONEXISTENT")
        assert result is None

    def test_all_marks(self):
        registry = TrademarkRegistry()
        marks = registry.all_marks
        assert len(marks) >= 3


# ============================================================
# PatentExaminer Tests
# ============================================================


class TestPatentExaminer:
    """Tests for the patent examination engine."""

    def test_prior_art_seeded(self):
        examiner = PatentExaminer()
        assert len(examiner.prior_art) >= 2

    def test_novel_patent_granted(self):
        examiner = PatentExaminer()
        result = examiner.examine(
            title="Method for divisibility by 11",
            description="A novel method for evaluating integers for divisibility by eleven, "
                        "producing the label 'Wham' for qualifying integers in enterprise contexts",
            divisor=11,
            label="Wham",
            inventor="Dr. Modulo",
        )
        assert result.status == PatentStatus.GRANTED

    def test_prior_art_rejection(self):
        """Filing a patent for divisor=3, label=Fizz should be rejected."""
        examiner = PatentExaminer()
        result = examiner.examine(
            title="Method for divisibility by 3",
            description="Short desc",
            divisor=3,
            label="Fizz",
        )
        assert result.status == PatentStatus.REJECTED

    def test_utility_check_valid(self):
        examiner = PatentExaminer()
        result = examiner.examine(
            title="Divisibility by 100",
            description="A method for checking if a number is divisible by one hundred with great ceremony",
            divisor=100,
            label="Centurion",
        )
        assert result.utility_score == 1.0

    def test_utility_check_zero_divisor(self):
        examiner = PatentExaminer()
        result = examiner.examine(
            title="Divisibility by 0",
            description="A method of dividing by zero which is inherently useless and mathematically undefined",
            divisor=0,
            label="Undefined",
        )
        assert result.utility_score == 0.0
        assert result.status == PatentStatus.REJECTED

    def test_patent_adds_to_prior_art(self):
        examiner = PatentExaminer()
        initial_count = len(examiner.prior_art)
        examiner.examine(
            title="Novel method",
            description="A truly unique and non-obvious method for FizzBuzz evaluation with unprecedented complexity",
            divisor=19,
            label="Zork",
        )
        assert len(examiner.prior_art) > initial_count

    def test_all_patents(self):
        examiner = PatentExaminer()
        examiner.examine("Test", "A description of adequate length for non-obviousness scoring", 11, "Eleven")
        assert len(examiner.all_patents) >= 1

    def test_get_patent_by_id(self):
        examiner = PatentExaminer()
        result = examiner.examine("Test", "A description of adequate length for scoring", 11, "Eleven")
        found = examiner.get_patent(result.patent_id)
        assert found is not None
        assert found.patent_id == result.patent_id

    def test_get_nonexistent_patent(self):
        examiner = PatentExaminer()
        assert examiner.get_patent("FAKE-ID") is None


# ============================================================
# CopyrightRegistry Tests
# ============================================================


class TestCopyrightRegistry:
    """Tests for the copyright registration system."""

    def test_register_first_work(self):
        registry = CopyrightRegistry()
        result = registry.register("FizzBuzz Opus 1", "1, 2, Fizz, 4, Buzz")
        assert result.status == CopyrightStatus.REGISTERED
        assert result.originality_score == 1.0

    def test_register_similar_work_disputed(self):
        registry = CopyrightRegistry(originality_threshold=0.3)
        registry.register("Original", "1, 2, Fizz, 4, Buzz")
        result = registry.register("Copy", "1, 2, Fizz, 4, Buzz")
        assert result.status == CopyrightStatus.DISPUTED
        assert result.originality_score < 0.3

    def test_register_different_work(self):
        registry = CopyrightRegistry()
        registry.register("Original", "1, 2, Fizz, 4, Buzz")
        result = registry.register("Different", "Completely unique and different content here")
        assert result.status == CopyrightStatus.REGISTERED

    def test_search_by_title(self):
        registry = CopyrightRegistry()
        registry.register("FizzBuzz Sonata", "content")
        results = registry.search("Sonata")
        assert len(results) == 1

    def test_search_no_results(self):
        registry = CopyrightRegistry()
        results = registry.search("nonexistent")
        assert len(results) == 0

    def test_all_works(self):
        registry = CopyrightRegistry()
        registry.register("Work 1", "content 1")
        registry.register("Work 2", "content 2")
        assert len(registry.all_works) == 2


# ============================================================
# LicenseManager Tests
# ============================================================


class TestLicenseManager:
    """Tests for the license management system."""

    def test_grant_fbpl(self):
        mgr = LicenseManager()
        lic = mgr.grant(LicenseType.FBPL, "User A", "TM-FIZZ")
        assert lic.license_type == LicenseType.FBPL
        assert lic.royalty_rate == 0.0

    def test_grant_fbel(self):
        mgr = LicenseManager()
        lic = mgr.grant(LicenseType.FBEL, "Enterprise Corp", "TM-FIZZ")
        assert lic.royalty_rate > 0

    def test_grant_fbcl(self):
        mgr = LicenseManager()
        lic = mgr.grant(LicenseType.FBCL, "Open Source Dev", "CR-001")
        assert "Copyleft" in lic.terms

    def test_compatibility_fbpl_to_all(self):
        mgr = LicenseManager()
        assert mgr.check_compatibility(LicenseType.FBPL, LicenseType.FBPL)
        assert mgr.check_compatibility(LicenseType.FBPL, LicenseType.FBEL)
        assert mgr.check_compatibility(LicenseType.FBPL, LicenseType.FBCL)

    def test_incompatibility_fbel_fbcl(self):
        mgr = LicenseManager()
        assert not mgr.check_compatibility(LicenseType.FBEL, LicenseType.FBCL)
        assert not mgr.check_compatibility(LicenseType.FBCL, LicenseType.FBEL)

    def test_all_licenses(self):
        mgr = LicenseManager()
        mgr.grant(LicenseType.FBPL, "User", "IP-1")
        mgr.grant(LicenseType.FBEL, "Corp", "IP-2")
        assert len(mgr.all_licenses) == 2


# ============================================================
# IPDisputeTribunal Tests
# ============================================================


class TestIPDisputeTribunal:
    """Tests for the FizzBuzz IP Tribunal."""

    def test_file_dispute(self):
        tribunal = IPDisputeTribunal()
        case = tribunal.file_dispute(
            "FizzBuzz Foundation", "Evil Corp", "trademark", "Use of 'Fhyzz'"
        )
        assert case.plaintiff == "FizzBuzz Foundation"
        assert case.case_number.startswith("FBIPT-")

    def test_adjudicate_trademark(self):
        tribunal = IPDisputeTribunal()
        case = tribunal.file_dispute(
            "FizzBuzz Foundation", "Evil Corp", "trademark", "Fhyzz vs Fizz"
        )
        result = tribunal.adjudicate(case)
        assert result.verdict is not None
        assert result.opinion != ""
        assert "BEFORE THE FIZZBUZZ INTELLECTUAL PROPERTY TRIBUNAL" in result.opinion

    def test_adjudicate_patent(self):
        tribunal = IPDisputeTribunal()
        case = tribunal.file_dispute(
            "Dr. Modulo", "Copy Corp", "patent", "Divisibility method"
        )
        result = tribunal.adjudicate(case)
        assert result.verdict == DisputeVerdict.PLAINTIFF_WINS
        assert result.damages_awarded > 0

    def test_adjudicate_copyright(self):
        tribunal = IPDisputeTribunal()
        case = tribunal.file_dispute(
            "Author A", "Author B", "copyright", "Similar output sequences"
        )
        result = tribunal.adjudicate(case)
        assert result.verdict == DisputeVerdict.SETTLED

    def test_adjudicate_unknown_type(self):
        tribunal = IPDisputeTribunal()
        case = tribunal.file_dispute(
            "Plaintiff", "Defendant", "trade_secret", "Proprietary algorithm"
        )
        result = tribunal.adjudicate(case)
        assert result.verdict == DisputeVerdict.DISMISSED

    def test_opinion_format(self):
        tribunal = IPDisputeTribunal()
        case = tribunal.file_dispute(
            "Alice", "Bob", "trademark", "Label dispute"
        )
        result = tribunal.adjudicate(case)
        assert "Case No.:" in result.opinion
        assert "FINDINGS OF FACT" in result.opinion
        assert "CONCLUSIONS OF LAW" in result.opinion
        assert "ORDER" in result.opinion
        assert "Judge Modulo" in result.opinion

    def test_all_cases(self):
        tribunal = IPDisputeTribunal()
        tribunal.file_dispute("A", "B", "trademark", "Test 1")
        tribunal.file_dispute("C", "D", "patent", "Test 2")
        assert len(tribunal.all_cases) == 2


# ============================================================
# IPOfficeDashboard Tests
# ============================================================


class TestIPOfficeDashboard:
    """Tests for the IP Office ASCII dashboard."""

    def _make_components(self):
        tm = TrademarkRegistry()
        pat = PatentExaminer()
        cr = CopyrightRegistry()
        lic = LicenseManager()
        tri = IPDisputeTribunal()
        return tm, pat, cr, lic, tri

    def test_render_empty(self):
        tm, pat, cr, lic, tri = self._make_components()
        output = IPOfficeDashboard.render(tm, pat, cr, lic, tri)
        assert "INTELLECTUAL PROPERTY OFFICE" in output
        assert "TRADEMARK PORTFOLIO" in output
        assert "PATENT PORTFOLIO" in output
        assert "COPYRIGHT PORTFOLIO" in output

    def test_render_with_data(self):
        tm, pat, cr, lic, tri = self._make_components()
        # Add some data
        tm.apply("WUZZ", "Corp", "test")
        pat.examine("Test", "A reasonably long description for the examination", 11, "Eleven")
        cr.register("Work 1", "content")
        lic.grant(LicenseType.FBPL, "User", "IP-1")
        tri.file_dispute("A", "B", "trademark", "test")

        output = IPOfficeDashboard.render(tm, pat, cr, lic, tri)
        assert "WUZZ" in output
        assert "FBPL" in output

    def test_render_custom_width(self):
        tm, pat, cr, lic, tri = self._make_components()
        output = IPOfficeDashboard.render(tm, pat, cr, lic, tri, width=80)
        assert len(output) > 0


# ============================================================
# Exception Tests
# ============================================================


class TestIPExceptions:
    """Tests for IP Office exception classes."""

    def test_ip_office_error(self):
        err = IPOfficeError("test error")
        assert "EFP-IP00" in str(err)

    def test_trademark_violation_error(self):
        err = TrademarkViolationError("Fhyzz", "Fizz", 0.85)
        assert "EFP-IP01" in str(err)
        assert "Fhyzz" in str(err)
        assert err.similarity == 0.85

    def test_patent_infringement_error(self):
        err = PatentInfringementError("div by 3", "FB-PAT-001", "prior art exists")
        assert "EFP-IP02" in str(err)
        assert err.patent_id == "FB-PAT-001"

    def test_copyright_infringement_error(self):
        err = CopyrightInfringementError("My Work", "CR-001", 0.95)
        assert "EFP-IP03" in str(err)
        assert err.original_work_id == "CR-001"

    def test_exception_hierarchy(self):
        """All IP exceptions should inherit from IPOfficeError and FizzBuzzError."""
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        assert issubclass(TrademarkViolationError, IPOfficeError)
        assert issubclass(PatentInfringementError, IPOfficeError)
        assert issubclass(CopyrightInfringementError, IPOfficeError)
        assert issubclass(IPOfficeError, FizzBuzzError)
