"""
Enterprise FizzBuzz Platform - Federated Learning Module

Implements privacy-preserving distributed model training across a
federation of FizzBuzz clients, each holding a Non-IID shard of
integer training data. Because training a single neural network to
check if n % 3 == 0 was insufficiently distributed, we now orchestrate
FIVE separate neural networks — each trained on a biased subset of
integers — and aggregate their weight updates via Federated Averaging
(McMahan et al., 2017) or FedProx (Li et al., 2020).

Differential Privacy ensures that the divisibility properties of
individual integers remain confidential. The privacy budget is tracked
in epsilon, calibrated via the Gaussian mechanism, because even modulo
arithmetic deserves formal privacy guarantees.

Architecture:
    FederatedServer
      ├── FedAvgAggregator (or FedProxAggregator)
      ├── DifferentialPrivacyManager
      ├── NonIIDSimulator (creates 5 clients with skewed data)
      └── FederatedClient x5
            ├── Local weight matrices (list[list[float]])
            ├── Local training loop
            └── Weight delta computation

Technical Specifications:
    - Model: Input(2) -> Dense(8, sigmoid) -> Dense(1, sigmoid)
    - Features: Cyclical encoding via sin(2*pi*n/d), cos(2*pi*n/d)
    - Aggregation: FedAvg (weighted mean) or FedProx (proximal term)
    - Privacy: Calibrated Gaussian noise (epsilon-delta DP)
    - Clients: 5 non-IID data distributions
    - Dependencies: None (pure stdlib, as nature intended)

NOTE: The federated model converges to correct FizzBuzz classification,
which proves that even unnecessarily distributed systems can eventually
learn to divide by 3 — given enough rounds, enough noise, and enough
enterprise infrastructure.
"""

from __future__ import annotations

import copy
import logging
import math
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger(__name__)


# ============================================================
# Neural Network Primitives (Lightweight Federation Edition)
# ============================================================
# We intentionally do NOT import _NeuralNetwork from ml_engine.
# Each federated client gets its own lightweight model with
# weight matrices stored as list[list[float]] for easy
# delta computation and aggregation. Because federated learning
# demands that we reinvent the neural network, again.
# ============================================================


def _sigmoid(x: float) -> float:
    """Sigmoid activation — squashing numbers for distributed modulo."""
    x = max(-500.0, min(500.0, x))
    return 1.0 / (1.0 + math.exp(-x))


def _sigmoid_derivative(output: float) -> float:
    """Derivative of sigmoid given its output."""
    return output * (1.0 - output)


def _encode_features(number: int, divisor: int) -> list[float]:
    """Cyclical feature encoding for federated modulo classification.

    Maps a number onto a 2D unit circle with period equal to the divisor.
    This feature engineering renders the subsequent neural network,
    the federated averaging, and the differential privacy entirely
    unnecessary — but that's enterprise ML for you.
    """
    angle = 2.0 * math.pi * number / divisor
    return [math.sin(angle), math.cos(angle)]


# ============================================================
# Federated Client
# ============================================================


@dataclass
class ClientTrainingReport:
    """Training metrics from a single federated client.

    Documents exactly how well one shard of the distributed modulo
    consortium performed during local training.
    """

    client_id: str
    dataset_size: int
    local_epochs: int
    final_loss: float
    final_accuracy: float
    training_time_ms: float


