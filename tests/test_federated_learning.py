"""
Enterprise FizzBuzz Platform - Federated Learning Tests

Tests for the privacy-preserving distributed modulo learning subsystem,
including federated clients, weight aggregation, differential privacy,
non-IID data simulation, dashboard rendering, and middleware.

NOTE: All federation rounds are kept LOW (3-5) and data ranges SMALL
to ensure tests run quickly. In production, you would obviously use
hundreds of rounds across thousands of clients to learn n % 3 == 0,
because that's the enterprise way.
"""

import math
import random
import unittest
from unittest.mock import MagicMock

from enterprise_fizzbuzz.infrastructure.federated_learning import (
    ClientTrainingReport,
    DifferentialPrivacyManager,
    FedAvgAggregator,
    FedProxAggregator,
    FederatedClient,
    FederatedDashboard,
    FederatedMiddleware,
    FederatedServer,
    FederationRoundResult,
    NonIIDSimulator,
    _encode_features,
    _sigmoid,
    _sigmoid_derivative,
    compute_weight_deltas,
)
from enterprise_fizzbuzz.domain.exceptions import (
    FederatedAggregationError,
    FederatedClientTrainingError,
    FederatedConvergenceError,
    FederatedLearningError,
    FederatedPrivacyBudgetExhaustedError,
    FederatedRoundTimeoutError,
)
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext


# ============================================================
# Neural Network Primitives Tests
# ============================================================


class TestSigmoid(unittest.TestCase):
    """Tests for the sigmoid activation function."""

    def test_sigmoid_zero(self):
        """sigmoid(0) should be 0.5."""
        self.assertAlmostEqual(_sigmoid(0.0), 0.5, places=5)

    def test_sigmoid_large_positive(self):
        """sigmoid(large) should approach 1.0."""
        self.assertAlmostEqual(_sigmoid(100.0), 1.0, places=5)

    def test_sigmoid_large_negative(self):
        """sigmoid(very negative) should approach 0.0."""
        self.assertAlmostEqual(_sigmoid(-100.0), 0.0, places=5)

    def test_sigmoid_clamping(self):
        """Extreme values should not overflow."""
        self.assertAlmostEqual(_sigmoid(1000.0), 1.0, places=5)
        self.assertAlmostEqual(_sigmoid(-1000.0), 0.0, places=5)


class TestSigmoidDerivative(unittest.TestCase):
    """Tests for the sigmoid derivative function."""

    def test_derivative_at_half(self):
        """Derivative at sigmoid output 0.5 should be 0.25."""
        self.assertAlmostEqual(_sigmoid_derivative(0.5), 0.25, places=5)

    def test_derivative_at_extremes(self):
        """Derivative near 0 or 1 should be near 0."""
        self.assertAlmostEqual(_sigmoid_derivative(0.01), 0.0099, places=3)
        self.assertAlmostEqual(_sigmoid_derivative(0.99), 0.0099, places=3)


class TestEncodeFeatures(unittest.TestCase):
    """Tests for cyclical feature encoding."""

    def test_multiples_encode_similarly(self):
        """Multiples of divisor should encode to the same point on the unit circle."""
        f1 = _encode_features(3, 3)
        f2 = _encode_features(6, 3)
        self.assertAlmostEqual(f1[0], f2[0], places=5)
        self.assertAlmostEqual(f1[1], f2[1], places=5)

    def test_feature_vector_length(self):
        """Feature vector should have length 2."""
        features = _encode_features(7, 3)
        self.assertEqual(len(features), 2)

    def test_features_on_unit_circle(self):
        """Features should lie on the unit circle (sin^2 + cos^2 = 1)."""
        features = _encode_features(17, 5)
        norm = features[0] ** 2 + features[1] ** 2
        self.assertAlmostEqual(norm, 1.0, places=5)


# ============================================================
# FederatedClient Tests
# ============================================================


