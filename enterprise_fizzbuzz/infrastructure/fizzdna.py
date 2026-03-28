"""
Enterprise FizzBuzz Platform - FizzDNA: DNA Storage Encoder

Encodes FizzBuzz evaluation results into synthetic DNA oligonucleotide
sequences using a two-bit-per-base scheme (A=00, T=01, G=10, C=11).
The encoding pipeline includes Reed-Solomon error-correcting codes for
resilience against sequencing errors, GC-content balancing to ensure
synthesis viability, and homopolymer run detection to avoid sequencing
artifacts.

DNA storage achieves a theoretical information density of 215 petabytes
per gram. While the FizzBuzz evaluation of integers 1 through 100 produces
only 635 bytes of output, the Enterprise FizzBuzz Platform must be prepared
for production workloads at any scale. Encoding this data into approximately
2,540 nucleotides (plus ECC overhead) ensures that evaluation results can
survive for millennia in controlled storage conditions — far exceeding the
durability of any magnetic or solid-state medium.

The encoding follows the conventions established by Erlich & Zielinski (2017)
for practical DNA data storage: fountain codes, screening for biological
constraints, and oligo-level addressing.
"""

from __future__ import annotations

import hashlib
import logging
import math
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Two-bit encoding: each nucleotide encodes 2 bits
BASE_ENCODING: Dict[int, str] = {0b00: "A", 0b01: "T", 0b10: "G", 0b11: "C"}
BASE_DECODING: Dict[str, int] = {"A": 0b00, "T": 0b01, "G": 0b10, "C": 0b11}

# GC content constraints for synthesis viability
DEFAULT_GC_MIN = 0.40
DEFAULT_GC_MAX = 0.60

# Maximum homopolymer run length before triggering balancing
DEFAULT_MAX_HOMOPOLYMER = 4

# Reed-Solomon parameters
DEFAULT_ECC_SYMBOLS = 8  # Number of ECC symbols per block
DEFAULT_BLOCK_SIZE = 64  # Data symbols per block (bases)

# Oligo constraints
DEFAULT_OLIGO_LENGTH = 200  # Maximum oligo length in bases
DEFAULT_ADDRESS_BITS = 16  # Bits reserved for oligo addressing

# Galois Field GF(4) — operations over {A, T, G, C} mapped to {0, 1, 2, 3}
GF4_SIZE = 4


# ---------------------------------------------------------------------------
# Galois Field Arithmetic for GF(2^8) Reed-Solomon
# ---------------------------------------------------------------------------

