"""Feature descriptor for the peer-to-peer gossip network."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class P2PNetworkFeature(FeatureDescriptor):
    name = "p2p_network"
    description = "Distributed FizzBuzz dissemination via SWIM failure detection and Kademlia DHT"
    middleware_priority = 55
    cli_flags = [
        ("--p2p", {"action": "store_true",
                   "help": "Enable the Peer-to-Peer Gossip Network: disseminate FizzBuzz results across 7 simulated nodes via SWIM and Kademlia"}),
        ("--p2p-nodes", {"type": int, "default": None, "metavar": "N",
                         "help": "Number of P2P cluster nodes (default: from config, typically 7)"}),
        ("--p2p-dashboard", {"action": "store_true",
                             "help": "Display the P2P Gossip Network ASCII dashboard after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "p2p", False),
            getattr(args, "p2p_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.p2p_network import (
            P2PMiddleware,
            P2PNetwork,
        )

        p2p_num_nodes = getattr(args, "p2p_nodes", None) or config.p2p_num_nodes

        network = P2PNetwork(
            num_nodes=p2p_num_nodes,
            k_bucket_size=config.p2p_k_bucket_size,
            gossip_fanout=config.p2p_gossip_fanout,
            suspect_timeout_rounds=config.p2p_suspect_timeout_rounds,
            max_gossip_rounds=config.p2p_max_gossip_rounds,
            event_bus=event_bus,
        )

        network.bootstrap()

        middleware = P2PMiddleware(
            network=network,
            event_bus=event_bus,
        )

        return network, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "p2p_dashboard", False):
            return None
        if middleware is None:
            return None
        from enterprise_fizzbuzz.infrastructure.p2p_network import P2PDashboard
        return P2PDashboard.render(
            middleware._network,
            width=60,
        )