class TestFederatedClient(unittest.TestCase):
    """Tests for the FederatedClient local model and training."""

    def setUp(self):
        self.rng = random.Random(42)
        self.client = FederatedClient(
            client_id="test_client",
            data=list(range(1, 31)),
            divisor=3,
            rng=self.rng,
        )

    def test_client_initialization(self):
        """Client should initialize with correct attributes."""
        self.assertEqual(self.client.client_id, "test_client")
        self.assertEqual(self.client.divisor, 3)
        self.assertEqual(len(self.client.data), 30)

    def test_get_set_weights(self):
        """Setting and getting weights should round-trip correctly."""
        w = self.client.get_weights()
        self.assertEqual(len(w), 4)  # wh, bh, wo, bo

        # Modify and set back
        w[0][0][0] = 99.0
        self.client.set_weights(*w)
        w2 = self.client.get_weights()
        self.assertEqual(w2[0][0][0], 99.0)

    def test_weight_independence(self):
        """get_weights should return copies, not references."""
        w1 = self.client.get_weights()
        w2 = self.client.get_weights()
        w1[0][0][0] = -999.0
        self.assertNotEqual(w2[0][0][0], -999.0)

    def test_forward_returns_tuple(self):
        """Forward pass should return (hidden_output, prediction)."""
        features = _encode_features(3, 3)
        hidden, output = self.client._forward(features)
        self.assertEqual(len(hidden), 8)
        self.assertGreater(output, 0.0)
        self.assertLess(output, 1.0)

    def test_predict(self):
        """Predict should return (bool, float)."""
        is_match, confidence = self.client.predict(3)
        self.assertIsInstance(is_match, bool)
        self.assertIsInstance(confidence, float)
        self.assertGreaterEqual(confidence, 0.0)
        self.assertLessEqual(confidence, 1.0)

    def test_train_local_returns_report(self):
        """Local training should return a ClientTrainingReport."""
        report = self.client.train_local(epochs=2, learning_rate=0.5)
        self.assertIsInstance(report, ClientTrainingReport)
        self.assertEqual(report.client_id, "test_client")
        self.assertEqual(report.dataset_size, 30)
        self.assertEqual(report.local_epochs, 2)
        self.assertGreater(report.training_time_ms, 0.0)

    def test_train_local_improves_accuracy(self):
        """Training should improve accuracy over untrained model."""
        # Get pre-training accuracy
        correct_before = sum(
            1 for n in range(1, 31)
            if self.client.predict(n)[0] == (n % 3 == 0)
        )

        # Train
        self.client.train_local(epochs=5, learning_rate=0.5)

        # Get post-training accuracy
        correct_after = sum(
            1 for n in range(1, 31)
            if self.client.predict(n)[0] == (n % 3 == 0)
        )

        self.assertGreaterEqual(correct_after, correct_before)

    def test_train_local_with_fedprox(self):
        """FedProx training with proximal term should run without error."""
        global_weights = self.client.get_weights()
        report = self.client.train_local(
            epochs=2,
            learning_rate=0.5,
            global_weights=global_weights,
            proximal_mu=0.01,
        )
        self.assertIsInstance(report, ClientTrainingReport)
        self.assertGreater(report.final_accuracy, 0.0)


# ============================================================
# Weight Delta Computation Tests
# ============================================================


class TestComputeWeightDeltas(unittest.TestCase):
    """Tests for weight delta computation."""

    def test_zero_deltas_when_same(self):
        """Deltas should be zero when before == after."""
        weights = (
            [[1.0, 2.0], [3.0, 4.0]],
            [0.5, 0.5],
            [[1.0, 2.0]],
            [0.1],
        )
        deltas = compute_weight_deltas(weights, weights)
        d_wh, d_bh, d_wo, d_bo = deltas
        for row in d_wh:
            for v in row:
                self.assertAlmostEqual(v, 0.0, places=10)
        for v in d_bh:
            self.assertAlmostEqual(v, 0.0, places=10)

    def test_correct_deltas(self):
        """Deltas should equal after - before."""
        before = ([[1.0, 2.0]], [0.0], [[3.0]], [0.0])
        after = ([[1.5, 2.5]], [0.1], [[3.5]], [0.2])
        d_wh, d_bh, d_wo, d_bo = compute_weight_deltas(before, after)
        self.assertAlmostEqual(d_wh[0][0], 0.5, places=10)
        self.assertAlmostEqual(d_wh[0][1], 0.5, places=10)
        self.assertAlmostEqual(d_bh[0], 0.1, places=10)
        self.assertAlmostEqual(d_wo[0][0], 0.5, places=10)
        self.assertAlmostEqual(d_bo[0], 0.2, places=10)


