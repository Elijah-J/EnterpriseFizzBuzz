"""
Enterprise FizzBuzz Platform - FizzML2 AutoML & Model Serving Platform Test Suite

Tests for the FizzML2 subsystem, which provides automated machine learning
capabilities for optimizing FizzBuzz classification models. The platform
supports model training, evaluation, serving, and lifecycle management
to ensure enterprise-grade ML operations for integer divisibility prediction.
"""

from __future__ import annotations

import pytest

from enterprise_fizzbuzz.infrastructure.fizzml2 import (
    FIZZML2_VERSION,
    MIDDLEWARE_PRIORITY,
    AutoMLEngine,
    Endpoint,
    FeatureStore,
    FizzML2Config,
    FizzML2Dashboard,
    FizzML2Middleware,
    Model,
    ModelRegistry,
    ModelStatus,
    ModelType,
    ServingEngine,
    create_fizzml2_subsystem,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def registry():
    """Fresh ModelRegistry instance for each test."""
    return ModelRegistry()


@pytest.fixture
def automl(registry):
    """AutoMLEngine wired to a fresh registry."""
    return AutoMLEngine(registry)


@pytest.fixture
def serving(registry):
    """ServingEngine wired to a fresh registry."""
    return ServingEngine(registry)


@pytest.fixture
def feature_store():
    """Fresh FeatureStore instance."""
    return FeatureStore()


# ---------------------------------------------------------------------------
# TestConstants
# ---------------------------------------------------------------------------

class TestConstants:
    """Verify module-level constants required by the subsystem wiring."""

    def test_version_string(self):
        assert FIZZML2_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 140


# ---------------------------------------------------------------------------
# TestModelRegistry
# ---------------------------------------------------------------------------

class TestModelRegistry:
    """Model lifecycle management via the central registry."""

    def test_register_returns_model(self, registry):
        model = registry.register("fizz_classifier", ModelType.CLASSIFICATION, {"author": "ml-team"})
        assert isinstance(model, Model)
        assert model.name == "fizz_classifier"
        assert model.model_type == ModelType.CLASSIFICATION
        assert model.metadata == {"author": "ml-team"}

    def test_get_registered_model(self, registry):
        registry.register("buzz_detector", ModelType.REGRESSION)
        retrieved = registry.get("buzz_detector")
        assert retrieved.name == "buzz_detector"
        assert retrieved.model_type == ModelType.REGRESSION

    def test_list_models(self, registry):
        registry.register("model_a", ModelType.CLASSIFICATION)
        registry.register("model_b", ModelType.CLUSTERING)
        models = registry.list_models()
        names = [m.name for m in models]
        assert "model_a" in names
        assert "model_b" in names
        assert len(models) >= 2

    def test_retire_model(self, registry):
        registry.register("old_model", ModelType.REGRESSION)
        registry.retire("old_model")
        model = registry.get("old_model")
        assert model.status == ModelStatus.RETIRED

    def test_get_nonexistent_raises(self, registry):
        with pytest.raises(Exception):
            registry.get("does_not_exist")


# ---------------------------------------------------------------------------
# TestAutoMLEngine
# ---------------------------------------------------------------------------

class TestAutoMLEngine:
    """Automated model training and evaluation pipeline."""

    def test_train_returns_model(self, automl):
        dataset = [{"input": i, "label": "fizz" if i % 3 == 0 else "none"} for i in range(1, 31)]
        model = automl.train("fizz_v1", dataset, ModelType.CLASSIFICATION)
        assert isinstance(model, Model)
        assert model.name == "fizz_v1"

    def test_trained_model_has_positive_accuracy(self, automl):
        dataset = [{"input": i, "label": "buzz" if i % 5 == 0 else "none"} for i in range(1, 51)]
        model = automl.train("buzz_v1", dataset, ModelType.CLASSIFICATION)
        assert model.accuracy is not None
        assert model.accuracy > 0.0

    def test_evaluate_returns_metrics(self, automl):
        dataset = [{"input": i, "label": "fizz" if i % 3 == 0 else "none"} for i in range(1, 31)]
        automl.train("eval_model", dataset, ModelType.CLASSIFICATION)
        test_data = [{"input": i, "label": "fizz" if i % 3 == 0 else "none"} for i in range(31, 61)]
        metrics = automl.evaluate("eval_model", test_data)
        assert isinstance(metrics, dict)
        assert "accuracy" in metrics or "score" in metrics or len(metrics) > 0

    def test_train_sets_status_to_ready(self, automl):
        dataset = [{"input": i, "label": "fizzbuzz" if i % 15 == 0 else "none"} for i in range(1, 31)]
        model = automl.train("ready_model", dataset, ModelType.CLASSIFICATION)
        assert model.status == ModelStatus.READY


# ---------------------------------------------------------------------------
# TestServingEngine
# ---------------------------------------------------------------------------

class TestServingEngine:
    """Model deployment and real-time prediction serving."""

    def test_deploy_returns_endpoint(self, registry, serving):
        registry.register("serve_me", ModelType.CLASSIFICATION)
        endpoint = serving.deploy("serve_me")
        assert isinstance(endpoint, Endpoint)
        assert endpoint.model_name == "serve_me"
        assert endpoint.active is True

    def test_predict_returns_value(self, registry, serving):
        registry.register("pred_model", ModelType.CLASSIFICATION)
        endpoint = serving.deploy("pred_model")
        result = serving.predict(endpoint, {"value": 15})
        assert result is not None

    def test_undeploy_deactivates(self, registry, serving):
        registry.register("temp_model", ModelType.REGRESSION)
        endpoint = serving.deploy("temp_model")
        serving.undeploy(endpoint)
        endpoints = serving.list_endpoints()
        active = [e for e in endpoints if e.model_name == "temp_model" and e.active]
        assert len(active) == 0

    def test_list_endpoints(self, registry, serving):
        registry.register("ep_model_1", ModelType.CLASSIFICATION)
        registry.register("ep_model_2", ModelType.CLUSTERING)
        serving.deploy("ep_model_1")
        serving.deploy("ep_model_2")
        endpoints = serving.list_endpoints()
        assert len(endpoints) >= 2
        assert all(isinstance(e, Endpoint) for e in endpoints)

    def test_predict_on_fizzbuzz_data(self, automl, serving):
        """Deploy a trained model and verify it can predict on FizzBuzz inputs."""
        dataset = [{"input": i, "label": "fizzbuzz" if i % 15 == 0 else "fizz" if i % 3 == 0 else "buzz" if i % 5 == 0 else str(i)} for i in range(1, 101)]
        automl.train("fb_predictor", dataset, ModelType.CLASSIFICATION)
        endpoint = serving.deploy("fb_predictor")
        prediction = serving.predict(endpoint, {"value": 30})
        assert prediction is not None


# ---------------------------------------------------------------------------
# TestFeatureStore
# ---------------------------------------------------------------------------

class TestFeatureStore:
    """Central repository for ML feature definitions."""

    def test_register_feature(self, feature_store):
        feature_store.register_feature("divisor_3", "bool", "Whether input is divisible by 3")
        feature = feature_store.get_feature("divisor_3")
        assert feature is not None

    def test_get_feature_attributes(self, feature_store):
        feature_store.register_feature("modulo_5", "int", "Modulo 5 remainder")
        feature = feature_store.get_feature("modulo_5")
        assert "modulo_5" in str(feature) or hasattr(feature, "name")

    def test_list_features(self, feature_store):
        feature_store.register_feature("feat_a", "float", "Feature A")
        feature_store.register_feature("feat_b", "str", "Feature B")
        features = feature_store.list_features()
        assert len(features) >= 2


# ---------------------------------------------------------------------------
# TestFizzML2Dashboard
# ---------------------------------------------------------------------------

class TestFizzML2Dashboard:
    """Dashboard rendering for ML operations visibility."""

    def test_render_returns_string(self):
        registry = ModelRegistry()
        dashboard = FizzML2Dashboard(registry)
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_contains_model_info(self):
        registry = ModelRegistry()
        registry.register("dashboard_model", ModelType.CLASSIFICATION, {"version": "2.0"})
        dashboard = FizzML2Dashboard(registry)
        output = dashboard.render()
        assert "dashboard_model" in output or "model" in output.lower()


# ---------------------------------------------------------------------------
# TestFizzML2Middleware
# ---------------------------------------------------------------------------

class TestFizzML2Middleware:
    """Middleware integration for the FizzBuzz processing pipeline."""

    def test_middleware_name(self):
        middleware = FizzML2Middleware()
        assert middleware.get_name() == "fizzml2"

    def test_middleware_priority(self):
        middleware = FizzML2Middleware()
        assert middleware.get_priority() == 140

    def test_process_delegates_to_next(self):
        """Middleware must call the next handler in the chain."""
        middleware = FizzML2Middleware()
        called = {"flag": False}

        def mock_next(ctx):
            called["flag"] = True
            return ctx

        from enterprise_fizzbuzz.domain.models import ProcessingContext
        ctx = ProcessingContext(number=15, session_id="test")
        middleware.process(ctx, mock_next)
        assert called["flag"] is True, "Middleware must delegate to the next handler"


# ---------------------------------------------------------------------------
# TestCreateSubsystem
# ---------------------------------------------------------------------------

class TestCreateSubsystem:
    """Factory function that wires up the entire FizzML2 subsystem."""

    def test_returns_tuple_of_correct_types(self):
        result = create_fizzml2_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 4
        registry, serving, dashboard, middleware = result
        assert isinstance(registry, ModelRegistry)
        assert isinstance(serving, ServingEngine)
        assert isinstance(dashboard, FizzML2Dashboard)
        assert isinstance(middleware, FizzML2Middleware)

    def test_registry_has_default_models(self):
        registry, serving, dashboard, middleware = create_fizzml2_subsystem()
        models = registry.list_models()
        assert len(models) >= 1, "Subsystem should register at least one default model"

    def test_can_predict_via_subsystem(self):
        """End-to-end: create subsystem, deploy a model, run prediction."""
        registry, serving, dashboard, middleware = create_fizzml2_subsystem()
        models = registry.list_models()
        assert len(models) > 0
        model = models[0]
        endpoint = serving.deploy(model.name)
        result = serving.predict(endpoint, {"value": 42})
        assert result is not None