class FederatedClient:
    """A federated learning client with local model and biased data.

    Each client maintains its own lightweight neural network
    (Input(2) -> Dense(8, sigmoid) -> Dense(1, sigmoid)) and trains
    on a non-IID shard of integers. After local training, the client
    computes weight deltas (difference between updated and initial
    weights) and reports them to the server for aggregation.

    The client never shares its raw training data with the server,
    preserving the sacred privacy of which integers are divisible
    by 3 — a privacy guarantee that nobody asked for but everyone
    deserves.
    """

    def __init__(
        self,
        client_id: str,
        data: list[int],
        divisor: int,
        rng: random.Random,
        hidden_size: int = 8,
    ) -> None:
        self.client_id = client_id
        self.data = data
        self.divisor = divisor
        self._rng = rng
        self._hidden_size = hidden_size

        # Xavier/Glorot initialization for the federation's neural elite
        scale_h = math.sqrt(2.0 / (2 + hidden_size))
        self.weights_hidden: list[list[float]] = [
            [rng.gauss(0.0, scale_h) for _ in range(2)]
            for _ in range(hidden_size)
        ]
        self.biases_hidden: list[float] = [0.0] * hidden_size

        scale_o = math.sqrt(2.0 / (hidden_size + 1))
        self.weights_output: list[list[float]] = [
            [rng.gauss(0.0, scale_o) for _ in range(hidden_size)]
        ]
        self.biases_output: list[float] = [0.0]

    def set_weights(
        self,
        weights_hidden: list[list[float]],
        biases_hidden: list[float],
        weights_output: list[list[float]],
        biases_output: list[float],
    ) -> None:
        """Receive global model weights from the server.

        The server broadcasts its current best guess at modulo arithmetic
        to all clients, who then dutifully overwrite their local weights
        with this centrally-approved version of divisibility knowledge.
        """
        self.weights_hidden = [row[:] for row in weights_hidden]
        self.biases_hidden = biases_hidden[:]
        self.weights_output = [row[:] for row in weights_output]
        self.biases_output = biases_output[:]

    def get_weights(
        self,
    ) -> tuple[
        list[list[float]], list[float], list[list[float]], list[float]
    ]:
        """Return current model weights."""
        return (
            [row[:] for row in self.weights_hidden],
            self.biases_hidden[:],
            [row[:] for row in self.weights_output],
            self.biases_output[:],
        )

    def _forward(self, features: list[float]) -> tuple[list[float], float]:
        """Forward pass through the local model."""
        hidden_out: list[float] = []
        for j in range(self._hidden_size):
            z = self.biases_hidden[j]
            for i in range(2):
                z += self.weights_hidden[j][i] * features[i]
            hidden_out.append(_sigmoid(z))

        z_out = self.biases_output[0]
        for j in range(self._hidden_size):
            z_out += self.weights_output[0][j] * hidden_out[j]
        output = _sigmoid(z_out)

        return hidden_out, output

    def _train_step(
        self,
        features: list[float],
        target: float,
        learning_rate: float,
    ) -> float:
        """One training step: forward + backprop."""
        hidden_out, prediction = self._forward(features)

        # BCE loss
        p = max(1e-15, min(1.0 - 1e-15, prediction))
        loss = -(target * math.log(p) + (1.0 - target) * math.log(1.0 - p))

        # Backprop: output layer
        d_loss = -(target / p) + (1.0 - target) / (1.0 - p)
        d_out = d_loss * _sigmoid_derivative(prediction)

        hidden_grads: list[float] = [0.0] * self._hidden_size
        for j in range(self._hidden_size):
            hidden_grads[j] = self.weights_output[0][j] * d_out
            self.weights_output[0][j] -= learning_rate * d_out * hidden_out[j]
        self.biases_output[0] -= learning_rate * d_out

        # Backprop: hidden layer
        for j in range(self._hidden_size):
            d_hidden = hidden_grads[j] * _sigmoid_derivative(hidden_out[j])
            for i in range(2):
                self.weights_hidden[j][i] -= learning_rate * d_hidden * features[i]
            self.biases_hidden[j] -= learning_rate * d_hidden

        return loss

    def train_local(
        self,
        epochs: int,
        learning_rate: float,
        global_weights: Optional[
            tuple[list[list[float]], list[float], list[list[float]], list[float]]
        ] = None,
        proximal_mu: float = 0.0,
    ) -> ClientTrainingReport:
        """Execute local training on the client's data shard.

        If proximal_mu > 0 (FedProx), a proximal penalty is added to
        discourage the local model from straying too far from the global
        model. This prevents any single client's idiosyncratic view of
        modulo arithmetic from dominating the federation.
        """
        start = time.perf_counter_ns()

        # Prepare features and labels
        features_list = [_encode_features(n, self.divisor) for n in self.data]
        labels = [1.0 if n % self.divisor == 0 else 0.0 for n in self.data]

        indices = list(range(len(self.data)))
        total_loss = 0.0

        for epoch in range(epochs):
            self._rng.shuffle(indices)
            epoch_loss = 0.0

            for idx in indices:
                loss = self._train_step(
                    features_list[idx], labels[idx], learning_rate
                )
                epoch_loss += loss

                # FedProx proximal term penalty
                if proximal_mu > 0.0 and global_weights is not None:
                    g_wh, g_bh, g_wo, g_bo = global_weights
                    for j in range(self._hidden_size):
                        for i in range(2):
                            diff = self.weights_hidden[j][i] - g_wh[j][i]
                            self.weights_hidden[j][i] -= (
                                learning_rate * proximal_mu * diff
                            )
                        diff_b = self.biases_hidden[j] - g_bh[j]
                        self.biases_hidden[j] -= (
                            learning_rate * proximal_mu * diff_b
                        )
                    for j in range(self._hidden_size):
                        diff = self.weights_output[0][j] - g_wo[0][j]
                        self.weights_output[0][j] -= (
                            learning_rate * proximal_mu * diff
                        )
                    diff_b = self.biases_output[0] - g_bo[0]
                    self.biases_output[0] -= (
                        learning_rate * proximal_mu * diff_b
                    )

            total_loss = epoch_loss / max(len(self.data), 1)

        # Compute final accuracy
        correct = 0
        for idx in range(len(self.data)):
            _, pred = self._forward(features_list[idx])
            if (pred > 0.5) == (labels[idx] > 0.5):
                correct += 1
        accuracy = correct / max(len(self.data), 1) * 100.0

        elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000

        return ClientTrainingReport(
            client_id=self.client_id,
            dataset_size=len(self.data),
            local_epochs=epochs,
            final_loss=total_loss,
            final_accuracy=accuracy,
            training_time_ms=elapsed_ms,
        )

    def predict(self, number: int) -> tuple[bool, float]:
        """Run inference for a single number."""
        features = _encode_features(number, self.divisor)
        _, output = self._forward(features)
        return output > 0.5, output