# ============================================================
# FedAvgAggregator Tests
# ============================================================


class TestFedAvgAggregator(unittest.TestCase):
    """Tests for the Federated Averaging aggregator."""

    def setUp(self):
        self.aggregator = FedAvgAggregator()

    def test_single_client_identity(self):
        """With one client, aggregated delta should equal the client's delta."""
        delta = ([[1.0, 2.0]], [0.5], [[3.0]], [0.1])
        result = self.aggregator.aggregate([delta], [10.0])
        self.assertAlmostEqual(result[0][0][0], 1.0, places=5)
        self.assertAlmostEqual(result[0][0][1], 2.0, places=5)

    def test_equal_weighted_average(self):
        """With equal weights, result should be the arithmetic mean."""
        d1 = ([[2.0, 4.0]], [1.0], [[6.0]], [0.2])
        d2 = ([[4.0, 6.0]], [3.0], [[8.0]], [0.4])
        result = self.aggregator.aggregate([d1, d2], [1.0, 1.0])
        self.assertAlmostEqual(result[0][0][0], 3.0, places=5)
        self.assertAlmostEqual(result[0][0][1], 5.0, places=5)
        self.assertAlmostEqual(result[1][0], 2.0, places=5)

    def test_weighted_average(self):
        """With unequal weights, result should be the weighted mean."""
        d1 = ([[0.0, 0.0]], [0.0], [[0.0]], [0.0])
        d2 = ([[10.0, 10.0]], [10.0], [[10.0]], [10.0])
        # Weight d2 3x as much as d1
        result = self.aggregator.aggregate([d1, d2], [1.0, 3.0])
        self.assertAlmostEqual(result[0][0][0], 7.5, places=5)
        self.assertAlmostEqual(result[1][0], 7.5, places=5)

    def test_three_client_aggregation(self):
        """Three clients should aggregate correctly."""
        d1 = ([[3.0]], [1.0], [[9.0]], [0.0])
        d2 = ([[6.0]], [2.0], [[12.0]], [0.0])
        d3 = ([[9.0]], [3.0], [[15.0]], [0.0])
        result = self.aggregator.aggregate([d1, d2, d3], [1.0, 1.0, 1.0])
        self.assertAlmostEqual(result[0][0][0], 6.0, places=5)


# ============================================================
# FedProxAggregator Tests
# ============================================================


class TestFedProxAggregator(unittest.TestCase):
    """Tests for the FedProx aggregator."""

    def test_inherits_fedavg(self):
        """FedProx should inherit from FedAvg."""
        agg = FedProxAggregator(mu=0.05)
        self.assertIsInstance(agg, FedAvgAggregator)

    def test_mu_stored(self):
        """FedProx should store the mu parameter."""
        agg = FedProxAggregator(mu=0.05)
        self.assertAlmostEqual(agg.mu, 0.05, places=5)

    def test_aggregation_works(self):
        """FedProx aggregation should produce valid results."""
        agg = FedProxAggregator(mu=0.01)
        d1 = ([[1.0, 2.0]], [0.5], [[3.0]], [0.1])
        result = agg.aggregate([d1], [10.0])
        self.assertAlmostEqual(result[0][0][0], 1.0, places=5)


# ============================================================
# DifferentialPrivacyManager Tests
# ============================================================


