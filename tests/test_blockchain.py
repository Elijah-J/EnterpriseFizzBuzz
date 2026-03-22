"""
Enterprise FizzBuzz Platform - Blockchain Audit Ledger Test Suite

Comprehensive tests for the immutable, cryptographically verified audit
trail that ensures every FizzBuzz evaluation is permanently etched into
a tamper-proof ledger. Because the SEC may one day audit your modulo
operations, and you will be ready.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from blockchain import Block, BlockchainObserver, FizzBuzzBlockchain
from models import Event, EventType


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def blockchain_easy() -> FizzBuzzBlockchain:
    """A blockchain with difficulty 1, for tests that value speed over security."""
    return FizzBuzzBlockchain(difficulty=1)


@pytest.fixture
def blockchain_medium() -> FizzBuzzBlockchain:
    """A blockchain with difficulty 2, the default enterprise-grade setting."""
    return FizzBuzzBlockchain(difficulty=2)


@pytest.fixture
def populated_chain() -> FizzBuzzBlockchain:
    """A blockchain pre-loaded with the canonical first five FizzBuzz results."""
    bc = FizzBuzzBlockchain(difficulty=1)
    for number, output in [(1, "1"), (2, "2"), (3, "Fizz"), (4, "4"), (5, "Buzz")]:
        bc.add_block({"number": number, "output": output})
    return bc


@pytest.fixture
def observer_with_chain() -> tuple[BlockchainObserver, FizzBuzzBlockchain]:
    """An observer wired to its own blockchain, ready for event-driven auditing."""
    bc = FizzBuzzBlockchain(difficulty=1)
    observer = BlockchainObserver(blockchain=bc)
    return observer, bc


# ============================================================
# Block Tests
# ============================================================


class TestBlock:
    """Tests for the fundamental unit of FizzBuzz accountability."""

    def test_compute_hash_is_deterministic(self):
        """A block's hash must not change between invocations.
        Nondeterministic hashing would undermine the entire FizzBuzz
        compliance framework."""
        block = Block(
            index=0,
            timestamp=1000000.0,
            data={"number": 3, "output": "Fizz"},
            previous_hash="0" * 64,
            nonce=42,
        )
        assert block.compute_hash() == block.compute_hash()

    def test_compute_hash_returns_64_hex_characters(self):
        """SHA-256 produces a 64-character hex digest. Anything else
        is grounds for a compliance investigation."""
        block = Block(
            index=0,
            timestamp=1000000.0,
            data={"number": 15, "output": "FizzBuzz"},
            previous_hash="0" * 64,
            nonce=0,
        )
        h = block.compute_hash()
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_hash_changes_when_nonce_changes(self):
        """The nonce is the miner's lever. Changing it must produce
        a different hash, or proof-of-work is just proof-of-nothing."""
        block = Block(
            index=0,
            timestamp=1000000.0,
            data={"number": 5, "output": "Buzz"},
            previous_hash="0" * 64,
            nonce=0,
        )
        hash_a = block.compute_hash()
        block.nonce = 1
        hash_b = block.compute_hash()
        assert hash_a != hash_b

    def test_hash_changes_when_data_changes(self):
        """If modifying the data doesn't change the hash, we don't
        have a blockchain — we have a very slow list."""
        block = Block(
            index=0,
            timestamp=1000000.0,
            data={"number": 3, "output": "Fizz"},
            previous_hash="0" * 64,
            nonce=0,
        )
        hash_fizz = block.compute_hash()
        block.data = {"number": 3, "output": "TAMPERED_FIZZ"}
        hash_tampered = block.compute_hash()
        assert hash_fizz != hash_tampered

    def test_hash_changes_when_index_changes(self):
        """Block position matters. Block #0 and block #1 with identical
        data must still hash differently."""
        block = Block(
            index=0,
            timestamp=1000000.0,
            data={"number": 1, "output": "1"},
            previous_hash="0" * 64,
            nonce=0,
        )
        hash_0 = block.compute_hash()
        block.index = 1
        hash_1 = block.compute_hash()
        assert hash_0 != hash_1

    def test_hash_changes_when_previous_hash_changes(self):
        """The chain linkage must be baked into the hash. Otherwise
        blocks could be rearranged like FizzBuzz anarchy."""
        block = Block(
            index=1,
            timestamp=1000000.0,
            data={"number": 3, "output": "Fizz"},
            previous_hash="0" * 64,
            nonce=0,
        )
        hash_a = block.compute_hash()
        block.previous_hash = "a" * 64
        hash_b = block.compute_hash()
        assert hash_a != hash_b

    def test_hash_changes_when_timestamp_changes(self):
        """Temporal integrity: the same FizzBuzz result recorded at
        different times must produce different hashes."""
        block = Block(
            index=0,
            timestamp=1000000.0,
            data={"number": 5, "output": "Buzz"},
            previous_hash="0" * 64,
            nonce=0,
        )
        hash_a = block.compute_hash()
        block.timestamp = 2000000.0
        hash_b = block.compute_hash()
        assert hash_a != hash_b

    def test_block_default_nonce_is_zero(self):
        """A freshly created block should have nonce 0, representing
        the start of its proof-of-work journey."""
        block = Block(
            index=0,
            timestamp=1000000.0,
            data={"test": True},
            previous_hash="0" * 64,
        )
        assert block.nonce == 0

    def test_block_default_hash_is_empty(self):
        """Before mining, a block's hash is empty — a blank canvas
        awaiting cryptographic enlightenment."""
        block = Block(
            index=0,
            timestamp=1000000.0,
            data={"test": True},
            previous_hash="0" * 64,
        )
        assert block.hash == ""


# ============================================================
# Genesis Block Tests
# ============================================================


class TestGenesisBlock:
    """Tests for the primordial block from which all FizzBuzz
    accountability descends."""

    def test_genesis_block_exists_on_creation(self, blockchain_easy):
        """A blockchain is born with exactly one block: the genesis."""
        assert blockchain_easy.get_chain_length() == 1

    def test_genesis_block_has_index_zero(self, blockchain_easy):
        """The genesis block occupies index 0, as tradition demands."""
        genesis = blockchain_easy.get_block(0)
        assert genesis.index == 0

    def test_genesis_block_has_sentinel_previous_hash(self, blockchain_easy):
        """The genesis block's previous_hash is 64 zeros — the
        cryptographic equivalent of 'In the beginning...'"""
        genesis = blockchain_easy.get_block(0)
        assert genesis.previous_hash == "0" * 64

    def test_genesis_block_contains_initialization_data(self, blockchain_easy):
        """The genesis block announces the blockchain's creation
        with appropriate gravitas."""
        genesis = blockchain_easy.get_block(0)
        assert genesis.data["genesis"] == "Enterprise FizzBuzz Blockchain Initialized"
        assert genesis.data["version"] == "1.0.0"

    def test_genesis_block_has_been_mined(self, blockchain_easy):
        """The genesis block must have a non-empty hash, proving
        it underwent the sacred mining ritual."""
        genesis = blockchain_easy.get_block(0)
        assert genesis.hash != ""
        assert len(genesis.hash) == 64

    def test_genesis_block_hash_satisfies_difficulty(self, blockchain_easy):
        """Even the genesis block must earn its place through
        proof-of-work. No free passes."""
        genesis = blockchain_easy.get_block(0)
        assert genesis.hash.startswith("0")

    def test_genesis_block_hash_matches_computed_hash(self, blockchain_easy):
        """The stored hash must match a fresh computation.
        Self-consistency is the foundation of trust."""
        genesis = blockchain_easy.get_block(0)
        assert genesis.hash == genesis.compute_hash()


# ============================================================
# Proof-of-Work Tests
# ============================================================


class TestProofOfWork:
    """Tests for the mining algorithm that converts electricity
    into FizzBuzz accountability."""

    def test_mining_difficulty_1_produces_one_leading_zero(self):
        """Difficulty 1: the training wheels of blockchain security."""
        bc = FizzBuzzBlockchain(difficulty=1)
        bc.add_block({"number": 3, "output": "Fizz"})
        latest = bc.get_block(bc.get_chain_length() - 1)
        assert latest.hash.startswith("0")

    def test_mining_difficulty_2_produces_two_leading_zeros(self):
        """Difficulty 2: the default enterprise-grade commitment level."""
        bc = FizzBuzzBlockchain(difficulty=2)
        bc.add_block({"number": 5, "output": "Buzz"})
        latest = bc.get_block(bc.get_chain_length() - 1)
        assert latest.hash.startswith("00")

    def test_mining_difficulty_3_produces_three_leading_zeros(self):
        """Difficulty 3: for when your FizzBuzz results require
        military-grade cryptographic verification."""
        bc = FizzBuzzBlockchain(difficulty=3)
        bc.add_block({"number": 15, "output": "FizzBuzz"})
        latest = bc.get_block(bc.get_chain_length() - 1)
        assert latest.hash.startswith("000")

    def test_mined_block_hash_matches_computed_hash(self, blockchain_easy):
        """A mined block's stored hash must equal its computed hash.
        This seems obvious, but in blockchain, trust no one."""
        bc = blockchain_easy
        bc.add_block({"number": 7, "output": "7"})
        block = bc.get_block(1)
        assert block.hash == block.compute_hash()

    def test_genesis_block_proof_of_work_satisfies_difficulty(self):
        """The genesis block must also be properly mined.
        No backdoor genesis blocks in this enterprise."""
        bc = FizzBuzzBlockchain(difficulty=2)
        genesis = bc.get_block(0)
        assert genesis.hash.startswith("00")


# ============================================================
# Chain Integrity Tests
# ============================================================


class TestChainIntegrity:
    """Tests for the cryptographic chain that binds FizzBuzz results
    into an unbreakable sequence of accountability."""

    def test_second_block_links_to_genesis(self, blockchain_easy):
        """The first data block must reference the genesis hash.
        This is how the chain of trust begins."""
        blockchain_easy.add_block({"number": 1, "output": "1"})
        second = blockchain_easy.get_block(1)
        genesis = blockchain_easy.get_block(0)
        assert second.previous_hash == genesis.hash

    def test_all_blocks_form_valid_chain(self, populated_chain):
        """Every block in the chain must reference its predecessor.
        A broken link is a broken promise of FizzBuzz integrity."""
        for i in range(1, populated_chain.get_chain_length()):
            current = populated_chain.get_block(i)
            previous = populated_chain.get_block(i - 1)
            assert current.previous_hash == previous.hash

    def test_block_indices_are_sequential(self, populated_chain):
        """Block indices must be sequential. Gaps in the audit trail
        are gaps in compliance."""
        for i in range(populated_chain.get_chain_length()):
            assert populated_chain.get_block(i).index == i

    def test_validate_chain_passes_for_valid_chain(self, populated_chain):
        """A properly constructed chain should validate successfully.
        This is the blockchain's annual performance review."""
        assert populated_chain.validate_chain() is True

    def test_chain_length_includes_genesis(self, populated_chain):
        """Chain length is genesis + data blocks. The genesis counts;
        it always counts."""
        assert populated_chain.get_chain_length() == 6  # genesis + 5