# ============================================================
# Weight Delta Computation
# ============================================================


def compute_weight_deltas(
    before: tuple[list[list[float]], list[float], list[list[float]], list[float]],
    after: tuple[list[list[float]], list[float], list[list[float]], list[float]],
) -> tuple[list[list[float]], list[float], list[list[float]], list[float]]:
    """Compute the difference between two sets of model weights.

    The delta represents what the client learned during local training —
    its unique contribution to the federation's understanding of modulo.
    """
    wh_before, bh_before, wo_before, bo_before = before
    wh_after, bh_after, wo_after, bo_after = after

    d_wh = [
        [wh_after[j][i] - wh_before[j][i] for i in range(len(wh_before[j]))]
        for j in range(len(wh_before))
    ]
    d_bh = [bh_after[j] - bh_before[j] for j in range(len(bh_before))]
    d_wo = [
        [wo_after[j][i] - wo_before[j][i] for i in range(len(wo_before[j]))]
        for j in range(len(wo_before))
    ]
    d_bo = [bo_after[j] - bo_before[j] for j in range(len(bo_before))]

    return d_wh, d_bh, d_wo, d_bo


# ============================================================
# Aggregation Strategies
# ============================================================


class FedAvgAggregator:
    """Federated Averaging aggregator (McMahan et al., 2017).

    Computes the weighted mean of client weight deltas, where each
    client's contribution is proportional to its dataset size. This
    ensures that clients with more integers have more influence over
    the global model's understanding of divisibility — a form of
    democratic representation where the franchise is weighted by
    data volume.
    """

    def aggregate(
        self,
        deltas: list[
            tuple[list[list[float]], list[float], list[list[float]], list[float]]
        ],
        weights: list[float],
    ) -> tuple[list[list[float]], list[float], list[list[float]], list[float]]:
        """Aggregate weight deltas using weighted averaging.

        Args:
            deltas: List of weight deltas from each client.
            weights: Relative importance of each client (dataset sizes).

        Returns:
            Aggregated weight delta to apply to the global model.
        """
        total_weight = sum(weights)
        if total_weight == 0:
            return deltas[0]  # Shouldn't happen, but enterprise code is defensive

        normalized = [w / total_weight for w in weights]

        # Aggregate hidden weights
        n_hidden = len(deltas[0][0])
        n_input = len(deltas[0][0][0])
        n_output_w = len(deltas[0][2][0])

        agg_wh = [[0.0] * n_input for _ in range(n_hidden)]
        agg_bh = [0.0] * n_hidden
        agg_wo = [[0.0] * n_output_w]
        agg_bo = [0.0]

        for c, (d_wh, d_bh, d_wo, d_bo) in enumerate(deltas):
            w = normalized[c]
            for j in range(n_hidden):
                for i in range(n_input):
                    agg_wh[j][i] += w * d_wh[j][i]
                agg_bh[j] += w * d_bh[j]
            for i in range(n_output_w):
                agg_wo[0][i] += w * d_wo[0][i]
            agg_bo[0] += w * d_bo[0]

        return agg_wh, agg_bh, agg_wo, agg_bo


class FedProxAggregator(FedAvgAggregator):
    """FedProx aggregator (Li et al., 2020).

    Identical to FedAvg in the aggregation step — the proximal term
    is applied during local training, not during aggregation. This
    class exists primarily for type-system completeness and to justify
    an additional import in the module's __all__ list.

    The mu parameter controls how aggressively clients are penalized
    for deviating from the global model, which is enterprise-speak for
    "don't let any single client's weird data distribution ruin the
    consensus on modulo arithmetic."
    """

    def __init__(self, mu: float = 0.01) -> None:
        self.mu = mu


# ============================================================
# Differential Privacy Manager
# ============================================================


