"""
Enterprise FizzBuzz Platform - Blockchain-Based Immutable Audit Ledger

Provides a tamper-proof, cryptographically verified audit trail for every
FizzBuzz evaluation performed by the platform. Because if there is one thing
the world needs, it is blockchain-backed proof that 15 is divisible by both
3 and 5.

Compliance frameworks supported:
    - SOX (Sarbanes-Oxley Act) Section 404: Internal controls over FizzBuzz reporting
    - GDPR Article 30: Records of FizzBuzz processing activities
    - The FizzBuzz Accountability Act of 2024: Mandates immutable audit trails
      for all modulo-arithmetic operations performed in enterprise contexts
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from interfaces import IObserver
from models import Event, EventType

logger = logging.getLogger(__name__)


@dataclass
class Block:
    """A single block in the FizzBuzz blockchain.

    Each block contains an immutable record of a FizzBuzz evaluation,
    cryptographically linked to the previous block via SHA-256 hashing.
    """

    index: int
    timestamp: float
    data: dict
    previous_hash: str
    nonce: int = 0
    hash: str = ""

    def compute_hash(self) -> str:
        """Compute the SHA-256 hash of this block's contents."""
        block_string = (
            str(self.index)
            + str(self.timestamp)
            + json.dumps(self.data, sort_keys=True, default=str)
            + self.previous_hash
            + str(self.nonce)
        )
        return hashlib.sha256(block_string.encode()).hexdigest()


class FizzBuzzBlockchain:
    """A proof-of-work blockchain for immutable FizzBuzz audit logging.

    Every FizzBuzz result is permanently recorded in a chain of
    cryptographically linked blocks. Tampering with any historical
    result will invalidate the entire chain, ensuring the highest
    level of FizzBuzz accountability.
    """

    def __init__(self, difficulty: int = 2) -> None:
        self.difficulty = difficulty
        self.chain: list[Block] = []
        self._lock = threading.Lock()
        self._total_mining_time_ms: float = 0.0

        if difficulty > 4:
            logger.warning(
                "Mining difficulty set to %d. This may cause significant delays. "
                "Consider whether your FizzBuzz results truly require "
                "this level of cryptographic commitment.",
                difficulty,
            )

        self._create_genesis_block()

    def _create_genesis_block(self) -> None:
        """Create the genesis block for the FizzBuzz blockchain."""
        genesis = Block(
            index=0,
            timestamp=time.time(),
            data={
                "genesis": "Enterprise FizzBuzz Blockchain Initialized",
                "version": "1.0.0",
            },
            previous_hash="0" * 64,
        )
        self._mine_block(genesis)
        self.chain.append(genesis)

    def _mine_block(self, block: Block) -> None:
        """Perform proof-of-work mining on a block.

        Incrementally searches for a nonce that produces a hash
        with the required number of leading zeros.
        """
        target = "0" * self.difficulty
        logger.info(
            "Mining block #%d with difficulty %d...",
            block.index,
            self.difficulty,
        )
        start_time = time.perf_counter()

        while True:
            block.hash = block.compute_hash()
            if block.hash.startswith(target):
                break
            block.nonce += 1

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        self._total_mining_time_ms += elapsed_ms

        logger.info(
            "Block #%d mined: nonce=%d, hash=%s, time=%.2fms",
            block.index,
            block.nonce,
            block.hash,
            elapsed_ms,
        )

    def add_block(self, data: dict) -> Block:
        """Add a new block to the chain with the given data. Thread-safe."""
        with self._lock:
            previous_block = self.chain[-1]
            new_block = Block(
                index=len(self.chain),
                timestamp=time.time(),
                data=data,
                previous_hash=previous_block.hash,
            )
            self._mine_block(new_block)
            self.chain.append(new_block)
            return new_block

    def validate_chain(self) -> bool:
        """Validate the integrity of the entire blockchain.

        Checks that each block's hash is correct and that the
        previous_hash links are consistent.
        """
        for i in range(1, len(self.chain)):
            current = self.chain[i]
            previous = self.chain[i - 1]

            if current.hash != current.compute_hash():
                logger.error(
                    "Blockchain integrity violation: block #%d hash mismatch",
                    current.index,
                )
                return False

            if current.previous_hash != previous.hash:
                logger.error(
                    "Blockchain integrity violation: block #%d previous_hash "
                    "does not match block #%d hash",
                    current.index,
                    previous.index,
                )
                return False

        logger.info("Blockchain validation passed. All %d blocks verified.", len(self.chain))
        return True

    def get_block(self, index: int) -> Block:
        """Retrieve a block by index."""
        return self.chain[index]

    def get_chain_length(self) -> int:
        """Return the number of blocks in the chain."""
        return len(self.chain)

    def get_total_mining_time_ms(self) -> float:
        """Return the total time spent mining in milliseconds."""
        return self._total_mining_time_ms

    def get_chain_summary(self) -> str:
        """Return a formatted summary of the blockchain state."""
        is_valid = self.validate_chain()
        integrity = "VALID" if is_valid else "COMPROMISED"

        genesis_hash = self.chain[0].hash if self.chain else "N/A"
        latest_hash = self.chain[-1].hash if self.chain else "N/A"

        lines = [
            "",
            "  +===========================================================+",
            "  |              BLOCKCHAIN AUDIT LEDGER SUMMARY              |",
            "  +===========================================================+",
            f"  |  Chain Length    : {self.get_chain_length():<39}|",
            f"  |  Mining Time    : {self._total_mining_time_ms:<35.2f}ms  |",
            f"  |  Integrity      : {integrity:<39}|",
            f"  |  Difficulty     : {self.difficulty:<39}|",
            f"  |  Genesis Hash   : {genesis_hash[:32]}... |",
            f"  |  Latest Hash    : {latest_hash[:32]}... |",
            "  +===========================================================+",
            "",
        ]
        return "\n".join(lines)


class BlockchainObserver(IObserver):
    """Observer that records FizzBuzz events to the blockchain audit ledger.

    Listens for NUMBER_PROCESSED events and creates an immutable
    blockchain record for each one, because every FizzBuzz evaluation
    deserves the same level of cryptographic security as a financial
    transaction.
    """

    def __init__(self, blockchain: Optional[FizzBuzzBlockchain] = None) -> None:
        self._blockchain = blockchain or FizzBuzzBlockchain()

    def on_event(self, event: Event) -> None:
        """Record NUMBER_PROCESSED events to the blockchain."""
        if event.event_type == EventType.NUMBER_PROCESSED:
            self._blockchain.add_block(event.payload)

    def get_name(self) -> str:
        """Return the observer's identifier."""
        return "BlockchainAuditObserver"

    def get_blockchain(self) -> FizzBuzzBlockchain:
        """Return the underlying blockchain instance."""
        return self._blockchain