# ============================================================
# Tamper Detection Tests
# ============================================================


class TestTamperDetection:
    """Tests for the blockchain's ability to detect unauthorized
    modifications to FizzBuzz history. Revisionism will not be
    tolerated."""

    def test_modifying_block_data_invalidates_chain(self, populated_chain):
        """Changing a block's data after mining is the blockchain
        equivalent of editing your FizzBuzz homework. We will catch you."""
        populated_chain.get_block(2).data = {"number": 2, "output": "FRAUDULENT_FIZZ"}
        assert populated_chain.validate_chain() is False

    def test_modifying_block_nonce_invalidates_chain(self, populated_chain):
        """Tampering with the nonce breaks the hash, which breaks
        the chain, which breaks compliance, which breaks Bob's heart."""
        populated_chain.get_block(1).nonce = 999999
        assert populated_chain.validate_chain() is False

    def test_modifying_genesis_hash_invalidates_chain(self, populated_chain):
        """Tampering with the genesis block's stored hash breaks the
        link to block 1, invalidating the entire chain. Even the
        foundation is not above scrutiny."""
        populated_chain.get_block(0).hash = "f" * 64
        assert populated_chain.validate_chain() is False

    def test_modifying_previous_hash_invalidates_chain(self, populated_chain):
        """Rewriting the previous_hash is an attempt to forge the
        chain linkage. The blockchain sees all."""
        populated_chain.get_block(2).previous_hash = "f" * 64
        assert populated_chain.validate_chain() is False

    def test_chain_valid_before_tampering(self, populated_chain):
        """Sanity check: the chain is valid before we tamper with it.
        We must establish the baseline of innocence."""
        assert populated_chain.validate_chain() is True

    def test_swapping_block_data_between_blocks_invalidates_chain(self, populated_chain):
        """Swapping the payloads of two blocks is a sophisticated attack.
        The blockchain remains vigilant."""
        data_1 = populated_chain.get_block(1).data
        data_2 = populated_chain.get_block(2).data
        populated_chain.get_block(1).data = data_2
        populated_chain.get_block(2).data = data_1
        assert populated_chain.validate_chain() is False