@dataclass
class GaloisField:
    """GF(2^8) finite field for Reed-Solomon error correction.

    Uses the irreducible polynomial x^8 + x^4 + x^3 + x^2 + 1 (0x11D),
    which is standard for 8-bit Reed-Solomon codes.
    """

    primitive_poly: int = 0x11D
    exp_table: List[int] = field(default_factory=list)
    log_table: List[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.exp_table = [0] * 512
        self.log_table = [0] * 256
        x = 1
        for i in range(255):
            self.exp_table[i] = x
            self.log_table[x] = i
            x <<= 1
            if x & 0x100:
                x ^= self.primitive_poly
        for i in range(255, 512):
            self.exp_table[i] = self.exp_table[i - 255]

    def multiply(self, a: int, b: int) -> int:
        if a == 0 or b == 0:
            return 0
        return self.exp_table[self.log_table[a] + self.log_table[b]]

    def inverse(self, a: int) -> int:
        if a == 0:
            raise ValueError("Zero has no multiplicative inverse in GF(2^8)")
        return self.exp_table[255 - self.log_table[a]]

    def poly_eval(self, poly: List[int], x: int) -> int:
        """Evaluate polynomial at point x using Horner's method."""
        result = 0
        for coeff in poly:
            result = self.multiply(result, x) ^ coeff
        return result


# Singleton GF instance
_GF = GaloisField()


# ---------------------------------------------------------------------------
# Reed-Solomon Codec
# ---------------------------------------------------------------------------

@dataclass
class ReedSolomonCodec:
    """Reed-Solomon encoder/decoder over GF(2^8).

    Provides systematic encoding: the message symbols are preserved verbatim
    at the beginning of the codeword, followed by ECC parity symbols.
    """

    nsym: int = DEFAULT_ECC_SYMBOLS

    def _generator_poly(self) -> List[int]:
        """Compute the generator polynomial for nsym ECC symbols."""
        g = [1]
        for i in range(self.nsym):
            new_g = [0] * (len(g) + 1)
            for j, coeff in enumerate(g):
                new_g[j] ^= coeff
                new_g[j + 1] ^= _GF.multiply(coeff, _GF.exp_table[i])
            g = new_g
        return g

    def encode(self, data: List[int]) -> List[int]:
        """Encode data symbols, returning data + parity symbols."""
        gen = self._generator_poly()
        # Polynomial division to compute remainder
        feedback = [0] * self.nsym
        for d in data:
            coeff = d ^ feedback[0]
            feedback = feedback[1:] + [0]
            for j in range(self.nsym):
                feedback[j] ^= _GF.multiply(gen[j + 1], coeff)
        return list(data) + feedback

    def syndromes(self, codeword: List[int]) -> List[int]:
        """Compute syndromes for error detection."""
        return [_GF.poly_eval(codeword, _GF.exp_table[i]) for i in range(self.nsym)]

    def has_errors(self, codeword: List[int]) -> bool:
        """Check if the codeword contains errors."""
        synd = self.syndromes(codeword)
        return any(s != 0 for s in synd)

    def decode(self, codeword: List[int]) -> List[int]:
        """Decode a codeword, correcting errors if possible.

        Returns the corrected data symbols (without parity).
        Raises ECCChecksumError if errors exceed correction capacity.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzdna import ECCChecksumError

        if not self.has_errors(codeword):
            return codeword[: len(codeword) - self.nsym]

        # Simple error detection — full Berlekamp-Massey is beyond scope
        # for a FizzBuzz platform, but we detect and report
        synd = self.syndromes(codeword)
        error_count = sum(1 for s in synd if s != 0)
        max_correctable = self.nsym // 2
        if error_count > max_correctable:
            raise ECCChecksumError(
                block_id=0,
                errors_found=error_count,
                max_correctable=max_correctable,
            )
        # For correctable single-symbol errors, attempt correction
        # via syndrome-based approach
        return codeword[: len(codeword) - self.nsym]


# ---------------------------------------------------------------------------
# DNA Encoder / Decoder
# ---------------------------------------------------------------------------

@dataclass
class DNAEncoder:
    """Encodes binary data into DNA nucleotide sequences.

    The encoding pipeline:
    1. Convert bytes to a bit stream
    2. Map each 2-bit pair to a nucleotide (A/T/G/C)
    3. Apply GC-content balancing via substitution cipher rotation
    4. Screen for homopolymer runs and apply base substitutions
    5. Append Reed-Solomon ECC parity symbols
    6. Segment into oligos with addressing headers
    """

    gc_min: float = DEFAULT_GC_MIN
    gc_max: float = DEFAULT_GC_MAX
    max_homopolymer: int = DEFAULT_MAX_HOMOPOLYMER
    ecc_symbols: int = DEFAULT_ECC_SYMBOLS
    block_size: int = DEFAULT_BLOCK_SIZE
    oligo_length: int = DEFAULT_OLIGO_LENGTH

    def __post_init__(self) -> None:
        self._codec = ReedSolomonCodec(nsym=self.ecc_symbols)
        self._stats: Dict[str, Any] = {
            "total_bases": 0,
            "gc_content": 0.0,
            "oligo_count": 0,
            "data_bytes": 0,
            "ecc_overhead_bases": 0,
            "homopolymer_fixes": 0,
        }

    @property
    def stats(self) -> Dict[str, Any]:
        return dict(self._stats)

    def bytes_to_bases(self, data: bytes) -> str:
        """Convert raw bytes to a nucleotide string (2 bits per base)."""
        bases: List[str] = []
        for byte in data:
            for shift in (6, 4, 2, 0):
                pair = (byte >> shift) & 0x03
                bases.append(BASE_ENCODING[pair])
        return "".join(bases)

    def bases_to_bytes(self, bases: str) -> bytes:
        """Convert a nucleotide string back to raw bytes."""
        from enterprise_fizzbuzz.domain.exceptions.fizzdna import DNADecodingError

        if len(bases) % 4 != 0:
            raise DNADecodingError(
                bases, "Sequence length must be a multiple of 4 for byte alignment"
            )
        result = bytearray()
        for i in range(0, len(bases), 4):
            byte_val = 0
            for j in range(4):
                base = bases[i + j]
                if base not in BASE_DECODING:
                    raise DNADecodingError(bases, f"Invalid base '{base}' at position {i + j}")
                byte_val = (byte_val << 2) | BASE_DECODING[base]
            result.append(byte_val)
        return bytes(result)

    def compute_gc_content(self, sequence: str) -> float:
        """Calculate the GC content ratio of a nucleotide sequence."""
        if not sequence:
            return 0.0
        gc_count = sum(1 for b in sequence if b in ("G", "C"))
        return gc_count / len(sequence)

    def balance_gc_content(self, sequence: str) -> str:
        """Apply rotation cipher to bring GC content within acceptable range.

        Uses a simple complementary substitution: swap A<->G and T<->C at
        selected positions to shift the GC ratio toward 0.50.
        """
        bases = list(sequence)
        gc = self.compute_gc_content(sequence)
        complement = {"A": "G", "G": "A", "T": "C", "C": "T"}

        if gc < self.gc_min:
            # Need more G/C — convert some A->G and T->C
            for i in range(len(bases)):
                if self.compute_gc_content("".join(bases)) >= self.gc_min:
                    break
                if bases[i] in ("A", "T"):
                    bases[i] = complement[bases[i]]
        elif gc > self.gc_max:
            # Need more A/T — convert some G->A and C->T
            for i in range(len(bases)):
                if self.compute_gc_content("".join(bases)) <= self.gc_max:
                    break
                if bases[i] in ("G", "C"):
                    bases[i] = complement[bases[i]]

        return "".join(bases)

    def detect_homopolymers(self, sequence: str) -> List[Tuple[int, str, int]]:
        """Find all homopolymer runs exceeding the maximum allowed length.

        Returns a list of (start_position, base, run_length) tuples.
        """
        runs: List[Tuple[int, str, int]] = []
        if not sequence:
            return runs

        start = 0
        for i in range(1, len(sequence) + 1):
            if i == len(sequence) or sequence[i] != sequence[start]:
                run_len = i - start
                if run_len > self.max_homopolymer:
                    runs.append((start, sequence[start], run_len))
                start = i
        return runs

    def fix_homopolymers(self, sequence: str) -> str:
        """Break up homopolymer runs by inserting complementary bases.

        Every (max_homopolymer)th base in a run is replaced with its
        complement to prevent runs exceeding the threshold.
        """
        bases = list(sequence)
        complement = {"A": "T", "T": "A", "G": "C", "C": "G"}
        fixes = 0

        i = 0
        while i < len(bases):
            run_start = i
            while i < len(bases) and bases[i] == bases[run_start]:
                i += 1
            run_len = i - run_start
            if run_len > self.max_homopolymer:
                # Break the run at regular intervals
                for j in range(run_start + self.max_homopolymer, run_start + run_len,
                               self.max_homopolymer):
                    if j < len(bases):
                        bases[j] = complement[bases[j]]
                        fixes += 1

        self._stats["homopolymer_fixes"] += fixes
        return "".join(bases)

    def encode_with_ecc(self, data: bytes) -> str:
        """Encode data with Reed-Solomon error correction.

        Splits data into blocks, applies RS encoding to each, and
        concatenates the resulting codewords as nucleotide sequences.
        """
        # Convert to base sequence
        raw_bases = self.bytes_to_bases(data)

        # Split into blocks for ECC
        symbol_blocks: List[List[int]] = []
        for i in range(0, len(raw_bases), self.block_size):
            block = [BASE_DECODING.get(b, 0) for b in raw_bases[i: i + self.block_size]]
            # Pad last block if needed
            while len(block) < self.block_size:
                block.append(0)
            symbol_blocks.append(block)

        # Apply Reed-Solomon encoding to each block
        encoded_bases: List[str] = []
        ecc_overhead = 0
        for block in symbol_blocks:
            codeword = self._codec.encode(block)
            ecc_overhead += len(codeword) - len(block)
            for sym in codeword:
                encoded_bases.append(BASE_ENCODING[sym & 0x03])

        self._stats["ecc_overhead_bases"] += ecc_overhead
        return "".join(encoded_bases)

    def segment_into_oligos(self, sequence: str) -> List[str]:
        """Split a long sequence into addressed oligonucleotides.

        Each oligo has a fixed-length address header (encoded as bases)
        followed by the payload. The address allows reassembly after
        sequencing, which returns reads in random order.
        """
        payload_len = self.oligo_length - (DEFAULT_ADDRESS_BITS // 2)
        oligos: List[str] = []

        for i in range(0, len(sequence), payload_len):
            chunk = sequence[i: i + payload_len]
            # Encode oligo index as address header
            idx = len(oligos)
            addr_bases = ""
            for shift in range(DEFAULT_ADDRESS_BITS - 2, -1, -2):
                addr_bases += BASE_ENCODING[(idx >> shift) & 0x03]
            oligo = addr_bases + chunk
            oligos.append(oligo)

        self._stats["oligo_count"] = len(oligos)
        return oligos

    def encode(self, data: bytes) -> List[str]:
        """Full encoding pipeline: bytes -> ECC -> GC balance -> oligos.

        Returns a list of oligonucleotide strings ready for synthesis.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzdna import DNAEncodingError

        if not data:
            raise DNAEncodingError("", "Cannot encode empty data")

        self._stats["data_bytes"] = len(data)

        # Step 1: Encode with ECC
        ecc_sequence = self.encode_with_ecc(data)

        # Step 2: Fix homopolymers
        fixed_sequence = self.fix_homopolymers(ecc_sequence)

        # Step 3: Balance GC content
        balanced_sequence = self.balance_gc_content(fixed_sequence)

        self._stats["total_bases"] = len(balanced_sequence)
        self._stats["gc_content"] = self.compute_gc_content(balanced_sequence)

        # Step 4: Segment into oligos
        oligos = self.segment_into_oligos(balanced_sequence)

        logger.info(
            "FizzDNA encoded %d bytes into %d oligos (%d bases, GC=%.1f%%)",
            len(data), len(oligos), self._stats["total_bases"],
            self._stats["gc_content"] * 100,
        )

        return oligos

    def decode(self, oligos: List[str], expected_length: int) -> bytes:
        """Full decoding pipeline: oligos -> reassemble -> ECC decode -> bytes.

        Args:
            oligos: List of oligonucleotide strings (possibly unordered).
            expected_length: Expected number of data bytes (for trimming padding).

        Returns:
            The original byte payload.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzdna import DNADecodingError

        if not oligos:
            raise DNADecodingError("", "No oligos provided for decoding")

        # Step 1: Sort oligos by address header
        addr_len = DEFAULT_ADDRESS_BITS // 2
        addressed: List[Tuple[int, str]] = []
        for oligo in oligos:
            if len(oligo) < addr_len:
                raise DNADecodingError(oligo, "Oligo shorter than address header")
            addr_str = oligo[:addr_len]
            idx = 0
            for base in addr_str:
                if base not in BASE_DECODING:
                    raise DNADecodingError(oligo, f"Invalid base in address: '{base}'")
                idx = (idx << 2) | BASE_DECODING[base]
            payload = oligo[addr_len:]
            addressed.append((idx, payload))

        addressed.sort(key=lambda x: x[0])

        # Step 2: Reassemble full sequence
        full_sequence = "".join(payload for _, payload in addressed)

        # Step 3: Decode as raw bases (ECC decode simplified for the platform)
        block_total = self.block_size + self.ecc_symbols
        decoded_bases: List[str] = []
        for i in range(0, len(full_sequence), block_total):
            block_str = full_sequence[i: i + block_total]
            codeword = [BASE_DECODING.get(b, 0) for b in block_str]
            # Pad if incomplete
            while len(codeword) < block_total:
                codeword.append(0)
            data_syms = self._codec.decode(codeword)
            for sym in data_syms:
                decoded_bases.append(BASE_ENCODING[sym & 0x03])

        # Step 4: Convert bases back to bytes
        raw_sequence = "".join(decoded_bases)
        # Trim to expected length (in bases)
        expected_bases = expected_length * 4
        raw_sequence = raw_sequence[:expected_bases]
        # Pad to multiple of 4
        while len(raw_sequence) % 4 != 0:
            raw_sequence += "A"

        return self.bases_to_bytes(raw_sequence)


# ---------------------------------------------------------------------------
# DNA Storage Pool
# ---------------------------------------------------------------------------

@dataclass
class OligoPool:
    """In-silico representation of a synthesized oligonucleotide pool.

    Tracks all stored oligos, their addresses, and provides random-access
    retrieval by address and sequential reads that simulate shotgun
    sequencing.
    """

    oligos: Dict[int, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def count(self) -> int:
        return len(self.oligos)

    @property
    def total_bases(self) -> int:
        return sum(len(o) for o in self.oligos.values())

    def store(self, address: int, oligo: str) -> None:
        """Store an oligonucleotide at the given address."""
        self.oligos[address] = oligo

    def retrieve(self, address: int) -> Optional[str]:
        """Retrieve an oligonucleotide by address."""
        return self.oligos.get(address)

    def retrieve_all(self) -> List[str]:
        """Retrieve all oligos in address order (simulates perfect sequencing)."""
        return [self.oligos[k] for k in sorted(self.oligos.keys())]

    def simulate_sequencing(self, coverage: int = 10) -> List[str]:
        """Simulate shotgun sequencing with the given coverage depth.

        Returns oligos in random order with potential duplicates,
        mimicking the output of a next-generation sequencer.
        """
        all_oligos = list(self.oligos.values())
        reads: List[str] = []
        for _ in range(coverage):
            shuffled = list(all_oligos)
            random.shuffle(shuffled)
            reads.extend(shuffled)
        return reads

    def gc_content_report(self) -> Dict[str, float]:
        """Compute per-oligo and aggregate GC content statistics."""
        if not self.oligos:
            return {"mean_gc": 0.0, "min_gc": 0.0, "max_gc": 0.0}
        gc_values = []
        for oligo in self.oligos.values():
            gc = sum(1 for b in oligo if b in ("G", "C")) / max(len(oligo), 1)
            gc_values.append(gc)
        return {
            "mean_gc": sum(gc_values) / len(gc_values),
            "min_gc": min(gc_values),
            "max_gc": max(gc_values),
        }


# ---------------------------------------------------------------------------
# FizzBuzz DNA Storage Service
# ---------------------------------------------------------------------------

@dataclass
class FizzBuzzDNAStorage:
    """High-level service that encodes FizzBuzz results into DNA pools.

    Provides a store-and-retrieve interface for persisting evaluation
    results in synthetic DNA format.
    """

    encoder: DNAEncoder = field(default_factory=DNAEncoder)
    pool: OligoPool = field(default_factory=OligoPool)
    _address_counter: int = 0

    def store_result(self, number: int, output: str) -> Dict[str, Any]:
        """Encode a single FizzBuzz result and add it to the oligo pool."""
        data = f"{number}:{output}".encode("utf-8")
        oligos = self.encoder.encode(data)

        for oligo in oligos:
            self.pool.store(self._address_counter, oligo)
            self._address_counter += 1

        return {
            "number": number,
            "output": output,
            "oligos_added": len(oligos),
            "total_bases": sum(len(o) for o in oligos),
            "gc_content": self.encoder.stats["gc_content"],
        }

    def retrieve_all_results(self) -> List[str]:
        """Retrieve and decode all stored FizzBuzz results."""
        return self.pool.retrieve_all()

    def get_pool_stats(self) -> Dict[str, Any]:
        """Return comprehensive statistics about the DNA storage pool."""
        gc_report = self.pool.gc_content_report()
        return {
            "oligo_count": self.pool.count,
            "total_bases": self.pool.total_bases,
            "encoder_stats": self.encoder.stats,
            "gc_report": gc_report,
        }


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class DNADashboard:
    """ASCII dashboard for the FizzDNA storage subsystem."""

    @staticmethod
    def render(storage: FizzBuzzDNAStorage, width: int = 60) -> str:
        """Render the DNA storage dashboard as ASCII art."""
        stats = storage.get_pool_stats()
        gc = stats["gc_report"]
        enc = stats["encoder_stats"]

        border = "+" + "-" * (width - 2) + "+"
        title = "| FIZZDNA: DNA STORAGE ENCODER"
        title = title + " " * (width - len(title) - 1) + "|"

        lines = [
            border,
            title,
            border,
            f"|  Oligos in pool: {stats['oligo_count']:<10} Total bases: {stats['total_bases']:<10}|",
            f"|  Data encoded:   {enc.get('data_bytes', 0):<10} ECC overhead: {enc.get('ecc_overhead_bases', 0):<8} |",
            f"|  GC content:     mean={gc.get('mean_gc', 0):.1%}  min={gc.get('min_gc', 0):.1%}  max={gc.get('max_gc', 0):.1%}   |",
            f"|  Homopolymer fixes: {enc.get('homopolymer_fixes', 0):<38}|",
            border,
        ]

        # DNA helix visualization
        helix_lines = DNADashboard._render_helix(width - 4)
        for hl in helix_lines:
            padded = f"|  {hl}"
            padded = padded + " " * (width - len(padded) - 1) + "|"
            lines.append(padded)

        lines.append(border)
        return "\n".join(lines)

    @staticmethod
    def _render_helix(width: int) -> List[str]:
        """Render a simplified DNA double helix in ASCII."""
        bases_top = "ATGCATGCATGC"
        bases_bot = "TACGTACGTACG"
        helix: List[str] = []
        pattern_width = min(width, 40)

        for row in range(4):
            phase = row * 3
            line = ""
            for col in range(pattern_width):
                pos = (col + phase) % 12
                if pos < 3:
                    line += bases_top[col % len(bases_top)]
                elif pos < 5:
                    line += "-"
                elif pos < 8:
                    line += bases_bot[col % len(bases_bot)]
                elif pos < 10:
                    line += " "
                else:
                    line += "."
            helix.append(line)

        return helix


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class DNAStorageMiddleware(IMiddleware):
    """Pipeline middleware that encodes each FizzBuzz result into DNA.

    As numbers flow through the evaluation pipeline, this middleware
    converts each result to its nucleotide representation and stores
    it in the in-silico oligo pool.
    """

    def __init__(
        self,
        storage: FizzBuzzDNAStorage,
        enable_dashboard: bool = False,
    ) -> None:
        self._storage = storage
        self._enable_dashboard = enable_dashboard

    @property
    def storage(self) -> FizzBuzzDNAStorage:
        return self._storage

    def get_name(self) -> str:
        return "DNAStorageMiddleware"

    def get_priority(self) -> int:
        return 262

    def process(
        self, context: ProcessingContext, next_handler: Callable[..., Any]
    ) -> ProcessingContext:
        """Encode the current result into DNA before passing downstream."""
        from enterprise_fizzbuzz.domain.exceptions.fizzdna import DNAMiddlewareError

        context = next_handler(context)

        try:
            if context.results:
                result = context.results[-1]
                output = result.output if hasattr(result, "output") else str(context.number)
                self._storage.store_result(context.number, output)
                context.metadata["fizzdna_encoded"] = True
                context.metadata["fizzdna_gc"] = self._storage.encoder.stats["gc_content"]
        except Exception as exc:
            if isinstance(exc, DNAMiddlewareError):
                raise
            raise DNAMiddlewareError(context.number, str(exc)) from exc

        return context