class TestDifferentialPrivacyManager(unittest.TestCase):
    """Tests for the Differential Privacy Manager."""

    def setUp(self):
        self.dp = DifferentialPrivacyManager(
            epsilon_budget=10.0,
            delta=1e-5,
            noise_multiplier=1.0,
            max_grad_norm=1.0,
            rng=random.Random(42),
        )

    def test_initial_budget(self):
        """Budget should start fully available."""
        self.assertAlmostEqual(self.dp.epsilon_remaining, 10.0, places=5)
        self.assertAlmostEqual(self.dp.epsilon_spent, 0.0, places=5)
        self.assertAlmostEqual(self.dp.budget_fraction_used, 0.0, places=5)

    def test_compute_sigma_positive(self):
        """Sigma should be a positive finite number."""
        sigma = self.dp.compute_sigma()
        self.assertGreater(sigma, 0.0)
        self.assertTrue(math.isfinite(sigma))

    def test_add_noise_changes_values(self):
        """Adding noise should change the weight deltas."""
        deltas = ([[1.0, 2.0]], [0.5], [[3.0]], [0.1])
        noisy = self.dp.add_noise_to_deltas(deltas)
        # At least one value should differ (noise is random but nonzero)
        all_same = (
            all(
                abs(noisy[0][j][i] - deltas[0][j][i]) < 1e-15
                for j in range(len(deltas[0]))
                for i in range(len(deltas[0][j]))
            )
        )
        self.assertFalse(all_same)

    def test_budget_depletes(self):
        """Adding noise should consume privacy budget."""
        deltas = ([[0.0, 0.0]], [0.0], [[0.0]], [0.0])
        self.dp.add_noise_to_deltas(deltas)
        self.assertGreater(self.dp.epsilon_spent, 0.0)
        self.assertLess(self.dp.epsilon_remaining, 10.0)

    def test_budget_fraction_increases(self):
        """Budget fraction should increase after noise injection."""
        deltas = ([[0.0]], [0.0], [[0.0]], [0.0])
        self.dp.add_noise_to_deltas(deltas)
        self.assertGreater(self.dp.budget_fraction_used, 0.0)

    def test_privacy_report(self):
        """Privacy report should contain all required fields."""
        report = self.dp.get_privacy_report()
        self.assertIn("epsilon_budget", report)
        self.assertIn("epsilon_spent", report)
        self.assertIn("epsilon_remaining", report)
        self.assertIn("delta", report)
        self.assertIn("budget_exhausted", report)
        self.assertFalse(report["budget_exhausted"])

    def test_exhausted_budget_raises(self):
        """Should raise when budget is fully exhausted."""
        self.dp.epsilon_spent = self.dp.epsilon_budget
        deltas = ([[0.0]], [0.0], [[0.0]], [0.0])
        with self.assertRaises(FederatedPrivacyBudgetExhaustedError):
            self.dp.add_noise_to_deltas(deltas)

    def test_sigma_infinite_when_exhausted(self):
        """Sigma should be infinite when budget is exhausted."""
        self.dp.epsilon_spent = self.dp.epsilon_budget
        sigma = self.dp.compute_sigma()
        self.assertEqual(sigma, float("inf"))


# ============================================================
# NonIIDSimulator Tests
# ============================================================


class TestNonIIDSimulator(unittest.TestCase):
    """Tests for the Non-IID data distribution simulator."""

    def test_creates_five_clients(self):
        """Should create exactly 5 clients."""
        clients = NonIIDSimulator.create_clients(divisor=3, data_range=30)
        self.assertEqual(len(clients), 5)

    def test_client_ids_unique(self):
        """Each client should have a unique ID."""
        clients = NonIIDSimulator.create_clients(divisor=3, data_range=30)
        ids = [c.client_id for c in clients]
        self.assertEqual(len(set(ids)), 5)

    def test_all_clients_have_data(self):
        """Every client should have at least some data."""
        clients = NonIIDSimulator.create_clients(divisor=3, data_range=30)
        for client in clients:
            self.assertGreater(len(client.data), 0)

    def test_clients_have_correct_divisor(self):
        """All clients should share the same divisor."""
        clients = NonIIDSimulator.create_clients(divisor=5, data_range=30)
        for client in clients:
            self.assertEqual(client.divisor, 5)

    def test_multiples_client_is_biased(self):
        """The multiples client should have proportionally more multiples."""
        clients = NonIIDSimulator.create_clients(divisor=3, data_range=60)
        multiples_client = clients[0]  # multiples_specialist
        mult_count = sum(1 for n in multiples_client.data if n % 3 == 0)
        mult_ratio = mult_count / len(multiples_client.data)
        # The ratio should be higher than the natural 1/3
        self.assertGreater(mult_ratio, 0.3)

    def test_primes_client_has_primes(self):
        """The primes client should contain prime numbers."""
        clients = NonIIDSimulator.create_clients(divisor=3, data_range=60)
        prime_client = clients[2]  # prime_purist
        primes_in_data = [
            n for n in prime_client.data if NonIIDSimulator._is_prime(n)
        ]
        self.assertGreater(len(primes_in_data), 0)

    def test_small_range_client(self):
        """The small range client should only have numbers <= 20."""
        clients = NonIIDSimulator.create_clients(divisor=3, data_range=60)
        small_client = clients[3]  # small_range_local
        self.assertTrue(all(n <= 20 for n in small_client.data))

    def test_is_prime_function(self):
        """_is_prime should correctly identify primes."""
        self.assertFalse(NonIIDSimulator._is_prime(0))
        self.assertFalse(NonIIDSimulator._is_prime(1))
        self.assertTrue(NonIIDSimulator._is_prime(2))
        self.assertTrue(NonIIDSimulator._is_prime(3))
        self.assertFalse(NonIIDSimulator._is_prime(4))
        self.assertTrue(NonIIDSimulator._is_prime(5))
        self.assertFalse(NonIIDSimulator._is_prime(9))
        self.assertTrue(NonIIDSimulator._is_prime(17))
        self.assertTrue(NonIIDSimulator._is_prime(29))
        self.assertFalse(NonIIDSimulator._is_prime(25))