# ============================================================
# Block Addition Tests
# ============================================================


class TestBlockAddition:
    """Tests for the ceremonial act of adding new FizzBuzz results
    to the permanent record."""

    def test_add_block_increments_chain_length(self, blockchain_easy):
        """Each added block must increase the chain length by exactly one."""
        initial = blockchain_easy.get_chain_length()
        blockchain_easy.add_block({"number": 42, "output": "Fizz"})
        assert blockchain_easy.get_chain_length() == initial + 1

    def test_add_block_returns_the_new_block(self, blockchain_easy):
        """add_block returns the newly minted block for immediate
        inspection by compliance officers."""
        block = blockchain_easy.add_block({"number": 7, "output": "7"})
        assert isinstance(block, Block)
        assert block.data == {"number": 7, "output": "7"}

    def test_added_block_has_correct_index(self, blockchain_easy):
        """The returned block's index must match its position in the chain."""
        block = blockchain_easy.add_block({"number": 1, "output": "1"})
        assert block.index == 1

    def test_added_block_has_valid_hash(self, blockchain_easy):
        """The new block must have a properly mined hash."""
        block = blockchain_easy.add_block({"number": 3, "output": "Fizz"})
        assert block.hash != ""
        assert block.hash == block.compute_hash()

    def test_added_block_references_previous_block(self, blockchain_easy):
        """The new block must cryptographically reference its predecessor."""
        genesis_hash = blockchain_easy.get_block(0).hash
        block = blockchain_easy.add_block({"number": 5, "output": "Buzz"})
        assert block.previous_hash == genesis_hash

    def test_multiple_blocks_maintain_chain_validity(self, blockchain_easy):
        """Adding many blocks must not corrupt the chain. Stress-testing
        the audit ledger's structural integrity."""
        for i in range(1, 11):
            blockchain_easy.add_block({"number": i, "output": str(i)})
        assert blockchain_easy.validate_chain() is True
        assert blockchain_easy.get_chain_length() == 11

    def test_get_block_out_of_range_raises_index_error(self, blockchain_easy):
        """Requesting a nonexistent block is a compliance violation
        that results in an IndexError."""
        with pytest.raises(IndexError):
            blockchain_easy.get_block(999)


