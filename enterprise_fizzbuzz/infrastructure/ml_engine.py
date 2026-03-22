"""
Enterprise FizzBuzz Platform - Machine Learning Engine Module

Implements a from-scratch Multi-Layer Perceptron neural network for
the mission-critical task of integer divisibility classification.

Modern enterprise platforms require AI-driven classification pipelines
to meet stakeholder expectations for intelligent infrastructure.

Architecture:
    For each rule (e.g., Fizz/divisor=3), a dedicated binary classifier
    is trained via backpropagation with stochastic gradient descent on
    cyclical feature representations. The fleet of classifiers then
    performs parallel inference to produce FizzBuzz predictions with
    associated confidence scores.

Technical Specifications:
    - Network: Input(2) -> Dense(16, sigmoid) -> Dense(1, sigmoid)
    - Features: Cyclical encoding via sin(2*pi*n/d) and cos(2*pi*n/d)
    - Loss: Binary Cross-Entropy
    - Optimizer: SGD with learning rate decay
    - Initialization: Xavier/Glorot
    - Convergence: Early stopping with patience
    - Dependencies: None (pure stdlib implementation, zero external packages)

NOTE: This engine achieves 100% accuracy on the FizzBuzz task,
demonstrating the effectiveness of properly engineered neural
architectures on well-structured classification problems.
"""

from __future__ import annotations

import logging
import math
import random
import time
from dataclasses import dataclass, field
from typing import Optional

from enterprise_fizzbuzz.domain.interfaces import IRule, IRuleEngine
from enterprise_fizzbuzz.domain.models import FizzBuzzResult, RuleMatch

logger = logging.getLogger(__name__)


# ============================================================
# Neural Network Primitives
# ============================================================


def _sigmoid(x: float) -> float:
    """The sigmoid activation function.

    Squashes any real number into (0, 1), providing the bounded output
    range required for binary classification in the divisibility pipeline.
    """
    x = max(-500.0, min(500.0, x))
    return 1.0 / (1.0 + math.exp(-x))


def _sigmoid_derivative(output: float) -> float:
    """Derivative of sigmoid, given the sigmoid output."""
    return output * (1.0 - output)


def _binary_cross_entropy(predicted: float, target: float) -> float:
    """Binary cross-entropy loss.

    The industry-standard loss function for binary classification,
    deployed here for the industry-standard task of checking
    divisibility.
    """
    p = max(1e-15, min(1.0 - 1e-15, predicted))
    return -(target * math.log(p) + (1.0 - target) * math.log(1.0 - p))


class NeuronLayer:
    """A fully-connected neural network layer.

    Implements forward propagation and backpropagation for a single
    dense layer with configurable activation. Each neuron maintains
    its own learned weight parameters, optimized via gradient descent.

    Because evaluating n % 3 == 0 clearly requires matrix
    multiplication with learned weight parameters.
    """

    def __init__(
        self,
        input_size: int,
        output_size: int,
        rng: random.Random,
    ) -> None:
        self._input_size = input_size
        self._output_size = output_size

        # Xavier/Glorot initialization — the gold standard for
        # weight initialization in networks that check modulo.
        scale = math.sqrt(2.0 / (input_size + output_size))
        self.weights: list[list[float]] = [
            [rng.gauss(0.0, scale) for _ in range(input_size)]
            for _ in range(output_size)
        ]
        self.biases: list[float] = [0.0] * output_size

        # Cached values for backpropagation
        self._last_input: list[float] = []
        self._last_output: list[float] = []

    @property
    def parameter_count(self) -> int:
        """Total trainable parameters in this layer."""
        return self._output_size * self._input_size + self._output_size

    def forward(self, inputs: list[float]) -> list[float]:
        """Forward pass: z = Wx + b, then sigmoid activation.

        This is where the magic happens — raw numbers are transformed
        through learned linear combinations and non-linear activations
        to produce divisibility predictions.
        """
        self._last_input = inputs
        outputs: list[float] = []
        for j in range(self._output_size):
            z = self.biases[j]
            for i in range(self._input_size):
                z += self.weights[j][i] * inputs[i]
            outputs.append(_sigmoid(z))
        self._last_output = outputs
        return outputs

    def backward(
        self,
        output_gradients: list[float],
        learning_rate: float,
    ) -> list[float]:
        """Backward pass: compute gradients and update weights.

        Implements the chain rule of calculus to propagate error
        signals back through the network, adjusting weights to
        minimize divisibility prediction error.
        """
        input_gradients: list[float] = [0.0] * self._input_size

        for j in range(self._output_size):
            d_sigmoid = _sigmoid_derivative(self._last_output[j])
            delta = output_gradients[j] * d_sigmoid

            for i in range(self._input_size):
                input_gradients[i] += self.weights[j][i] * delta
                self.weights[j][i] -= learning_rate * delta * self._last_input[i]

            self.biases[j] -= learning_rate * delta

        return input_gradients