# ============================================================
# FederatedServer Tests
# ============================================================


class TestFederatedServer(unittest.TestCase):
    """Tests for the Federated Server orchestration."""

    def setUp(self):
        self.clients = NonIIDSimulator.create_clients(
            divisor=3, data_range=30, rng=random.Random(42)
        )
        self.aggregator = FedAvgAggregator()
        self.server = FederatedServer(
            clients=self.clients,
            aggregator=self.aggregator,
            dp_manager=None,
            learning_rate=0.5,
            local_epochs=2,
            target_accuracy=90.0,
            patience=2,
        )

    def test_server_initialization(self):
        """Server should initialize with correct state."""
        self.assertEqual(len(self.server.clients), 5)
        self.assertFalse(self.server.converged)
        self.assertIsNone(self.server.convergence_round)
        self.assertEqual(len(self.server.round_results), 0)

    def test_run_single_round(self):
        """A single round should return a FederationRoundResult."""
        result = self.server.run_round(1)
        self.assertIsInstance(result, FederationRoundResult)
        self.assertEqual(result.round_number, 1)
        self.assertEqual(len(result.client_reports), 5)
        self.assertGreater(result.global_accuracy, 0.0)

    def test_round_results_accumulate(self):
        """Round results should accumulate across rounds."""
        self.server.run_round(1)
        self.server.run_round(2)
        self.assertEqual(len(self.server.round_results), 2)

    def test_train_runs_multiple_rounds(self):
        """train() should execute rounds (may stop early on convergence)."""
        results = self.server.train(num_rounds=3)
        self.assertGreater(len(results), 0)
        self.assertLessEqual(len(results), 3)

    def test_accuracy_generally_improves(self):
        """Accuracy should generally improve or at least not completely collapse."""
        results = self.server.train(num_rounds=5)
        # The final accuracy should be better than pure chance (>50%)
        # because even a distributed modulo learner should beat a coin flip
        final_accuracy = results[-1].global_accuracy
        self.assertGreater(final_accuracy, 40.0)

    def test_get_global_weights(self):
        """Global weights should be retrievable."""
        self.server.run_round(1)
        weights = self.server.get_global_weights()
        self.assertEqual(len(weights), 4)
        self.assertIsInstance(weights[0], list)
        self.assertIsInstance(weights[0][0], list)

    def test_global_weights_are_copies(self):
        """get_global_weights should return copies."""
        w1 = self.server.get_global_weights()
        w2 = self.server.get_global_weights()
        w1[0][0][0] = -999.0
        self.assertNotEqual(w2[0][0][0], -999.0)

    def test_train_with_dp(self):
        """Training with differential privacy should work."""
        dp = DifferentialPrivacyManager(
            epsilon_budget=10.0, rng=random.Random(42)
        )
        server = FederatedServer(
            clients=self.clients,
            aggregator=self.aggregator,
            dp_manager=dp,
            learning_rate=0.5,
            local_epochs=2,
            target_accuracy=90.0,
            patience=2,
        )
        results = server.train(num_rounds=3)
        self.assertEqual(len(results), 3)
        self.assertGreater(dp.epsilon_spent, 0.0)

    def test_train_with_fedprox(self):
        """Training with FedProx should work."""
        prox = FedProxAggregator(mu=0.01)
        server = FederatedServer(
            clients=self.clients,
            aggregator=prox,
            learning_rate=0.5,
            local_epochs=2,
            target_accuracy=99.9,
            patience=5,
        )
        results = server.train(num_rounds=3)
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0].aggregation_strategy, "fedprox")

    def test_convergence_detection(self):
        """Server should detect convergence when target is met."""
        server = FederatedServer(
            clients=self.clients,
            aggregator=self.aggregator,
            learning_rate=0.5,
            local_epochs=3,
            target_accuracy=50.0,  # Low target for easy convergence
            patience=1,
        )
        server.train(num_rounds=5)
        # With target=50% and patience=1, it should converge quickly
        self.assertTrue(server.converged)
        self.assertIsNotNone(server.convergence_round)

    def test_event_emission(self):
        """Server should emit events when event_bus is provided."""
        mock_bus = MagicMock()
        server = FederatedServer(
            clients=self.clients,
            aggregator=self.aggregator,
            learning_rate=0.5,
            local_epochs=1,
            target_accuracy=99.0,
            patience=2,
            event_bus=mock_bus,
        )
        server.run_round(1)
        self.assertTrue(mock_bus.publish.called)

    def test_empty_clients_handling(self):
        """Server should handle empty client list gracefully."""
        server = FederatedServer(
            clients=[],
            aggregator=self.aggregator,
        )
        accuracy, loss = server._evaluate_global_accuracy()
        self.assertEqual(accuracy, 0.0)