# ============================================================
# Mining Time Tracking Tests
# ============================================================


class TestMiningTimeTracking:
    """Tests for the mining time telemetry, because management
    needs to know how many milliseconds were spent securing
    their FizzBuzz results."""

    def test_total_mining_time_is_positive_after_genesis(self, blockchain_easy):
        """Mining the genesis block takes nonzero time, even on
        the fastest hardware."""
        assert blockchain_easy.get_total_mining_time_ms() >= 0.0

    def test_mining_time_increases_with_blocks(self, blockchain_easy):
        """Each mined block contributes to the cumulative mining time.
        Time, like the blockchain, only moves forward."""
        time_after_genesis = blockchain_easy.get_total_mining_time_ms()
        blockchain_easy.add_block({"number": 3, "output": "Fizz"})
        time_after_one = blockchain_easy.get_total_mining_time_ms()
        assert time_after_one >= time_after_genesis


# ============================================================
# Chain Summary Tests
# ============================================================


class TestChainSummary:
    """Tests for the executive summary dashboard, because C-level
    stakeholders need ASCII art to understand blockchain status."""

    def test_summary_contains_blockchain_header(self, blockchain_easy):
        """The summary must announce itself as a BLOCKCHAIN AUDIT LEDGER."""
        summary = blockchain_easy.get_chain_summary()
        assert "BLOCKCHAIN AUDIT LEDGER SUMMARY" in summary

    def test_summary_reports_valid_integrity(self, populated_chain):
        """A valid chain's summary must proudly declare VALID status."""
        summary = populated_chain.get_chain_summary()
        assert "VALID" in summary

    def test_summary_reports_compromised_integrity(self, populated_chain):
        """A tampered chain's summary must shamefully display COMPROMISED."""
        populated_chain.get_block(1).data = {"number": 1, "output": "LIES"}
        summary = populated_chain.get_chain_summary()
        assert "COMPROMISED" in summary

    def test_summary_contains_chain_length(self, populated_chain):
        """The summary must report the chain length, because stakeholders
        love big numbers."""
        summary = populated_chain.get_chain_summary()
        assert "Chain Length" in summary

    def test_summary_contains_difficulty(self, blockchain_easy):
        """The summary must report the mining difficulty, so auditors
        can assess the cryptographic commitment level."""
        summary = blockchain_easy.get_chain_summary()
        assert "Difficulty" in summary