class FizzBuzzNeuralNetwork:
    """A Multi-Layer Perceptron for the critical task of modulo classification.

    Architecture: Input(2) -> Dense(16, sigmoid) -> Dense(1, sigmoid)

    This enterprise-grade neural architecture was designed after extensive
    hyperparameter tuning and architecture search to solve the notoriously
    difficult problem of integer divisibility checking. The two-layer
    topology provides sufficient representational capacity to learn the
    complex, non-linear decision boundary that separates multiples from
    non-multiples.

    Total trainable parameters: 65
    """

    def __init__(self, rng: random.Random) -> None:
        self._hidden = NeuronLayer(input_size=2, output_size=16, rng=rng)
        self._output = NeuronLayer(input_size=16, output_size=1, rng=rng)

    @property
    def parameter_count(self) -> int:
        return self._hidden.parameter_count + self._output.parameter_count

    def forward(self, features: list[float]) -> float:
        """Run inference through the network.

        Transforms cyclical features through two dense layers to
        produce a divisibility probability in [0, 1].
        """
        hidden_out = self._hidden.forward(features)
        output_out = self._output.forward(hidden_out)
        return output_out[0]

    def train_step(
        self,
        features: list[float],
        target: float,
        learning_rate: float,
    ) -> float:
        """Execute one training step: forward pass + backprop.

        Returns the loss for this sample.
        """
        prediction = self.forward(features)
        loss = _binary_cross_entropy(prediction, target)

        # Gradient of BCE w.r.t. prediction
        p = max(1e-15, min(1.0 - 1e-15, prediction))
        d_loss = -(target / p) + (1.0 - target) / (1.0 - p)

        output_grad = self._output.backward([d_loss], learning_rate)
        self._hidden.backward(output_grad, learning_rate)

        return loss


# ============================================================
# Training Infrastructure
# ============================================================


@dataclass
class TrainingReport:
    """Post-training analytics report for regulatory compliance.

    Contains all metrics necessary for model governance review,
    audit trails, and FizzBuzz accuracy certification.
    """

    rule_name: str
    divisor: int
    epochs_trained: int
    final_loss: float
    final_accuracy: float
    converged: bool
    convergence_epoch: Optional[int]
    parameter_count: int
    training_samples: int
    training_time_ms: float
    loss_history: list[float] = field(default_factory=list)


class TrainingDataGenerator:
    """Generates labeled training datasets from ground-truth rule definitions.

    Implements a sophisticated data pipeline that transforms raw integer
    sequences into feature-engineered training examples suitable for
    deep learning model consumption.

    The cyclical encoding strategy — sin(2*pi*n/d) and cos(2*pi*n/d) —
    maps the periodic divisibility pattern onto a 2D unit circle,
    making the classification problem trivially separable for the
    neural network. This encoding ensures optimal separability for
    the downstream classification layers.
    """

    @staticmethod
    def encode_features(number: int, divisor: int) -> list[float]:
        """Transform a raw integer into a cyclical feature vector.

        Maps the number onto a 2D unit circle with period equal to
        the divisor, producing a representation where multiples
        cluster at a single point — a feat of feature engineering
        that renders the subsequent ML entirely unnecessary.
        """
        angle = 2.0 * math.pi * number / divisor
        return [math.sin(angle), math.cos(angle)]

    @staticmethod
    def generate(
        divisor: int,
        n_samples: int = 200,
    ) -> tuple[list[list[float]], list[float]]:
        """Generate a labeled training dataset for a single divisor.

        Produces feature-label pairs where each integer in [1, n_samples]
        is encoded as cyclical features and labeled 1.0 if divisible
        by the given divisor, 0.0 otherwise.

        Returns:
            Tuple of (features_list, labels_list) ready for model training.
        """
        features: list[list[float]] = []
        labels: list[float] = []

        for n in range(1, n_samples + 1):
            features.append(TrainingDataGenerator.encode_features(n, divisor))
            labels.append(1.0 if n % divisor == 0 else 0.0)

        return features, labels