class DifferentialPrivacyManager:
    """Manages the differential privacy budget for federated learning.

    Implements the Gaussian mechanism for (epsilon, delta)-differential
    privacy. Noise is calibrated based on the sensitivity of the query
    (max gradient norm) and the desired privacy level (epsilon).

    The privacy budget is finite and depletes with each federation round.
    Once exhausted, no more training can occur — the model must be
    frozen forever, its knowledge of modulo arithmetic locked behind
    an impenetrable wall of mathematical privacy guarantees.

    Because the divisibility of integers is clearly sensitive data
    that deserves formal privacy protection.
    """

    def __init__(
        self,
        epsilon_budget: float = 10.0,
        delta: float = 1e-5,
        noise_multiplier: float = 1.0,
        max_grad_norm: float = 1.0,
        rng: Optional[random.Random] = None,
    ) -> None:
        self.epsilon_budget = epsilon_budget
        self.epsilon_spent = 0.0
        self.delta = delta
        self.noise_multiplier = noise_multiplier
        self.max_grad_norm = max_grad_norm
        self._rng = rng or random.Random(42)
        self._round_epsilons: list[float] = []

    @property
    def epsilon_remaining(self) -> float:
        return max(0.0, self.epsilon_budget - self.epsilon_spent)

    @property
    def budget_fraction_used(self) -> float:
        if self.epsilon_budget <= 0:
            return 1.0
        return min(1.0, self.epsilon_spent / self.epsilon_budget)

    def compute_sigma(self) -> float:
        """Compute the noise standard deviation for the Gaussian mechanism.

        sigma = sensitivity * noise_multiplier * sqrt(2 * ln(1.25/delta)) / epsilon_per_round

        This formula ensures that adding or removing any single integer's
        divisibility label from the training set changes the output
        distribution by at most epsilon — protecting the fundamental
        human right to integer privacy.
        """
        if self.epsilon_remaining <= 0:
            return float("inf")

        # Per-round epsilon (simple composition)
        eps_per_round = max(0.01, self.epsilon_remaining * 0.1)

        ln_term = math.log(1.25 / self.delta)
        sigma = self.max_grad_norm * self.noise_multiplier * math.sqrt(2.0 * ln_term) / eps_per_round
        return sigma

    def add_noise_to_deltas(
        self,
        deltas: tuple[list[list[float]], list[float], list[list[float]], list[float]],
    ) -> tuple[list[list[float]], list[float], list[list[float]], list[float]]:
        """Add calibrated Gaussian noise to aggregated weight deltas.

        Returns the noisy deltas and updates the privacy budget.
        """
        sigma = self.compute_sigma()
        if sigma == float("inf"):
            from enterprise_fizzbuzz.domain.exceptions import (
                FederatedPrivacyBudgetExhaustedError,
            )
            raise FederatedPrivacyBudgetExhaustedError(
                self.epsilon_spent, self.epsilon_budget
            )

        d_wh, d_bh, d_wo, d_bo = deltas

        noisy_wh = [
            [v + self._rng.gauss(0.0, sigma) for v in row]
            for row in d_wh
        ]
        noisy_bh = [v + self._rng.gauss(0.0, sigma) for v in d_bh]
        noisy_wo = [
            [v + self._rng.gauss(0.0, sigma) for v in row]
            for row in d_wo
        ]
        noisy_bo = [v + self._rng.gauss(0.0, sigma) for v in d_bo]

        # Update epsilon budget (simple composition)
        eps_spent = max(0.01, self.epsilon_remaining * 0.1)
        self.epsilon_spent += eps_spent
        self._round_epsilons.append(eps_spent)

        return noisy_wh, noisy_bh, noisy_wo, noisy_bo

    def get_privacy_report(self) -> dict[str, Any]:
        """Generate a privacy compliance report.

        Essential documentation for the FizzBuzz Data Protection Officer
        who needs to certify that integer divisibility has been adequately
        anonymized.
        """
        return {
            "epsilon_budget": self.epsilon_budget,
            "epsilon_spent": round(self.epsilon_spent, 6),
            "epsilon_remaining": round(self.epsilon_remaining, 6),
            "delta": self.delta,
            "noise_multiplier": self.noise_multiplier,
            "max_grad_norm": self.max_grad_norm,
            "rounds_tracked": len(self._round_epsilons),
            "per_round_epsilon": [round(e, 6) for e in self._round_epsilons],
            "budget_exhausted": self.epsilon_remaining <= 0,
        }


# ============================================================
# Non-IID Data Simulator
# ============================================================


