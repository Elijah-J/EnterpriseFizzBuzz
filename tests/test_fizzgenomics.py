"""
Enterprise FizzBuzz Platform - FizzGenomics Genome Sequence Analyzer Test Suite

Comprehensive verification of the genome sequence analysis pipeline, including
Smith-Waterman alignment, codon translation, ORF detection, BLAST search,
and phylogenetic tree construction. These tests ensure that the biological
encoding of FizzBuzz divisibility patterns is genetically sound.

Genomic analysis integrity is mission-critical: an incorrect alignment
score could misclassify the evolutionary relationship between Fizz and
Buzz sequences, constituting a violation of the Enterprise FizzBuzz
Bioinformatics Compliance Standard (EFBCS).
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzgenomics import (
    BLASTSearch,
    CodonTranslator,
    FizzBuzzGenomicEncoder,
    GenomicsMiddleware,
    ORFFinder,
    PhylogeneticTreeBuilder,
    PhyloNode,
    Sequence,
    SequenceType,
    SmithWaterman,
    AlignmentResult,
)
from enterprise_fizzbuzz.domain.exceptions.fizzgenomics import (
    AlignmentError,
    BLASTSearchError,
    CodonTranslationError,
    InvalidSequenceError,
    ORFDetectionError,
    PhylogeneticTreeError,
)
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
)


# ============================================================
# Helpers
# ============================================================


def _make_context(number: int, output: str = "") -> ProcessingContext:
    ctx = ProcessingContext(number=number, session_id=str(uuid.uuid4()))
    result = FizzBuzzResult(number=number, output=output or str(number), matched_rules=[])
    ctx.results.append(result)
    return ctx


def _identity_handler(ctx: ProcessingContext) -> ProcessingContext:
    return ctx


# ============================================================
# Sequence Validation Tests
# ============================================================


class TestSequenceValidation:
    def test_valid_dna_sequence(self):
        seq = Sequence(id="test", data="ATCGATCG")
        seq.validate()  # Should not raise

    def test_valid_rna_sequence(self):
        seq = Sequence(id="test", data="AUCGAUCG", seq_type=SequenceType.RNA)
        seq.validate()

    def test_invalid_dna_character_raises(self):
        seq = Sequence(id="test", data="ATCXATCG")
        with pytest.raises(InvalidSequenceError):
            seq.validate()

    def test_sequence_length(self):
        seq = Sequence(id="test", data="ATCG")
        assert len(seq) == 4


# ============================================================
# Smith-Waterman Alignment Tests
# ============================================================


class TestSmithWaterman:
    def test_identical_sequences(self):
        sw = SmithWaterman()
        a = Sequence(id="a", data="ATCGATCG")
        b = Sequence(id="b", data="ATCGATCG")
        result = sw.align(a, b)
        assert result.score > 0
        assert result.identity == 1.0

    def test_different_sequences_positive_score(self):
        sw = SmithWaterman()
        a = Sequence(id="a", data="ATCGATCG")
        b = Sequence(id="b", data="ATCAATCG")
        result = sw.align(a, b)
        assert result.score > 0

    def test_completely_different_sequences(self):
        sw = SmithWaterman()
        a = Sequence(id="a", data="AAAA")
        b = Sequence(id="b", data="TTTT")
        result = sw.align(a, b)
        assert result.score == 0 or result.identity < 0.5

    def test_empty_sequence_raises(self):
        sw = SmithWaterman()
        a = Sequence(id="a", data="ATCG")
        b = Sequence(id="b", data="")
        with pytest.raises(AlignmentError):
            sw.align(a, b)


# ============================================================
# Codon Translation Tests
# ============================================================


class TestCodonTranslator:
    def test_start_codon_translates_to_methionine(self):
        ct = CodonTranslator()
        result = ct.translate("ATG")
        assert result == "M"

    def test_stop_codon_produces_asterisk(self):
        ct = CodonTranslator()
        result = ct.translate("TAA")
        assert result == "*"

    def test_full_translation(self):
        ct = CodonTranslator()
        result = ct.translate("ATGGCTTAA")
        assert result == "MA*"

    def test_invalid_frame_raises(self):
        ct = CodonTranslator()
        with pytest.raises(CodonTranslationError):
            ct.translate("ATG", frame=5)

    def test_frame_offset(self):
        ct = CodonTranslator()
        # Frame 1: skip first base, read "TGA" = stop
        result = ct.translate("ATGA", frame=1)
        assert "*" in result


# ============================================================
# ORF Finder Tests
# ============================================================


class TestORFFinder:
    def test_simple_orf(self):
        finder = ORFFinder(min_length=9)
        seq = Sequence(id="test", data="ATGGCTTAA")
        orfs = finder.find_orfs(seq)
        assert len(orfs) >= 1
        assert orfs[0].start == 0
        assert orfs[0].protein == "MA*"

    def test_no_orf_in_short_sequence(self):
        finder = ORFFinder(min_length=30)
        seq = Sequence(id="test", data="ATGTAA")
        orfs = finder.find_orfs(seq)
        assert len(orfs) == 0

    def test_too_short_sequence_raises(self):
        finder = ORFFinder()
        seq = Sequence(id="test", data="AT")
        with pytest.raises(ORFDetectionError):
            finder.find_orfs(seq)


# ============================================================
# BLAST Search Tests
# ============================================================


class TestBLASTSearch:
    def test_exact_match_found(self):
        blast = BLASTSearch(k=4, min_score=5.0)
        blast.add_sequence("db1", "ATCGATCGATCG")
        query = Sequence(id="q", data="ATCGATCG")
        hits = blast.search(query)
        assert len(hits) > 0
        assert hits[0].subject_id == "db1"

    def test_empty_database_raises(self):
        blast = BLASTSearch()
        query = Sequence(id="q", data="ATCGATCG")
        with pytest.raises(BLASTSearchError):
            blast.search(query)

    def test_no_hits_for_unrelated_query(self):
        blast = BLASTSearch(k=7, min_score=20.0)
        blast.add_sequence("db1", "AAAAAAAAAAAAAAAA")
        query = Sequence(id="q", data="TTTTTTTTTTT")
        hits = blast.search(query)
        assert len(hits) == 0


# ============================================================
# Phylogenetic Tree Tests
# ============================================================


class TestPhylogeneticTree:
    def test_two_taxa_tree(self):
        tree = PhylogeneticTreeBuilder.build(
            ["A", "B"],
            [[0.0, 1.0], [1.0, 0.0]],
        )
        assert tree is not None
        assert tree.left is not None
        assert tree.right is not None

    def test_three_taxa_tree(self):
        tree = PhylogeneticTreeBuilder.build(
            ["A", "B", "C"],
            [[0.0, 1.0, 2.0], [1.0, 0.0, 1.5], [2.0, 1.5, 0.0]],
        )
        assert tree is not None

    def test_newick_format(self):
        tree = PhylogeneticTreeBuilder.build(
            ["A", "B"],
            [[0.0, 2.0], [2.0, 0.0]],
        )
        newick = tree.newick()
        assert "A" in newick
        assert "B" in newick

    def test_single_taxon_raises(self):
        with pytest.raises(PhylogeneticTreeError):
            PhylogeneticTreeBuilder.build(["A"], [[0.0]])


# ============================================================
# FizzBuzz Genomic Encoder Tests
# ============================================================


class TestFizzBuzzGenomicEncoder:
    def test_fizz_encodes_to_atg(self):
        encoder = FizzBuzzGenomicEncoder()
        seq = encoder.encode([(3, "Fizz")])
        assert seq.data == "ATG"

    def test_buzz_encodes_to_gct(self):
        encoder = FizzBuzzGenomicEncoder()
        seq = encoder.encode([(5, "Buzz")])
        assert seq.data == "GCT"

    def test_numeric_encodes_by_modulo(self):
        encoder = FizzBuzzGenomicEncoder()
        seq = encoder.encode([(1, "1")])
        assert len(seq.data) == 3


# ============================================================
# Middleware Tests
# ============================================================


class TestGenomicsMiddleware:
    def test_middleware_injects_gc_content(self):
        mw = GenomicsMiddleware(min_orf_length=3)
        ctx = _make_context(3, "Fizz")
        result = mw.process(ctx, _identity_handler)
        assert "genomics_gc_content" in result.metadata

    def test_middleware_accumulates_sequence(self):
        mw = GenomicsMiddleware(min_orf_length=3)
        for i in range(1, 16):
            output = "FizzBuzz" if i % 15 == 0 else "Fizz" if i % 3 == 0 else "Buzz" if i % 5 == 0 else str(i)
            ctx = _make_context(i, output)
            result = mw.process(ctx, _identity_handler)
        assert result.metadata["genomics_sequence_length"] > 0

    def test_middleware_implements_imiddleware(self):
        from enterprise_fizzbuzz.domain.interfaces import IMiddleware
        mw = GenomicsMiddleware()
        assert isinstance(mw, IMiddleware)