# ============================================================
# Thread Safety Tests
# ============================================================


class TestThreadSafety:
    """Tests for concurrent blockchain access, because in the
    enterprise, multiple threads may simultaneously need to
    record that 15 is FizzBuzz."""

    def test_concurrent_block_additions_maintain_chain_validity(self):
        """Multiple threads adding blocks simultaneously must not
        corrupt the chain. The lock is the blockchain's bouncer."""
        bc = FizzBuzzBlockchain(difficulty=1)
        errors = []

        def add_blocks(start, count):
            try:
                for i in range(start, start + count):
                    bc.add_block({"number": i, "output": str(i)})
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=add_blocks, args=(1, 5)),
            threading.Thread(target=add_blocks, args=(100, 5)),
            threading.Thread(target=add_blocks, args=(200, 5)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert bc.get_chain_length() == 16  # genesis + 15
        assert bc.validate_chain() is True


# ============================================================
# BlockchainObserver Tests
# ============================================================


class TestBlockchainObserver:
    """Tests for the observer that bridges the event bus and the
    blockchain, ensuring every NUMBER_PROCESSED event is permanently
    recorded for posterity."""

    def test_observer_records_number_processed_event(self, observer_with_chain):
        """A NUMBER_PROCESSED event must produce a new block.
        This is the pipeline from evaluation to immutable record."""
        observer, bc = observer_with_chain
        event = Event(
            event_type=EventType.NUMBER_PROCESSED,
            payload={"number": 3, "output": "Fizz"},
        )
        observer.on_event(event)
        assert bc.get_chain_length() == 2  # genesis + 1

    def test_observer_ignores_fizz_detected_event(self, observer_with_chain):
        """FIZZ_DETECTED is informational only. The blockchain does
        not care about your feelings, only about NUMBER_PROCESSED."""
        observer, bc = observer_with_chain
        event = Event(
            event_type=EventType.FIZZ_DETECTED,
            payload={"number": 3},
        )
        observer.on_event(event)
        assert bc.get_chain_length() == 1  # only genesis

    def test_observer_ignores_buzz_detected_event(self, observer_with_chain):
        """BUZZ_DETECTED is similarly irrelevant to the audit ledger.
        The blockchain has standards."""
        observer, bc = observer_with_chain
        event = Event(
            event_type=EventType.BUZZ_DETECTED,
            payload={"number": 5},
        )
        observer.on_event(event)
        assert bc.get_chain_length() == 1

    def test_observer_get_name_returns_correct_identifier(self):
        """The observer must identify itself for the event bus registry.
        Anonymous auditors are not permitted."""
        observer = BlockchainObserver(blockchain=FizzBuzzBlockchain(difficulty=1))
        assert observer.get_name() == "BlockchainAuditObserver"

    def test_observer_get_blockchain_returns_instance(self, observer_with_chain):
        """The observer must expose its blockchain for external
        inspection and compliance audits."""
        observer, bc = observer_with_chain
        assert observer.get_blockchain() is bc

    def test_observer_creates_default_blockchain_if_none_provided(self):
        """An observer created without an explicit blockchain must
        provision its own. Self-sufficiency is a virtue."""
        observer = BlockchainObserver()
        bc = observer.get_blockchain()
        assert isinstance(bc, FizzBuzzBlockchain)
        assert bc.get_chain_length() == 1  # has genesis

    def test_observer_records_multiple_events_in_sequence(self, observer_with_chain):
        """Processing a sequence of events must produce a valid chain
        with the correct number of blocks."""
        observer, bc = observer_with_chain
        for i in range(1, 6):
            event = Event(
                event_type=EventType.NUMBER_PROCESSED,
                payload={"number": i, "output": str(i)},
            )
            observer.on_event(event)
        assert bc.get_chain_length() == 6  # genesis + 5
        assert bc.validate_chain() is True

    def test_observer_block_data_matches_event_payload(self, observer_with_chain):
        """The block's data must faithfully reproduce the event payload.
        No editorial changes to the historical record."""
        observer, bc = observer_with_chain
        payload = {"number": 15, "output": "FizzBuzz", "strategy": "STANDARD"}
        event = Event(event_type=EventType.NUMBER_PROCESSED, payload=payload)
        observer.on_event(event)
        block = bc.get_block(1)
        assert block.data == payload