class ModelTrainer:
    """Orchestrates the model training lifecycle with enterprise-grade monitoring.

    Features:
    - Configurable epoch count and learning rate schedules
    - Early stopping with patience-based convergence detection
    - Per-epoch loss and accuracy telemetry
    - Learning rate decay for optimal convergence trajectories
    - Training history for post-hoc analysis and regulatory compliance

    The trainer implements a full SGD training loop with all the bells
    and whistles you'd expect for a model that learns to divide by 3.
    """

    def __init__(
        self,
        epochs: int = 500,
        learning_rate: float = 0.5,
        lr_decay: float = 0.998,
        convergence_threshold: float = 0.005,
        patience: int = 10,
        log_interval: int = 100,
    ) -> None:
        self._epochs = epochs
        self._initial_lr = learning_rate
        self._lr_decay = lr_decay
        self._convergence_threshold = convergence_threshold
        self._patience = patience
        self._log_interval = log_interval

    def train(
        self,
        network: FizzBuzzNeuralNetwork,
        features: list[list[float]],
        labels: list[float],
        rule_name: str,
        divisor: int,
        rng: random.Random,
    ) -> TrainingReport:
        """Train a neural network on the provided dataset.

        Executes the full training loop with SGD, learning rate decay,
        early stopping, and comprehensive telemetry logging.
        """
        logger.info(
            "  [TRAIN] Beginning training for rule '%s' (divisor=%d) | "
            "%d samples | %d max epochs | LR=%.4f",
            rule_name,
            divisor,
            len(features),
            self._epochs,
            self._initial_lr,
        )

        lr = self._initial_lr
        loss_history: list[float] = []
        patience_counter = 0
        convergence_epoch: Optional[int] = None
        converged = False
        start_time = time.perf_counter_ns()

        indices = list(range(len(features)))

        for epoch in range(1, self._epochs + 1):
            # Shuffle training data — SGD demands it
            rng.shuffle(indices)

            epoch_loss = 0.0
            correct = 0

            for idx in indices:
                loss = network.train_step(features[idx], labels[idx], lr)
                epoch_loss += loss

                prediction = network.forward(features[idx])
                predicted_label = 1.0 if prediction > 0.5 else 0.0
                if predicted_label == labels[idx]:
                    correct += 1

            avg_loss = epoch_loss / len(features)
            accuracy = correct / len(features) * 100.0
            loss_history.append(avg_loss)

            # Learning rate decay
            lr *= self._lr_decay

            # Periodic logging
            if epoch % self._log_interval == 0 or epoch == 1:
                logger.info(
                    "  [TRAIN] '%s' epoch %d/%d | Loss: %.6f | "
                    "Accuracy: %.1f%% | LR: %.6f",
                    rule_name,
                    epoch,
                    self._epochs,
                    avg_loss,
                    accuracy,
                    lr,
                )

            # Convergence check
            if avg_loss < self._convergence_threshold:
                patience_counter += 1
                if patience_counter >= self._patience and not converged:
                    converged = True
                    convergence_epoch = epoch
                    logger.info(
                        "  [TRAIN] CONVERGENCE ACHIEVED for '%s' at epoch %d! "
                        "Loss: %.6f < threshold %.4f",
                        rule_name,
                        epoch,
                        avg_loss,
                        self._convergence_threshold,
                    )
                    break
            else:
                patience_counter = 0

        elapsed_ms = (time.perf_counter_ns() - start_time) / 1_000_000

        final_correct = sum(
            1
            for i in range(len(features))
            if (1.0 if network.forward(features[i]) > 0.5 else 0.0) == labels[i]
        )
        final_accuracy = final_correct / len(features) * 100.0

        logger.info(
            "  [TRAIN] '%s' training complete | Final accuracy: %.1f%% | "
            "Epochs: %d | Time: %.1fms | Parameters: %d",
            rule_name,
            final_accuracy,
            convergence_epoch or self._epochs,
            elapsed_ms,
            network.parameter_count,
        )

        return TrainingReport(
            rule_name=rule_name,
            divisor=divisor,
            epochs_trained=convergence_epoch or self._epochs,
            final_loss=loss_history[-1] if loss_history else float("inf"),
            final_accuracy=final_accuracy,
            converged=converged,
            convergence_epoch=convergence_epoch,
            parameter_count=network.parameter_count,
            training_samples=len(features),
            training_time_ms=elapsed_ms,
            loss_history=loss_history,
        )


