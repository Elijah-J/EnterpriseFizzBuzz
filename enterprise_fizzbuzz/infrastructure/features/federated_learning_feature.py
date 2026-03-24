"""Feature descriptor for the federated learning subsystem."""

from __future__ import annotations

import random
from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FederatedLearningFeature(FeatureDescriptor):
    name = "federated_learning"
    description = "Privacy-preserving federated learning for collaborative modulo arithmetic training"
    middleware_priority = 43
    cli_flags = [
        ("--federated", {"action": "store_true", "default": False,
                         "help": "Enable Federated Learning: train 5 non-IID clients to collaboratively learn modulo arithmetic"}),
        ("--fed-rounds", {"type": int, "default": None, "metavar": "N",
                          "help": "Number of federation rounds (default: from config)"}),
        ("--fed-dashboard", {"action": "store_true", "default": False,
                             "help": "Display the Federated Learning ASCII dashboard after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "federated", False) or getattr(args, "fed_dashboard", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.federated_learning import (
            DifferentialPrivacyManager,
            FedAvgAggregator,
            FedProxAggregator,
            FederatedMiddleware,
            FederatedServer,
            NonIIDSimulator,
        )

        fed_num_rounds = getattr(args, "fed_rounds", None) or config.federated_learning_num_rounds
        fed_lr = config.federated_learning_learning_rate
        fed_local_epochs = config.federated_learning_local_epochs
        fed_agg_strategy = config.federated_learning_aggregation_strategy

        fed_divisor = config.rules[0].divisor if config.rules else 3

        fed_clients = NonIIDSimulator.create_clients(
            divisor=fed_divisor,
            data_range=60,
            rng=random.Random(42),
        )

        if fed_agg_strategy == "fedprox":
            aggregator = FedProxAggregator(mu=config.federated_learning_fedprox_mu)
        else:
            aggregator = FedAvgAggregator()

        dp_manager = None
        if config.federated_learning_dp_enabled:
            dp_manager = DifferentialPrivacyManager(
                epsilon_budget=config.federated_learning_dp_epsilon,
                delta=config.federated_learning_dp_delta,
                noise_multiplier=config.federated_learning_dp_noise_multiplier,
                max_grad_norm=config.federated_learning_dp_max_grad_norm,
            )

        server = FederatedServer(
            clients=fed_clients,
            aggregator=aggregator,
            dp_manager=dp_manager,
            learning_rate=fed_lr,
            local_epochs=fed_local_epochs,
            target_accuracy=config.federated_learning_convergence_target,
            patience=config.federated_learning_convergence_patience,
            event_bus=event_bus,
        )

        server.train(fed_num_rounds)

        middleware = FederatedMiddleware(
            server=server,
            event_bus=event_bus,
        )

        return server, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        if not getattr(args, "fed_dashboard", False):
            return None
        from enterprise_fizzbuzz.infrastructure.federated_learning import FederatedDashboard
        server = middleware._server if hasattr(middleware, "_server") else None
        if server is None:
            return None
        return FederatedDashboard.render(
            server,
            width=60,
            show_convergence=True,
            show_clients=True,
        )
