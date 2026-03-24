"""Federated Learning properties"""

from __future__ import annotations

from typing import Any


class FederatedLearningConfigMixin:
    """Configuration properties for the federated learning subsystem."""

    # ------------------------------------------------------------------
    # Federated Learning properties
    # ------------------------------------------------------------------

    @property
    def federated_learning_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("federated_learning", {}).get("enabled", False)

    @property
    def federated_learning_num_rounds(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("federated_learning", {}).get("num_rounds", 10)

    @property
    def federated_learning_num_clients(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("federated_learning", {}).get("num_clients", 5)

    @property
    def federated_learning_local_epochs(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("federated_learning", {}).get("local_epochs", 3)

    @property
    def federated_learning_learning_rate(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("federated_learning", {}).get("learning_rate", 0.5)

    @property
    def federated_learning_aggregation_strategy(self) -> str:
        self._ensure_loaded()
        return self._raw_config.get("federated_learning", {}).get("aggregation_strategy", "fedavg")

    @property
    def federated_learning_fedprox_mu(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("federated_learning", {}).get("fedprox_mu", 0.01)

    @property
    def federated_learning_dp_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("federated_learning", {}).get(
            "differential_privacy", {}
        ).get("enabled", True)

    @property
    def federated_learning_dp_epsilon(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("federated_learning", {}).get(
            "differential_privacy", {}
        ).get("epsilon_budget", 10.0)

    @property
    def federated_learning_dp_delta(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("federated_learning", {}).get(
            "differential_privacy", {}
        ).get("delta", 1e-5)

    @property
    def federated_learning_dp_noise_multiplier(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("federated_learning", {}).get(
            "differential_privacy", {}
        ).get("noise_multiplier", 1.0)

    @property
    def federated_learning_dp_max_grad_norm(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("federated_learning", {}).get(
            "differential_privacy", {}
        ).get("max_grad_norm", 1.0)

    @property
    def federated_learning_convergence_target(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("federated_learning", {}).get(
            "convergence", {}
        ).get("target_accuracy", 95.0)

    @property
    def federated_learning_convergence_patience(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("federated_learning", {}).get(
            "convergence", {}
        ).get("patience", 3)

    @property
    def federated_learning_dashboard_width(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("federated_learning", {}).get(
            "dashboard", {}
        ).get("width", 60)

    @property
    def federated_learning_dashboard_show_convergence(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("federated_learning", {}).get(
            "dashboard", {}
        ).get("show_convergence_curve", True)

    @property
    def federated_learning_dashboard_show_clients(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("federated_learning", {}).get(
            "dashboard", {}
        ).get("show_client_details", True)

    # ── Knowledge Graph & Domain Ontology ──