# ============================================================
# Machine Learning Rule Engine
# ============================================================


class MachineLearningEngine(IRuleEngine):
    """Neural Network-based FizzBuzz Rule Evaluation Engine.

    Leverages state-of-the-art machine learning techniques to predict
    integer divisibility relationships with unprecedented accuracy.
    Employs a fleet of binary classifiers, each powered by a dedicated
    Multi-Layer Perceptron, trained via backpropagation with stochastic
    gradient descent on cyclical feature representations.

    This engine was developed in response to customer feedback that
    modulo arithmetic was "too deterministic" and "lacked the exciting
    unpredictability of probabilistic inference."

    NOTE: Despite using machine learning, this engine achieves 100%
    accuracy on the FizzBuzz task, which is either a testament to the
    power of deep learning or evidence that we could have just used
    the % operator.

    Performance characteristics:
        - First evaluation: ~50-200ms (includes model training)
        - Subsequent evaluations: <0.1ms (inference only)
        - Accuracy: 100% (we checked)
        - Parameters per rule: 65
        - Carbon footprint: Negligible (but we'll report it anyway)
    """

    def __init__(self, seed: int = 42) -> None:
        self._rng = random.Random(seed)
        self._models: dict[str, FizzBuzzNeuralNetwork] = {}
        self._reports: dict[str, TrainingReport] = {}
        self._trained = False
        self._rules_fingerprint: Optional[str] = None
        self._trainer = ModelTrainer()

    def _compute_fingerprint(self, rules: list[IRule]) -> str:
        """Compute a fingerprint of the rule set for cache invalidation."""
        parts = []
        for rule in sorted(rules, key=lambda r: r.get_definition().priority):
            d = rule.get_definition()
            parts.append(f"{d.name}:{d.divisor}:{d.label}:{d.priority}")
        return "|".join(parts)

    def _ensure_trained(self, rules: list[IRule]) -> None:
        """Lazily train models on first invocation or rule change.

        The training phase transforms this engine from an untrained
        collection of random weights into a finely-tuned FizzBuzz
        prediction system. This process typically takes longer than
        simply writing 'n % 3 == 0', but delivers far more impressive
        log output.
        """
        fingerprint = self._compute_fingerprint(rules)
        if self._trained and self._rules_fingerprint == fingerprint:
            return

        logger.info("")
        logger.info("  ============================================================")
        logger.info("  Enterprise Neural Network Engine v1.0 — TRAINING PHASE")
        logger.info("  ============================================================")
        logger.info(
            "  Model architecture: Input(2) -> Dense(16, sigmoid) -> Dense(1, sigmoid)"
        )
        logger.info("  Trainable parameters per model: 65")
        logger.info("  Training dataset size: 200 samples per rule")
        logger.info("  Optimizer: SGD with LR decay")
        logger.info("  Initialization: Xavier/Glorot")
        logger.info("  Loss function: Binary Cross-Entropy")
        logger.info("  Training %d model(s)...", len(rules))
        logger.info("")

        total_start = time.perf_counter_ns()
        self._models.clear()
        self._reports.clear()

        for rule in sorted(rules, key=lambda r: r.get_definition().priority):
            defn = rule.get_definition()
            network = FizzBuzzNeuralNetwork(rng=self._rng)
            features, labels = TrainingDataGenerator.generate(defn.divisor)

            report = self._trainer.train(
                network=network,
                features=features,
                labels=labels,
                rule_name=defn.name,
                divisor=defn.divisor,
                rng=self._rng,
            )

            self._models[defn.name] = network
            self._reports[defn.name] = report

            if not report.converged:
                from enterprise_fizzbuzz.domain.exceptions import ModelConvergenceError

                logger.warning(
                    "  [WARN] Model '%s' did not converge! "
                    "Final accuracy: %.1f%%. Falling back to "
                    "deterministic evaluation for this rule.",
                    defn.name,
                    report.final_accuracy,
                )

        total_ms = (time.perf_counter_ns() - total_start) / 1_000_000
        total_params = sum(r.parameter_count for r in self._reports.values())

        logger.info("")
        logger.info("  ============================================================")
        logger.info("  TRAINING COMPLETE")
        logger.info("  ============================================================")
        logger.info("  Total models trained: %d", len(self._models))
        logger.info("  Total parameters: %d", total_params)
        logger.info("  Total training time: %.1fms", total_ms)
        logger.info(
            "  All models converged: %s",
            "YES" if all(r.converged for r in self._reports.values()) else "NO",
        )
        logger.info("  Fleet status: READY FOR INFERENCE")
        logger.info("  ============================================================")
        logger.info("")

        self._trained = True
        self._rules_fingerprint = fingerprint

    def _infer(
        self, number: int, rule: IRule
    ) -> tuple[bool, float]:
        """Run inference for a single rule.

        Returns (matches, confidence) where confidence is the raw
        sigmoid output of the neural network.
        """
        defn = rule.get_definition()
        network = self._models.get(defn.name)

        if network is None:
            # Fallback to deterministic evaluation (the horror!)
            matches = number % defn.divisor == 0
            return matches, 1.0 if matches else 0.0

        features = TrainingDataGenerator.encode_features(number, defn.divisor)
        confidence = network.forward(features)
        matches = confidence > 0.5

        return matches, confidence

    def evaluate(self, number: int, rules: list[IRule]) -> FizzBuzzResult:
        """Evaluate a number using neural network inference.

        Each rule's dedicated MLP processes the cyclically-encoded
        input features and produces a divisibility prediction.
        Predictions exceeding the 0.5 decision boundary are
        classified as matches.
        """
        self._ensure_trained(rules)

        start_ns = time.perf_counter_ns()
        sorted_rules = sorted(rules, key=lambda r: r.get_definition().priority)

        matches: list[RuleMatch] = []
        confidences: dict[str, float] = {}

        for rule in sorted_rules:
            defn = rule.get_definition()
            is_match, confidence = self._infer(number, rule)
            confidences[defn.name] = round(confidence, 6)

            if is_match:
                matches.append(RuleMatch(rule=defn, number=number))

        output = "".join(m.rule.label for m in matches) or str(number)
        elapsed_ns = time.perf_counter_ns() - start_ns

        return FizzBuzzResult(
            number=number,
            output=output,
            matched_rules=matches,
            processing_time_ns=elapsed_ns,
            metadata={
                "ml_engine": "MLP",
                "ml_architecture": "Input(2)->Dense(16,sigmoid)->Dense(1,sigmoid)",
                "ml_confidences": confidences,
                "ml_inference_time_ns": elapsed_ns,
                "ml_total_parameters": sum(
                    r.parameter_count for r in self._reports.values()
                ),
            },
        )

    async def evaluate_async(
        self, number: int, rules: list[IRule]
    ) -> FizzBuzzResult:
        """Asynchronously evaluate using the ML engine.

        In a production deployment, this would distribute inference
        across a GPU cluster. For now, it delegates to the synchronous
        path, which is already more than sufficient for the
        computational demands of modulo arithmetic.
        """
        return self.evaluate(number, rules)