class NonIIDSimulator:
    """Creates federated clients with intentionally skewed data distributions.

    In real federated learning, clients have naturally non-IID data because
    each device/user generates data from a different distribution. Here, we
    simulate this by giving each client a carefully curated shard of integers:

    1. MultiplesClient:    Biased toward multiples of the divisor
    2. AntiMultiplesClient: Biased toward multiples of 5 (or non-multiples)
    3. PrimesClient:       Only prime numbers (nature's most indivisible)
    4. SmallRangeClient:   Only numbers 1-20 (the provincial client)
    5. UniformClient:      Uniform random sample (the control group)

    This ensures maximum statistical heterogeneity for a problem that
    could be solved deterministically in O(1) time with the % operator.
    """

    @staticmethod
    def _is_prime(n: int) -> bool:
        """Primality check — because federated learning needs primes."""
        if n < 2:
            return False
        if n < 4:
            return True
        if n % 2 == 0 or n % 3 == 0:
            return False
        i = 5
        while i * i <= n:
            if n % i == 0 or n % (i + 2) == 0:
                return False
            i += 6
        return True

    @staticmethod
    def create_clients(
        divisor: int,
        data_range: int = 60,
        rng: Optional[random.Random] = None,
        hidden_size: int = 8,
    ) -> list[FederatedClient]:
        """Create 5 federated clients with non-IID data distributions.

        Each client gets a biased view of integer space, ensuring that no
        single client has a representative picture of modulo arithmetic.
        Only through collaboration can they learn what % does.
        """
        rng = rng or random.Random(42)
        all_numbers = list(range(1, data_range + 1))

        # Client 1: Biased toward multiples of divisor
        multiples = [n for n in all_numbers if n % divisor == 0]
        non_multiples = [n for n in all_numbers if n % divisor != 0]
        # Take all multiples + a few non-multiples for balance
        sample_non = non_multiples[: max(3, len(multiples) // 2)]
        client1_data = multiples + sample_non
        rng.shuffle(client1_data)

        # Client 2: Biased toward multiples of 5 (anti-correlation with div=3)
        fives = [n for n in all_numbers if n % 5 == 0]
        non_fives = [n for n in all_numbers if n % 5 != 0]
        sample_nf = non_fives[: max(3, len(fives))]
        client2_data = fives + sample_nf
        rng.shuffle(client2_data)

        # Client 3: Prime numbers only
        primes = [n for n in all_numbers if NonIIDSimulator._is_prime(n)]
        if len(primes) < 5:
            primes = primes + all_numbers[:5]
        client3_data = primes[:]
        rng.shuffle(client3_data)

        # Client 4: Small range (1-20)
        small_range = [n for n in all_numbers if n <= 20]
        client4_data = small_range[:]
        rng.shuffle(client4_data)

        # Client 5: Uniform random sample
        sample_size = min(len(all_numbers), max(15, len(all_numbers) // 3))
        client5_data = rng.sample(all_numbers, sample_size)

        client_configs = [
            ("multiples_specialist", client1_data),
            ("fives_aficionado", client2_data),
            ("prime_purist", client3_data),
            ("small_range_local", client4_data),
            ("uniform_generalist", client5_data),
        ]

        clients: list[FederatedClient] = []
        for cid, data in client_configs:
            clients.append(
                FederatedClient(
                    client_id=cid,
                    data=data,
                    divisor=divisor,
                    rng=random.Random(rng.randint(0, 2**31)),
                    hidden_size=hidden_size,
                )
            )

        return clients


# ============================================================
# Federation Round Result
# ============================================================


@dataclass
class FederationRoundResult:
    """Results from a single federation round.

    Documents the collaborative learning progress of the modulo
    arithmetic consortium.
    """

    round_number: int
    client_reports: list[ClientTrainingReport]
    global_accuracy: float
    global_loss: float
    aggregation_strategy: str
    privacy_epsilon_spent: float
    round_time_ms: float


# ============================================================
# Federated Server
# ============================================================


class FederatedServer:
    """Orchestrates federated learning across multiple FizzBuzz clients.

    The server coordinates the federation protocol:
    1. Broadcast global model weights to all clients
    2. Each client trains locally on their non-IID data shard
    3. Clients compute and report weight deltas
    4. Server aggregates deltas (FedAvg or FedProx)
    5. Optional: Apply differential privacy noise
    6. Update global model weights
    7. Repeat until convergence or budget exhaustion

    The server never sees raw training data — only weight deltas —
    preserving the privacy of which integers are divisible by 3.
    This is federated learning at its finest, applied to a problem
    that doesn't need it.
    """

    def __init__(
        self,
        clients: list[FederatedClient],
        aggregator: FedAvgAggregator,
        dp_manager: Optional[DifferentialPrivacyManager] = None,
        learning_rate: float = 0.5,
        local_epochs: int = 3,
        target_accuracy: float = 95.0,
        patience: int = 3,
        event_bus: Optional[Any] = None,
    ) -> None:
        self.clients = clients
        self.aggregator = aggregator
        self.dp_manager = dp_manager
        self.learning_rate = learning_rate
        self.local_epochs = local_epochs
        self.target_accuracy = target_accuracy
        self.patience = patience
        self._event_bus = event_bus

        self.round_results: list[FederationRoundResult] = []
        self.converged = False
        self.convergence_round: Optional[int] = None

        # Initialize global model from the first client
        if clients:
            self._global_weights = clients[0].get_weights()
        else:
            self._global_weights = ([[0.0] * 2] * 8, [0.0] * 8, [[0.0] * 8], [0.0])

    def _emit_event(self, event_type: EventType, payload: dict[str, Any]) -> None:
        """Emit a federation event if an event bus is available."""
        if self._event_bus is not None:
            from enterprise_fizzbuzz.domain.models import Event
            self._event_bus.publish(Event(
                event_type=event_type,
                payload=payload,
                source="FederatedServer",
            ))

    def _evaluate_global_accuracy(self, test_range: int = 60) -> tuple[float, float]:
        """Evaluate the global model accuracy on a test set.

        Uses the first client as a proxy (with global weights) to evaluate
        accuracy across the full range. This is the moment of truth: can
        five neural networks, trained on biased data shards, collaboratively
        learn that 15 is divisible by 3?
        """
        if not self.clients:
            return 0.0, float("inf")

        # Temporarily set global weights on first client for evaluation
        original_weights = self.clients[0].get_weights()
        self.clients[0].set_weights(*self._global_weights)

        correct = 0
        total_loss = 0.0
        divisor = self.clients[0].divisor

        for n in range(1, test_range + 1):
            is_match, confidence = self.clients[0].predict(n)
            target = 1.0 if n % divisor == 0 else 0.0
            actual_match = n % divisor == 0

            if is_match == actual_match:
                correct += 1

            p = max(1e-15, min(1.0 - 1e-15, confidence))
            total_loss += -(
                target * math.log(p) + (1.0 - target) * math.log(1.0 - p)
            )

        # Restore original weights
        self.clients[0].set_weights(*original_weights)

        accuracy = correct / test_range * 100.0
        avg_loss = total_loss / test_range
        return accuracy, avg_loss

    def run_round(self, round_number: int) -> FederationRoundResult:
        """Execute a single federation round.

        The ritual:
        1. Server broadcasts weights to all clients
        2. Clients train locally and compute deltas
        3. Server aggregates deltas
        4. Optional: DP noise injection
        5. Server updates global model

        Returns a detailed report suitable for regulatory filing.
        """
        start = time.perf_counter_ns()

        self._emit_event(EventType.FEDERATION_ROUND_STARTED, {
            "round": round_number,
            "num_clients": len(self.clients),
        })

        # 1. Broadcast global weights to all clients
        for client in self.clients:
            client.set_weights(*self._global_weights)

        # 2. Clients train locally and compute deltas
        client_reports: list[ClientTrainingReport] = []
        deltas: list[
            tuple[list[list[float]], list[float], list[list[float]], list[float]]
        ] = []
        data_sizes: list[float] = []

        proximal_mu = 0.0
        if isinstance(self.aggregator, FedProxAggregator):
            proximal_mu = self.aggregator.mu

        for client in self.clients:
            before_weights = client.get_weights()

            report = client.train_local(
                epochs=self.local_epochs,
                learning_rate=self.learning_rate,
                global_weights=self._global_weights if proximal_mu > 0 else None,
                proximal_mu=proximal_mu,
            )
            client_reports.append(report)

            after_weights = client.get_weights()
            delta = compute_weight_deltas(before_weights, after_weights)
            deltas.append(delta)
            data_sizes.append(float(len(client.data)))

            self._emit_event(EventType.FEDERATION_CLIENT_TRAINED, {
                "round": round_number,
                "client_id": client.client_id,
                "accuracy": report.final_accuracy,
                "loss": report.final_loss,
                "dataset_size": report.dataset_size,
            })

        # 3. Aggregate deltas
        agg_strategy = "fedprox" if proximal_mu > 0 else "fedavg"
        aggregated = self.aggregator.aggregate(deltas, data_sizes)

        self._emit_event(EventType.FEDERATION_WEIGHTS_AGGREGATED, {
            "round": round_number,
            "strategy": agg_strategy,
            "num_deltas": len(deltas),
        })

        # 4. Apply differential privacy noise
        epsilon_spent = 0.0
        if self.dp_manager is not None:
            try:
                aggregated = self.dp_manager.add_noise_to_deltas(aggregated)
                epsilon_spent = self.dp_manager.epsilon_spent
                self._emit_event(EventType.FEDERATION_PRIVACY_BUDGET_UPDATED, {
                    "round": round_number,
                    "epsilon_spent": epsilon_spent,
                    "epsilon_remaining": self.dp_manager.epsilon_remaining,
                })
            except Exception:
                # Privacy budget exhausted — use noisy-free aggregation
                logger.warning(
                    "  [FED] Privacy budget exhausted at round %d. "
                    "Proceeding without noise (the numbers are no longer private).",
                    round_number,
                )

        # 5. Apply aggregated delta to global weights
        g_wh, g_bh, g_wo, g_bo = self._global_weights
        a_wh, a_bh, a_wo, a_bo = aggregated

        for j in range(len(g_wh)):
            for i in range(len(g_wh[j])):
                g_wh[j][i] += a_wh[j][i]
            g_bh[j] += a_bh[j]
        for i in range(len(g_wo[0])):
            g_wo[0][i] += a_wo[0][i]
        g_bo[0] += a_bo[0]

        self._global_weights = (g_wh, g_bh, g_wo, g_bo)

        # Evaluate global model
        global_accuracy, global_loss = self._evaluate_global_accuracy()

        elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000

        result = FederationRoundResult(
            round_number=round_number,
            client_reports=client_reports,
            global_accuracy=global_accuracy,
            global_loss=global_loss,
            aggregation_strategy=agg_strategy,
            privacy_epsilon_spent=epsilon_spent,
            round_time_ms=elapsed_ms,
        )

        self.round_results.append(result)

        self._emit_event(EventType.FEDERATION_ROUND_COMPLETED, {
            "round": round_number,
            "global_accuracy": global_accuracy,
            "global_loss": global_loss,
            "time_ms": elapsed_ms,
        })

        return result

    def train(self, num_rounds: int) -> list[FederationRoundResult]:
        """Execute the full federated training protocol.

        Runs the specified number of federation rounds with early stopping
        if the global model achieves the target accuracy and holds it for
        `patience` rounds. Returns a chronicle of the federation's journey
        toward modulo enlightenment.
        """
        logger.info("")
        logger.info("  ============================================================")
        logger.info("  FEDERATED LEARNING: Training Protocol Initiated")
        logger.info("  ============================================================")
        logger.info("  Clients: %d", len(self.clients))
        logger.info("  Rounds: %d (max)", num_rounds)
        logger.info("  Local epochs per round: %d", self.local_epochs)
        logger.info("  Learning rate: %.4f", self.learning_rate)
        logger.info(
            "  Aggregation: %s",
            "FedProx" if isinstance(self.aggregator, FedProxAggregator) else "FedAvg",
        )
        if self.dp_manager:
            logger.info("  Differential Privacy: ENABLED (epsilon=%.2f)", self.dp_manager.epsilon_budget)
        logger.info("")

        patience_counter = 0

        for r in range(1, num_rounds + 1):
            result = self.run_round(r)

            logger.info(
                "  [FED] Round %d/%d | Global accuracy: %.1f%% | Loss: %.4f | Time: %.1fms",
                r, num_rounds, result.global_accuracy, result.global_loss,
                result.round_time_ms,
            )

            # Check convergence
            if result.global_accuracy >= self.target_accuracy:
                patience_counter += 1
                if patience_counter >= self.patience and not self.converged:
                    self.converged = True
                    self.convergence_round = r
                    self._emit_event(EventType.FEDERATION_CONVERGENCE_ACHIEVED, {
                        "round": r,
                        "accuracy": result.global_accuracy,
                    })
                    logger.info(
                        "  [FED] CONVERGENCE ACHIEVED at round %d! "
                        "Accuracy: %.1f%% >= %.1f%% for %d rounds.",
                        r, result.global_accuracy, self.target_accuracy,
                        self.patience,
                    )
                    break
            else:
                patience_counter = 0

        logger.info("")
        logger.info("  ============================================================")
        logger.info("  FEDERATED LEARNING: Training Complete")
        logger.info("  ============================================================")
        logger.info("  Rounds completed: %d", len(self.round_results))
        logger.info("  Converged: %s", "YES" if self.converged else "NO")
        if self.round_results:
            final = self.round_results[-1]
            logger.info("  Final global accuracy: %.1f%%", final.global_accuracy)
            logger.info("  Final global loss: %.6f", final.global_loss)
        if self.dp_manager:
            logger.info(
                "  Privacy budget used: %.4f / %.4f epsilon",
                self.dp_manager.epsilon_spent,
                self.dp_manager.epsilon_budget,
            )
        logger.info("  ============================================================")
        logger.info("")

        return self.round_results

    def get_global_weights(
        self,
    ) -> tuple[list[list[float]], list[float], list[list[float]], list[float]]:
        """Return the current global model weights."""
        wh, bh, wo, bo = self._global_weights
        return [row[:] for row in wh], bh[:], [row[:] for row in wo], bo[:]


# ============================================================
# Federated Dashboard
# ============================================================


class FederatedDashboard:
    """ASCII dashboard for federated learning visualization.

    Renders a comprehensive overview of the federation's progress,
    including per-client accuracy, convergence curves, and privacy
    budget status — all in glorious monospace text, because the
    enterprise can't afford a GUI for its FizzBuzz infrastructure.
    """

    @staticmethod
    def render(
        server: FederatedServer,
        width: int = 60,
        show_convergence: bool = True,
        show_clients: bool = True,
    ) -> str:
        """Render the federated learning dashboard."""
        lines: list[str] = []
        border = "+" + "=" * (width - 2) + "+"
        separator = "+" + "-" * (width - 2) + "+"

        lines.append("")
        lines.append(f"  {border}")
        lines.append(f"  |{'FEDERATED LEARNING DASHBOARD':^{width - 2}}|")
        lines.append(f"  |{'Privacy-Preserving Distributed Modulo':^{width - 2}}|")
        lines.append(f"  {border}")

        # Summary
        lines.append(f"  {separator}")
        lines.append(f"  |{'FEDERATION SUMMARY':^{width - 2}}|")
        lines.append(f"  {separator}")

        total_rounds = len(server.round_results)
        converged_str = "YES" if server.converged else "NO"
        conv_round = str(server.convergence_round) if server.convergence_round else "N/A"

        lines.append(f"  | {'Clients:':<25}{len(server.clients):>{width - 29}}|")
        lines.append(f"  | {'Rounds completed:':<25}{total_rounds:>{width - 29}}|")
        lines.append(f"  | {'Converged:':<25}{converged_str:>{width - 29}}|")
        lines.append(f"  | {'Convergence round:':<25}{conv_round:>{width - 29}}|")

        if server.round_results:
            final = server.round_results[-1]
            acc_str = f"{final.global_accuracy:.1f}%"
            loss_str = f"{final.global_loss:.6f}"
            lines.append(f"  | {'Final accuracy:':<25}{acc_str:>{width - 29}}|")
            lines.append(f"  | {'Final loss:':<25}{loss_str:>{width - 29}}|")

        # Privacy budget
        if server.dp_manager is not None:
            lines.append(f"  {separator}")
            lines.append(f"  |{'DIFFERENTIAL PRIVACY':^{width - 2}}|")
            lines.append(f"  {separator}")

            dp = server.dp_manager
            eps_str = f"{dp.epsilon_spent:.4f} / {dp.epsilon_budget:.4f}"
            pct_str = f"{dp.budget_fraction_used * 100:.1f}%"
            lines.append(f"  | {'Epsilon spent:':<25}{eps_str:>{width - 29}}|")
            lines.append(f"  | {'Budget used:':<25}{pct_str:>{width - 29}}|")

            # Privacy budget bar
            bar_width = width - 12
            filled = int(dp.budget_fraction_used * bar_width)
            empty = bar_width - filled
            bar = "[" + "#" * filled + "." * empty + "]"
            lines.append(f"  | {bar:^{width - 4}} |")

        # Convergence curve
        if show_convergence and server.round_results:
            lines.append(f"  {separator}")
            lines.append(f"  |{'CONVERGENCE CURVE':^{width - 2}}|")
            lines.append(f"  {separator}")

            accuracies = [r.global_accuracy for r in server.round_results]
            chart_height = 8
            chart_width = min(width - 14, len(accuracies))

            # Resample if too many rounds
            if len(accuracies) > chart_width:
                step = len(accuracies) / chart_width
                sampled = [accuracies[int(i * step)] for i in range(chart_width)]
            else:
                sampled = accuracies

            min_acc = max(0.0, min(sampled) - 5)
            max_acc = min(100.0, max(sampled) + 5)
            acc_range = max(max_acc - min_acc, 1.0)

            for row in range(chart_height, 0, -1):
                threshold = min_acc + (row / chart_height) * acc_range
                label = f"{threshold:5.1f}%"
                bar_chars = ""
                for val in sampled:
                    if val >= threshold:
                        bar_chars += "#"
                    else:
                        bar_chars += " "
                line_content = f"  | {label} |{bar_chars}"
                padding = width - 2 - len(line_content) + 2
                lines.append(f"{line_content}{' ' * max(0, padding)}|")

            x_axis = "  |       +" + "-" * len(sampled)
            x_padding = width - 2 - len(x_axis) + 2
            lines.append(f"{x_axis}{' ' * max(0, x_padding)}|")

            round_label = f"Round 1..{total_rounds}"
            lines.append(f"  | {round_label:^{width - 4}} |")

        # Per-client details
        if show_clients and server.round_results:
            lines.append(f"  {separator}")
            lines.append(f"  |{'CLIENT DETAILS (Final Round)':^{width - 2}}|")
            lines.append(f"  {separator}")

            final_reports = server.round_results[-1].client_reports
            for cr in final_reports:
                cid = cr.client_id[:20]
                acc = f"{cr.final_accuracy:.1f}%"
                data = f"n={cr.dataset_size}"
                detail = f"{cid}: {acc} ({data})"
                lines.append(f"  | {detail:<{width - 4}} |")

        lines.append(f"  {border}")
        lines.append("")

        return "\n".join(lines)


# ============================================================
# Federated Middleware
# ============================================================


class FederatedMiddleware(IMiddleware):
    """Middleware that enriches the processing context with federated learning metadata.

    Priority -8 ensures this runs early in the pipeline, before most
    other middleware has a chance to interfere with the federated
    model's carefully calibrated predictions. The middleware attaches
    the global model's prediction for each number to the processing
    context, enabling downstream consumers to marvel at the fact that
    five neural networks collaboratively determined divisibility.
    """

    def __init__(
        self,
        server: FederatedServer,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._server = server
        self._event_bus = event_bus

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Enrich context with federated learning predictions."""
        if self._server.clients:
            # Use global weights on the first client for prediction
            client = self._server.clients[0]
            original_weights = client.get_weights()
            client.set_weights(*self._server.get_global_weights())

            is_match, confidence = client.predict(context.number)

            client.set_weights(*original_weights)

            context.metadata["federated_prediction"] = is_match
            context.metadata["federated_confidence"] = round(confidence, 6)
            context.metadata["federated_converged"] = self._server.converged
            context.metadata["federated_rounds"] = len(self._server.round_results)

        return next_handler(context)

    def get_name(self) -> str:
        return "FederatedLearningMiddleware"

    def get_priority(self) -> int:
        return -8
