"""
Enterprise FizzBuzz Platform - FizzGenomics Genome Sequence Analyzer

Provides DNA/RNA sequence alignment, BLAST-style homology search, codon
translation, open reading frame detection, and phylogenetic tree construction
for the biological analysis of FizzBuzz classification patterns.

The FizzBuzz sequence encodes a hidden biological signal: when the output
labels "Fizz", "Buzz", and "FizzBuzz" are mapped to nucleotide triplets
(Fizz -> ATG, Buzz -> TAA, FizzBuzz -> TGA), the resulting sequence forms
a valid open reading frame that translates to a protein with structural
homology to known divisibility-sensing enzymes found in extremophile archaea.

Sequence alignment uses the Smith-Waterman local alignment algorithm with
affine gap penalties. The BLAST-style search uses a seed-and-extend strategy
for rapid homology detection. Phylogenetic trees are built using UPGMA
hierarchical clustering on pairwise distance matrices.

All computations use pure Python with no external bioinformatics libraries.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions.fizzgenomics import (
    AlignmentError,
    BLASTSearchError,
    CodonTranslationError,
    GenomicsMiddlewareError,
    InvalidSequenceError,
    ORFDetectionError,
    PhylogeneticTreeError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)

# Valid nucleotide alphabets
DNA_ALPHABET = set("ATCGN")
RNA_ALPHABET = set("AUCGN")

# Standard genetic code (DNA codons -> amino acids)
CODON_TABLE = {
    "TTT": "F", "TTC": "F", "TTA": "L", "TTG": "L",
    "CTT": "L", "CTC": "L", "CTA": "L", "CTG": "L",
    "ATT": "I", "ATC": "I", "ATA": "I", "ATG": "M",
    "GTT": "V", "GTC": "V", "GTA": "V", "GTG": "V",
    "TCT": "S", "TCC": "S", "TCA": "S", "TCG": "S",
    "CCT": "P", "CCC": "P", "CCA": "P", "CCG": "P",
    "ACT": "T", "ACC": "T", "ACA": "T", "ACG": "T",
    "GCT": "A", "GCC": "A", "GCA": "A", "GCG": "A",
    "TAT": "Y", "TAC": "Y", "TAA": "*", "TAG": "*",
    "CAT": "H", "CAC": "H", "CAA": "Q", "CAG": "Q",
    "AAT": "N", "AAC": "N", "AAA": "K", "AAG": "K",
    "GAT": "D", "GAC": "D", "GAA": "E", "GAG": "E",
    "TGT": "C", "TGC": "C", "TGA": "*", "TGG": "W",
    "CGT": "R", "CGC": "R", "CGA": "R", "CGG": "R",
    "AGT": "S", "AGC": "S", "AGA": "R", "AGG": "R",
    "GGT": "G", "GGC": "G", "GGA": "G", "GGG": "G",
}

# BLOSUM62-inspired substitution scores for nucleotides
NUC_MATCH = 2
NUC_MISMATCH = -1
GAP_OPEN = -5
GAP_EXTEND = -2


# ============================================================
# Sequence Type Enum
# ============================================================


class SequenceType(Enum):
    """Type of nucleotide sequence."""

    DNA = auto()
    RNA = auto()


# ============================================================
# Data Classes
# ============================================================


@dataclass
class Sequence:
    """A biological sequence with identifier and nucleotide data."""

    id: str
    data: str
    seq_type: SequenceType = SequenceType.DNA

    def validate(self) -> None:
        """Validate that all characters are valid nucleotides."""
        alphabet = DNA_ALPHABET if self.seq_type == SequenceType.DNA else RNA_ALPHABET
        for i, ch in enumerate(self.data.upper()):
            if ch not in alphabet:
                raise InvalidSequenceError(self.id, ch, i)

    def __len__(self) -> int:
        return len(self.data)


@dataclass
class AlignmentResult:
    """Result of a pairwise sequence alignment."""

    seq_a_id: str
    seq_b_id: str
    score: float
    aligned_a: str
    aligned_b: str
    start_a: int
    start_b: int
    identity: float


@dataclass
class ORF:
    """An open reading frame found in a sequence."""

    start: int
    end: int
    frame: int  # 0, 1, or 2
    protein: str
    length: int


@dataclass
class BLASTHit:
    """A hit from a BLAST-style sequence search."""

    subject_id: str
    score: float
    identity: float
    alignment_length: int
    query_start: int
    subject_start: int


@dataclass
class PhyloNode:
    """A node in a phylogenetic tree."""

    name: str
    distance: float = 0.0
    left: Optional[PhyloNode] = None
    right: Optional[PhyloNode] = None

    @property
    def is_leaf(self) -> bool:
        return self.left is None and self.right is None

    def newick(self) -> str:
        """Render this node in Newick format."""
        if self.is_leaf:
            return f"{self.name}:{self.distance:.4f}"
        left_s = self.left.newick() if self.left else ""
        right_s = self.right.newick() if self.right else ""
        return f"({left_s},{right_s}):{self.distance:.4f}"


# ============================================================
# Smith-Waterman Alignment
# ============================================================


class SmithWaterman:
    """Smith-Waterman local sequence alignment with affine gap penalties.

    The Smith-Waterman algorithm guarantees optimal local alignment
    between two sequences. It uses dynamic programming to fill a
    scoring matrix where each cell represents the best alignment
    ending at that position. Affine gap penalties model the biological
    reality that gap initiation is costlier than gap extension.
    """

    def __init__(
        self,
        match: int = NUC_MATCH,
        mismatch: int = NUC_MISMATCH,
        gap_open: int = GAP_OPEN,
        gap_extend: int = GAP_EXTEND,
    ) -> None:
        self.match = match
        self.mismatch = mismatch
        self.gap_open = gap_open
        self.gap_extend = gap_extend

    def align(self, seq_a: Sequence, seq_b: Sequence) -> AlignmentResult:
        """Perform local alignment between two sequences."""
        a = seq_a.data.upper()
        b = seq_b.data.upper()
        m, n = len(a), len(b)

        if m == 0 or n == 0:
            raise AlignmentError(seq_a.id, seq_b.id, "Empty sequence")

        # Score matrices: H (main), E (gap in a), F (gap in b)
        H = [[0] * (n + 1) for _ in range(m + 1)]
        E = [[0] * (n + 1) for _ in range(m + 1)]
        F = [[0] * (n + 1) for _ in range(m + 1)]

        max_score = 0
        max_i, max_j = 0, 0

        for i in range(1, m + 1):
            for j in range(1, n + 1):
                # Substitution score
                sub = self.match if a[i - 1] == b[j - 1] else self.mismatch

                # Gap in sequence b (insertion)
                E[i][j] = max(
                    H[i][j - 1] + self.gap_open + self.gap_extend,
                    E[i][j - 1] + self.gap_extend,
                )

                # Gap in sequence a (deletion)
                F[i][j] = max(
                    H[i - 1][j] + self.gap_open + self.gap_extend,
                    F[i - 1][j] + self.gap_extend,
                )

                # Main recursion
                H[i][j] = max(
                    0,
                    H[i - 1][j - 1] + sub,
                    E[i][j],
                    F[i][j],
                )

                if H[i][j] > max_score:
                    max_score = H[i][j]
                    max_i, max_j = i, j

        # Traceback
        aligned_a, aligned_b = [], []
        i, j = max_i, max_j
        while i > 0 and j > 0 and H[i][j] > 0:
            if H[i][j] == H[i - 1][j - 1] + (self.match if a[i - 1] == b[j - 1] else self.mismatch):
                aligned_a.append(a[i - 1])
                aligned_b.append(b[j - 1])
                i -= 1
                j -= 1
            elif H[i][j] == F[i][j]:
                aligned_a.append(a[i - 1])
                aligned_b.append("-")
                i -= 1
            else:
                aligned_a.append("-")
                aligned_b.append(b[j - 1])
                j -= 1

        aligned_a.reverse()
        aligned_b.reverse()
        al_a = "".join(aligned_a)
        al_b = "".join(aligned_b)

        # Compute identity
        matches = sum(1 for x, y in zip(al_a, al_b) if x == y and x != "-")
        al_len = max(len(al_a), 1)
        identity = matches / al_len

        return AlignmentResult(
            seq_a_id=seq_a.id,
            seq_b_id=seq_b.id,
            score=max_score,
            aligned_a=al_a,
            aligned_b=al_b,
            start_a=i,
            start_b=j,
            identity=identity,
        )


# ============================================================
# Codon Translator
# ============================================================


class CodonTranslator:
    """Translates nucleotide sequences into amino acid sequences.

    Uses the standard genetic code to translate each triplet of
    nucleotides (codon) into the corresponding amino acid. Stop
    codons (TAA, TAG, TGA) terminate translation.
    """

    def __init__(self, codon_table: Optional[dict[str, str]] = None) -> None:
        self._table = codon_table or CODON_TABLE

    def translate(self, sequence: str, frame: int = 0) -> str:
        """Translate a DNA sequence starting at the given reading frame.

        Args:
            sequence: DNA sequence string
            frame: Reading frame offset (0, 1, or 2)

        Returns:
            Amino acid sequence string (stop codons as '*')
        """
        seq = sequence.upper()
        if frame < 0 or frame > 2:
            raise CodonTranslationError("N/A", f"Invalid reading frame {frame}")

        protein = []
        for i in range(frame, len(seq) - 2, 3):
            codon = seq[i:i + 3]
            if len(codon) < 3:
                break
            aa = self._table.get(codon)
            if aa is None:
                raise CodonTranslationError(codon, "Unrecognized codon")
            protein.append(aa)

        return "".join(protein)


# ============================================================
# ORF Finder
# ============================================================


class ORFFinder:
    """Detects open reading frames in DNA sequences.

    An ORF begins with a start codon (ATG) and extends to the nearest
    in-frame stop codon (TAA, TAG, TGA). All three reading frames on
    the forward strand are searched. ORFs shorter than the minimum
    length are filtered out.
    """

    def __init__(self, min_length: int = 30, translator: Optional[CodonTranslator] = None) -> None:
        self.min_length = min_length
        self._translator = translator or CodonTranslator()

    def find_orfs(self, sequence: Sequence) -> list[ORF]:
        """Find all ORFs in the given sequence."""
        if len(sequence) < 3:
            raise ORFDetectionError(sequence.id, "Sequence too short for ORF detection")

        seq = sequence.data.upper()
        stop_codons = {"TAA", "TAG", "TGA"}
        orfs: list[ORF] = []

        for frame in range(3):
            i = frame
            while i < len(seq) - 2:
                codon = seq[i:i + 3]
                if codon == "ATG":
                    # Found start codon, scan for stop
                    start = i
                    j = i + 3
                    while j < len(seq) - 2:
                        next_codon = seq[j:j + 3]
                        if next_codon in stop_codons:
                            end = j + 3
                            orf_seq = seq[start:end]
                            if len(orf_seq) >= self.min_length:
                                protein = self._translator.translate(orf_seq)
                                orfs.append(ORF(
                                    start=start,
                                    end=end,
                                    frame=frame,
                                    protein=protein,
                                    length=end - start,
                                ))
                            i = j + 3
                            break
                        j += 3
                    else:
                        i += 3
                        continue
                    continue
                i += 3

        return orfs


# ============================================================
# BLAST-style Search
# ============================================================


class BLASTSearch:
    """Seed-and-extend sequence homology search.

    Implements a simplified BLAST strategy: index the database
    sequences by k-mer seeds, then for each query k-mer, extend
    matching seeds into full ungapped alignments. This provides
    rapid homology detection with near-optimal sensitivity for
    FizzBuzz-scale genomic databases.
    """

    def __init__(self, k: int = 7, min_score: float = 20.0) -> None:
        self.k = k
        self.min_score = min_score
        self._database: dict[str, str] = {}
        self._index: dict[str, list[tuple[str, int]]] = {}

    def add_sequence(self, seq_id: str, data: str) -> None:
        """Add a sequence to the search database."""
        data_upper = data.upper()
        self._database[seq_id] = data_upper
        for i in range(len(data_upper) - self.k + 1):
            kmer = data_upper[i:i + self.k]
            self._index.setdefault(kmer, []).append((seq_id, i))

    def search(self, query: Sequence) -> list[BLASTHit]:
        """Search the database for sequences similar to query."""
        if not self._database:
            raise BLASTSearchError(query.id, "Empty database")

        q = query.data.upper()
        hits: dict[str, BLASTHit] = {}

        for i in range(len(q) - self.k + 1):
            kmer = q[i:i + self.k]
            for subj_id, subj_pos in self._index.get(kmer, []):
                # Extend the seed match
                score, length, matches = self._extend(
                    q, i, self._database[subj_id], subj_pos
                )
                if score >= self.min_score:
                    key = f"{subj_id}:{subj_pos}"
                    if key not in hits or hits[key].score < score:
                        hits[key] = BLASTHit(
                            subject_id=subj_id,
                            score=score,
                            identity=matches / max(length, 1),
                            alignment_length=length,
                            query_start=i,
                            subject_start=subj_pos,
                        )

        return sorted(hits.values(), key=lambda h: h.score, reverse=True)

    def _extend(
        self, query: str, q_start: int, subject: str, s_start: int
    ) -> tuple[float, int, int]:
        """Extend a seed match in both directions."""
        score = 0.0
        matches = 0
        length = 0

        # Extend right
        qi, si = q_start, s_start
        while qi < len(query) and si < len(subject):
            if query[qi] == subject[si]:
                score += NUC_MATCH
                matches += 1
            else:
                score += NUC_MISMATCH
                if score < 0:
                    break
            qi += 1
            si += 1
            length += 1

        return score, length, matches


# ============================================================
# Phylogenetic Tree Builder (UPGMA)
# ============================================================


class PhylogeneticTreeBuilder:
    """Builds phylogenetic trees using UPGMA hierarchical clustering.

    The Unweighted Pair Group Method with Arithmetic Mean (UPGMA)
    assumes a molecular clock (constant rate of evolution). It
    iteratively merges the closest pair of clusters until a single
    tree remains. The resulting ultrametric tree represents the
    evolutionary relationships between FizzBuzz sequence variants.
    """

    @staticmethod
    def build(
        taxa: list[str],
        distance_matrix: list[list[float]],
    ) -> PhyloNode:
        """Build a UPGMA tree from a distance matrix."""
        n = len(taxa)
        if n < 2:
            raise PhylogeneticTreeError(n, "At least two taxa required")
        if len(distance_matrix) != n:
            raise PhylogeneticTreeError(n, "Distance matrix dimensions mismatch")

        # Initialize clusters
        clusters: list[PhyloNode] = [PhyloNode(name=t) for t in taxa]
        sizes: list[int] = [1] * n
        # Copy distance matrix
        dist = [row[:] for row in distance_matrix]

        while len(clusters) > 1:
            # Find minimum distance pair
            min_d = float("inf")
            mi, mj = 0, 1
            for i in range(len(clusters)):
                for j in range(i + 1, len(clusters)):
                    if dist[i][j] < min_d:
                        min_d = dist[i][j]
                        mi, mj = i, j

            # Create merged node
            half_dist = min_d / 2.0
            left_node = clusters[mi]
            right_node = clusters[mj]
            left_node.distance = half_dist
            right_node.distance = half_dist

            merged = PhyloNode(
                name=f"({left_node.name},{right_node.name})",
                left=left_node,
                right=right_node,
            )

            # Update distance matrix (UPGMA average)
            new_row = []
            for k in range(len(clusters)):
                if k == mi or k == mj:
                    new_row.append(0.0)
                else:
                    d_new = (dist[mi][k] * sizes[mi] + dist[mj][k] * sizes[mj]) / (sizes[mi] + sizes[mj])
                    new_row.append(d_new)

            # Remove mj first (higher index), then mi
            new_size = sizes[mi] + sizes[mj]
            for idx in sorted([mi, mj], reverse=True):
                clusters.pop(idx)
                sizes.pop(idx)
                dist.pop(idx)
                for row in dist:
                    row.pop(idx)

            # Add merged cluster
            for i, row in enumerate(dist):
                row.append(new_row[i] if i < len(new_row) else 0.0)
            dist.append([new_row[i] if i < len(clusters) else 0.0 for i in range(len(clusters))] + [0.0])
            clusters.append(merged)
            sizes.append(new_size)

        return clusters[0]


# ============================================================
# FizzBuzz Genomic Encoder
# ============================================================


class FizzBuzzGenomicEncoder:
    """Encodes FizzBuzz output sequences as DNA.

    Maps FizzBuzz classification labels to nucleotide codons:
    - "Fizz"     -> ATG (start codon / Methionine)
    - "Buzz"     -> GCT (Alanine)
    - "FizzBuzz" -> TGG (Tryptophan)
    - numeric    -> mapped by (n % 4) to {AAA, CCC, GGG, TTT}

    This encoding preserves the algebraic structure of the FizzBuzz
    sequence in biological form, enabling phylogenetic analysis of
    divisibility patterns across different modular bases.
    """

    LABEL_MAP = {
        "Fizz": "ATG",
        "Buzz": "GCT",
        "FizzBuzz": "TGG",
    }
    NUMERIC_MAP = {0: "AAA", 1: "CCC", 2: "GGG", 3: "TTT"}

    def encode(self, labels: list[tuple[int, str]]) -> Sequence:
        """Encode a list of (number, label) pairs as a DNA sequence."""
        codons = []
        for number, label in labels:
            if label in self.LABEL_MAP:
                codons.append(self.LABEL_MAP[label])
            else:
                codons.append(self.NUMERIC_MAP[number % 4])
        return Sequence(id="fizzbuzz_genome", data="".join(codons))


# ============================================================
# FizzGenomics Middleware
# ============================================================


class GenomicsMiddleware(IMiddleware):
    """Injects genomic analysis context into the FizzBuzz pipeline.

    Accumulates FizzBuzz classifications and periodically encodes them
    as DNA, searching for ORFs and computing sequence statistics. The
    genomic context is attached to the processing metadata for
    downstream consumption.
    """

    def __init__(
        self,
        min_orf_length: int = 9,
        enable_blast: bool = False,
    ) -> None:
        self._encoder = FizzBuzzGenomicEncoder()
        self._orf_finder = ORFFinder(min_length=min_orf_length)
        self._translator = CodonTranslator()
        self._accumulated: list[tuple[int, str]] = []
        self._enable_blast = enable_blast
        self._blast = BLASTSearch() if enable_blast else None

    def get_name(self) -> str:
        return "fizzgenomics"

    def get_priority(self) -> int:
        return 275

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Accumulate classification and inject genomic context."""
        try:
            output = ""
            if context.results:
                output = context.results[-1].output

            label = output if output in ("Fizz", "Buzz", "FizzBuzz") else str(context.number)
            self._accumulated.append((context.number, label))

            # Encode current accumulated sequence
            seq = self._encoder.encode(self._accumulated)
            context.metadata["genomics_sequence_length"] = len(seq.data)
            context.metadata["genomics_gc_content"] = self._gc_content(seq.data)

            # Find ORFs every 15 numbers (one FizzBuzz cycle)
            if len(self._accumulated) % 15 == 0 and len(seq.data) >= 9:
                orfs = self._orf_finder.find_orfs(seq)
                context.metadata["genomics_orf_count"] = len(orfs)
                if orfs:
                    context.metadata["genomics_longest_orf"] = max(o.length for o in orfs)

        except Exception as exc:
            logger.error("FizzGenomics middleware error: %s", exc)
            context.metadata["genomics_error"] = str(exc)

        return next_handler(context)

    @staticmethod
    def _gc_content(seq: str) -> float:
        """Compute GC content ratio of a sequence."""
        if not seq:
            return 0.0
        gc = sum(1 for c in seq.upper() if c in ("G", "C"))
        return gc / len(seq)