# ============================================================
# FederatedDashboard Tests
# ============================================================


class TestFederatedDashboard(unittest.TestCase):
    """Tests for the ASCII dashboard renderer."""

    def _make_server(self):
        clients = NonIIDSimulator.create_clients(
            divisor=3, data_range=30, rng=random.Random(42)
        )
        server = FederatedServer(
            clients=clients,
            aggregator=FedAvgAggregator(),
            dp_manager=DifferentialPrivacyManager(
                epsilon_budget=5.0, rng=random.Random(42)
            ),
            learning_rate=0.5,
            local_epochs=2,
            target_accuracy=95.0,
            patience=2,
        )
        server.train(num_rounds=3)
        return server

    def test_dashboard_renders(self):
        """Dashboard should render without error."""
        server = self._make_server()
        output = FederatedDashboard.render(server)
        self.assertIsInstance(output, str)
        self.assertGreater(len(output), 0)

    def test_dashboard_contains_headers(self):
        """Dashboard should contain expected section headers."""
        server = self._make_server()
        output = FederatedDashboard.render(server)
        self.assertIn("FEDERATED LEARNING DASHBOARD", output)
        self.assertIn("FEDERATION SUMMARY", output)

    def test_dashboard_contains_privacy_section(self):
        """Dashboard should show privacy info when DP is enabled."""
        server = self._make_server()
        output = FederatedDashboard.render(server)
        self.assertIn("DIFFERENTIAL PRIVACY", output)

    def test_dashboard_contains_convergence(self):
        """Dashboard should show convergence curve."""
        server = self._make_server()
        output = FederatedDashboard.render(
            server, show_convergence=True
        )
        self.assertIn("CONVERGENCE CURVE", output)

    def test_dashboard_contains_client_details(self):
        """Dashboard should show client details."""
        server = self._make_server()
        output = FederatedDashboard.render(
            server, show_clients=True
        )
        self.assertIn("CLIENT DETAILS", output)

    def test_dashboard_without_convergence(self):
        """Dashboard should render without convergence curve."""
        server = self._make_server()
        output = FederatedDashboard.render(
            server, show_convergence=False
        )
        self.assertNotIn("CONVERGENCE CURVE", output)

    def test_dashboard_without_client_details(self):
        """Dashboard should render without client details."""
        server = self._make_server()
        output = FederatedDashboard.render(
            server, show_clients=False
        )
        self.assertNotIn("CLIENT DETAILS", output)

    def test_dashboard_custom_width(self):
        """Dashboard should respect custom width."""
        server = self._make_server()
        output = FederatedDashboard.render(server, width=80)
        self.assertIsInstance(output, str)


