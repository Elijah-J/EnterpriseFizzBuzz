"""Feature descriptor for the distributed Paxos consensus subsystem."""

from __future__ import annotations

import random
from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class PaxosFeature(FeatureDescriptor):
    name = "paxos"
    description = "Distributed Paxos consensus for multi-node FizzBuzz evaluation with Byzantine fault injection"
    middleware_priority = 41
    cli_flags = [
        ("--paxos", {"action": "store_true", "default": False,
                     "help": "Enable Distributed Paxos Consensus for multi-node FizzBuzz evaluation"}),
        ("--paxos-nodes", {"type": int, "default": None, "metavar": "N",
                           "help": "Number of Paxos cluster nodes (default: from config, typically 5)"}),
        ("--paxos-byzantine", {"action": "store_true", "default": False,
                               "help": "Enable Byzantine fault injection (one node lies about its FizzBuzz evaluation)"}),
        ("--paxos-dashboard", {"action": "store_true", "default": False,
                               "help": "Display the Paxos Consensus ASCII dashboard after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "paxos", False) or getattr(args, "paxos_dashboard", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.paxos import (
            ByzantineFaultInjector,
            NetworkPartitionSimulator,
            PaxosCluster,
            PaxosMesh,
            PaxosMiddleware,
        )

        num_nodes = getattr(args, "paxos_nodes", None) or config.paxos_num_nodes
        mesh = PaxosMesh(
            delay_ms=config.paxos_message_delay_ms,
            drop_rate=config.paxos_message_drop_rate,
        )

        cluster = PaxosCluster(
            num_nodes=num_nodes,
            rules=config.rules,
            mesh=mesh,
            event_callback=event_bus.publish if event_bus else None,
        )

        byzantine_node_id = None
        if getattr(args, "paxos_byzantine", False) or config.paxos_byzantine_mode:
            injector = ByzantineFaultInjector(cluster)
            byzantine_node_id = injector.inject(
                node_index=-1,
                lie_probability=config.paxos_byzantine_lie_probability,
            )

        if config.paxos_partition_enabled:
            partition_sim = NetworkPartitionSimulator(cluster)
            partition_sim.partition(config.paxos_partition_groups)

        middleware = PaxosMiddleware(cluster=cluster)

        # Store byzantine_node_id on the cluster for dashboard rendering
        cluster._byzantine_node_id = byzantine_node_id

        byz_status = f"node {byzantine_node_id}" if byzantine_node_id is not None else "NONE"
        print(
            "  +---------------------------------------------------------+\n"
            "  | PAXOS CONSENSUS: Distributed FizzBuzz ENABLED           |\n"
            f"  | Nodes: {num_nodes:<49}|\n"
            f"  | Quorum: {cluster.quorum_size:<48}|\n"
            f"  | Byzantine traitor: {byz_status:<37}|\n"
            "  | Every number will be evaluated by ALL nodes and then    |\n"
            "  | ratified through Lamport's Paxos protocol. Because one  |\n"
            "  | modulo operation is never enough for enterprise.        |\n"
            "  +---------------------------------------------------------+"
        )

        return cluster, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        if not getattr(args, "paxos_dashboard", False):
            return None
        from enterprise_fizzbuzz.infrastructure.paxos import ConsensusDashboard
        cluster = middleware._cluster if hasattr(middleware, "_cluster") else None
        if cluster is None:
            return None
        byzantine_node_id = getattr(cluster, "_byzantine_node_id", None)
        return ConsensusDashboard.render(
            cluster,
            width=60,
            byzantine_node_id=byzantine_node_id,
        )
