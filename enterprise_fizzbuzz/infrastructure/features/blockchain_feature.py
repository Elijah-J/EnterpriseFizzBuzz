"""Feature descriptor for the Blockchain immutable audit ledger."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class BlockchainFeature(FeatureDescriptor):
    name = "blockchain"
    description = "Blockchain-based immutable audit ledger for tamper-proof compliance"
    middleware_priority = 100
    cli_flags = [
        ("--blockchain", {"action": "store_true",
                          "help": "Enable blockchain-based immutable audit ledger for tamper-proof compliance"}),
        ("--mining-difficulty", {"type": int, "default": 2, "metavar": "N",
                                 "help": "Proof-of-work difficulty for blockchain mining (default: 2)"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "blockchain", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.blockchain import BlockchainObserver, FizzBuzzBlockchain

        blockchain = FizzBuzzBlockchain(difficulty=args.mining_difficulty)
        blockchain_observer = BlockchainObserver(blockchain=blockchain)
        if event_bus is not None:
            event_bus.subscribe(blockchain_observer)
        return blockchain_observer, None