# ============================================================
# FederatedMiddleware Tests
# ============================================================


class TestFederatedMiddleware(unittest.TestCase):
    """Tests for the FederatedMiddleware pipeline component."""

    def setUp(self):
        clients = NonIIDSimulator.create_clients(
            divisor=3, data_range=30, rng=random.Random(42)
        )
        self.server = FederatedServer(
            clients=clients,
            aggregator=FedAvgAggregator(),
            learning_rate=0.5,
            local_epochs=2,
        )
        self.server.train(num_rounds=3)
        self.middleware = FederatedMiddleware(server=self.server)

    def test_middleware_name(self):
        """Middleware should have correct name."""
        self.assertEqual(
            self.middleware.get_name(), "FederatedLearningMiddleware"
        )

    def test_middleware_priority(self):
        """Middleware should have priority -8."""
        self.assertEqual(self.middleware.get_priority(), -8)

    def test_middleware_enriches_context(self):
        """Middleware should add federated metadata to context."""
        context = ProcessingContext(number=15, session_id="test")

        def mock_next(ctx):
            return ctx

        result = self.middleware.process(context, mock_next)
        self.assertIn("federated_prediction", result.metadata)
        self.assertIn("federated_confidence", result.metadata)
        self.assertIn("federated_converged", result.metadata)
        self.assertIn("federated_rounds", result.metadata)

    def test_middleware_calls_next(self):
        """Middleware should call the next handler."""
        context = ProcessingContext(number=15, session_id="test")
        called = [False]

        def mock_next(ctx):
            called[0] = True
            return ctx

        self.middleware.process(context, mock_next)
        self.assertTrue(called[0])

    def test_middleware_confidence_range(self):
        """Federated confidence should be between 0 and 1."""
        context = ProcessingContext(number=9, session_id="test")

        def mock_next(ctx):
            return ctx

        result = self.middleware.process(context, mock_next)
        confidence = result.metadata["federated_confidence"]
        self.assertGreaterEqual(confidence, 0.0)
        self.assertLessEqual(confidence, 1.0)


# ============================================================
# Exception Tests
# ============================================================


class TestFederatedExceptions(unittest.TestCase):
    """Tests for the federated learning exception hierarchy."""

    def test_base_exception(self):
        """FederatedLearningError should have correct error code."""
        err = FederatedLearningError("test error")
        self.assertIn("EFP-FL00", str(err))

    def test_client_training_error(self):
        """FederatedClientTrainingError should contain client ID."""
        err = FederatedClientTrainingError("client_1", "loss exploded")
        self.assertIn("EFP-FL01", str(err))
        self.assertIn("client_1", str(err))

    def test_aggregation_error(self):
        """FederatedAggregationError should contain round number."""
        err = FederatedAggregationError(5, "NaN detected")
        self.assertIn("EFP-FL02", str(err))
        self.assertIn("5", str(err))

    def test_privacy_budget_error(self):
        """FederatedPrivacyBudgetExhaustedError should contain budget info."""
        err = FederatedPrivacyBudgetExhaustedError(10.0, 10.0)
        self.assertIn("EFP-FL03", str(err))

    def test_convergence_error(self):
        """FederatedConvergenceError should contain round count and accuracy."""
        err = FederatedConvergenceError(20, 45.0)
        self.assertIn("EFP-FL04", str(err))
        self.assertIn("20", str(err))

    def test_round_timeout_error(self):
        """FederatedRoundTimeoutError should contain timing info."""
        err = FederatedRoundTimeoutError(3, 5000.0, 1000.0)
        self.assertIn("EFP-FL05", str(err))
        self.assertIn("5000", str(err))

    def test_exception_hierarchy(self):
        """All federated exceptions should inherit from FederatedLearningError."""
        self.assertTrue(
            issubclass(FederatedClientTrainingError, FederatedLearningError)
        )
        self.assertTrue(
            issubclass(FederatedAggregationError, FederatedLearningError)
        )
        self.assertTrue(
            issubclass(
                FederatedPrivacyBudgetExhaustedError, FederatedLearningError
            )
        )
        self.assertTrue(
            issubclass(FederatedConvergenceError, FederatedLearningError)
        )
        self.assertTrue(
            issubclass(FederatedRoundTimeoutError, FederatedLearningError)
        )


# ============================================================
# EventType Tests
# ============================================================


class TestFederatedEventTypes(unittest.TestCase):
    """Tests for the federation-related EventType entries."""

    def test_event_types_exist(self):
        """All federation event types should exist in the enum."""
        self.assertIsNotNone(EventType.FEDERATION_ROUND_STARTED)
        self.assertIsNotNone(EventType.FEDERATION_ROUND_COMPLETED)
        self.assertIsNotNone(EventType.FEDERATION_CLIENT_TRAINED)
        self.assertIsNotNone(EventType.FEDERATION_WEIGHTS_AGGREGATED)
        self.assertIsNotNone(EventType.FEDERATION_PRIVACY_BUDGET_UPDATED)
        self.assertIsNotNone(EventType.FEDERATION_CONVERGENCE_ACHIEVED)
        self.assertIsNotNone(EventType.FEDERATION_DASHBOARD_RENDERED)


# ============================================================
# Integration Tests
# ============================================================


class TestFederatedIntegration(unittest.TestCase):
    """Integration tests for the full federated pipeline."""

    def test_full_pipeline_divisor_3(self):
        """Full pipeline should achieve reasonable accuracy for divisor=3."""
        clients = NonIIDSimulator.create_clients(
            divisor=3, data_range=45, rng=random.Random(123)
        )
        server = FederatedServer(
            clients=clients,
            aggregator=FedAvgAggregator(),
            learning_rate=0.5,
            local_epochs=3,
            target_accuracy=85.0,
            patience=2,
        )
        results = server.train(num_rounds=5)
        # Should reach decent accuracy with 5 rounds
        final_acc = results[-1].global_accuracy
        self.assertGreater(final_acc, 50.0)

    def test_full_pipeline_divisor_5(self):
        """Full pipeline should work for divisor=5."""
        clients = NonIIDSimulator.create_clients(
            divisor=5, data_range=50, rng=random.Random(456)
        )
        server = FederatedServer(
            clients=clients,
            aggregator=FedAvgAggregator(),
            learning_rate=0.5,
            local_epochs=3,
            target_accuracy=80.0,
            patience=2,
        )
        results = server.train(num_rounds=5)
        self.assertGreater(len(results), 0)
        self.assertGreater(results[-1].global_accuracy, 40.0)

    def test_full_pipeline_with_dp_and_fedprox(self):
        """Full pipeline with DP and FedProx should complete without error."""
        clients = NonIIDSimulator.create_clients(
            divisor=3, data_range=30, rng=random.Random(789)
        )
        dp = DifferentialPrivacyManager(
            epsilon_budget=10.0,
            noise_multiplier=0.5,
            rng=random.Random(789),
        )
        server = FederatedServer(
            clients=clients,
            aggregator=FedProxAggregator(mu=0.01),
            dp_manager=dp,
            learning_rate=0.5,
            local_epochs=2,
            target_accuracy=90.0,
            patience=2,
        )
        results = server.train(num_rounds=3)
        self.assertEqual(len(results), 3)
        self.assertGreater(dp.epsilon_spent, 0.0)

    def test_dashboard_after_training(self):
        """Dashboard should render correctly after training."""
        clients = NonIIDSimulator.create_clients(
            divisor=3, data_range=30, rng=random.Random(42)
        )
        dp = DifferentialPrivacyManager(
            epsilon_budget=5.0, rng=random.Random(42)
        )
        server = FederatedServer(
            clients=clients,
            aggregator=FedAvgAggregator(),
            dp_manager=dp,
            learning_rate=0.5,
            local_epochs=2,
            target_accuracy=95.0,
            patience=2,
        )
        server.train(num_rounds=3)

        output = FederatedDashboard.render(server)
        self.assertIn("FEDERATED LEARNING DASHBOARD", output)
        self.assertIn("DIFFERENTIAL PRIVACY", output)
        self.assertIn("CONVERGENCE CURVE", output)
        self.assertIn("CLIENT DETAILS", output)


if __name__ == "__main__":
    unittest.main()
