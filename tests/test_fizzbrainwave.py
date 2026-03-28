"""
Enterprise FizzBuzz Platform - FizzBrainwave Brain-Computer Interface Test Suite

Comprehensive verification of the EEG signal processing pipeline, from
signal generation through artifact rejection, spectral decomposition,
mental state classification, and neural FizzBuzz decoding. These tests
ensure that every input integer produces a physiologically plausible
EEG signal whose spectral features are correctly mapped to a FizzBuzz
classification.

Correct neural decoding is essential: an incorrectly classified mental
state could lead to a wrong FizzBuzz label, undermining operator trust
in the brain-computer interface subsystem.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzbrainwave import (
    ALPHA_HIGH,
    ALPHA_LOW,
    BETA_HIGH,
    BETA_LOW,
    DEFAULT_CONFIDENCE_THRESHOLD,
    DEFAULT_SNR_THRESHOLD,
    FIZZBUZZ_CLASSES,
    GAMMA_HIGH,
    GAMMA_LOW,
    MENTAL_STATES,
    NUM_CHANNELS,
    NUM_SAMPLES,
    SAMPLE_RATE,
    THETA_HIGH,
    THETA_LOW,
    ArtifactRejector,
    BandPowers,
    BrainwaveDashboard,
    BrainwaveMiddleware,
    BrainwaveStatistics,
    DecodingResult,
    EEGEpoch,
    EEGSignalGenerator,
    MentalState,
    MentalStateClassifier,
    NeuralDecoder,
    SpectralAnalyzer,
)
from enterprise_fizzbuzz.domain.exceptions.fizzbrainwave import (
    ArtifactRejectionError,
    BrainwaveMiddlewareError,
    EEGSignalError,
    FizzBrainwaveError,
    MentalStateClassificationError,
    NeuralDecodingError,
    SpectralDecompositionError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
    RuleDefinition,
    RuleMatch,
)


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def signal_generator():
    return EEGSignalGenerator(seed=42)


@pytest.fixture
def artifact_rejector():
    return ArtifactRejector(max_rejection_rate=0.5)


@pytest.fixture
def spectral_analyzer():
    return SpectralAnalyzer()


@pytest.fixture
def mental_state_classifier():
    return MentalStateClassifier()


@pytest.fixture
def neural_decoder():
    return NeuralDecoder(confidence_threshold=0.1)


@pytest.fixture
def make_context():
    def _make(number: int) -> ProcessingContext:
        return ProcessingContext(number=number, session_id="test-brainwave")
    return _make


# ===========================================================================
# EEG Signal Generator Tests
# ===========================================================================

class TestEEGSignalGenerator:
    """Verification of synthetic EEG signal generation."""

    def test_generates_correct_number_of_channels(self, signal_generator):
        epoch = signal_generator.generate(42)
        assert len(epoch.channels) == NUM_CHANNELS

    def test_each_channel_has_correct_length(self, signal_generator):
        epoch = signal_generator.generate(7)
        for channel in epoch.channels:
            assert len(channel) == NUM_SAMPLES

    def test_deterministic_output(self, signal_generator):
        epoch1 = signal_generator.generate(15)
        epoch2 = signal_generator.generate(15)
        assert epoch1.channels[0] == epoch2.channels[0]

    def test_different_numbers_produce_different_signals(self, signal_generator):
        epoch1 = signal_generator.generate(3)
        epoch2 = signal_generator.generate(5)
        assert epoch1.channels[0] != epoch2.channels[0]

    def test_artifact_mask_has_correct_length(self, signal_generator):
        epoch = signal_generator.generate(10)
        assert len(epoch.artifact_mask) == NUM_CHANNELS


# ===========================================================================
# Artifact Rejection Tests
# ===========================================================================

class TestArtifactRejector:
    """Verification of ICA-based artifact rejection."""

    def test_clean_epoch_passes_through(self, artifact_rejector):
        epoch = EEGEpoch(
            channels=[[0.0] * 10 for _ in range(4)],
            artifact_mask=[False, False, False, False],
        )
        clean, rate = artifact_rejector.reject(epoch)
        assert len(clean.channels) == 4
        assert rate == 0.0

    def test_partial_rejection(self, artifact_rejector):
        epoch = EEGEpoch(
            channels=[[0.0] * 10 for _ in range(4)],
            artifact_mask=[True, False, False, False],
        )
        clean, rate = artifact_rejector.reject(epoch)
        assert len(clean.channels) == 3
        assert rate == pytest.approx(0.25)

    def test_excessive_rejection_raises(self):
        rejector = ArtifactRejector(max_rejection_rate=0.3)
        epoch = EEGEpoch(
            channels=[[0.0] * 10 for _ in range(4)],
            artifact_mask=[True, True, False, False],
        )
        with pytest.raises(ArtifactRejectionError):
            rejector.reject(epoch)


# ===========================================================================
# Spectral Analyzer Tests
# ===========================================================================

class TestSpectralAnalyzer:
    """Verification of frequency-band spectral decomposition."""

    def test_empty_channels_raises(self, spectral_analyzer):
        epoch = EEGEpoch(channels=[], artifact_mask=[])
        with pytest.raises(SpectralDecompositionError):
            spectral_analyzer.analyze(epoch)

    def test_returns_band_powers(self, spectral_analyzer, signal_generator):
        epoch = signal_generator.generate(42)
        powers = spectral_analyzer.analyze(epoch)
        assert powers.total > 0
        assert powers.theta >= 0
        assert powers.alpha >= 0
        assert powers.beta >= 0
        assert powers.gamma >= 0

    def test_total_power_positive(self, spectral_analyzer, signal_generator):
        epoch = signal_generator.generate(7)
        powers = spectral_analyzer.analyze(epoch)
        assert powers.total > 0


# ===========================================================================
# Band Powers Tests
# ===========================================================================

class TestBandPowers:
    """Verification of frequency band power ratio computations."""

    def test_theta_beta_ratio(self):
        powers = BandPowers(theta=4.0, beta=2.0)
        assert powers.theta_beta_ratio == pytest.approx(2.0)

    def test_alpha_gamma_ratio(self):
        powers = BandPowers(alpha=6.0, gamma=3.0)
        assert powers.alpha_gamma_ratio == pytest.approx(2.0)

    def test_zero_denominator_returns_zero(self):
        powers = BandPowers(theta=4.0, beta=0.0)
        assert powers.theta_beta_ratio == pytest.approx(0.0)


# ===========================================================================
# Mental State Classifier Tests
# ===========================================================================

class TestMentalStateClassifier:
    """Verification of mental state classification from spectral features."""

    def test_classifies_to_known_state(self, mental_state_classifier, signal_generator, spectral_analyzer):
        epoch = signal_generator.generate(42)
        # Get only artifact-free channels
        clean_channels = [ch for ch, mask in zip(epoch.channels, epoch.artifact_mask) if not mask]
        clean_epoch = EEGEpoch(channels=clean_channels, artifact_mask=[False] * len(clean_channels))
        powers = spectral_analyzer.analyze(clean_epoch)
        state = mental_state_classifier.classify(powers)
        assert state.label in MENTAL_STATES

    def test_confidence_between_zero_and_one(self, mental_state_classifier):
        powers = BandPowers(theta=1.0, alpha=2.0, beta=1.5, gamma=0.5, total=5.0)
        state = mental_state_classifier.classify(powers)
        assert 0.0 <= state.confidence <= 1.0

    def test_features_contain_expected_keys(self, mental_state_classifier):
        powers = BandPowers(theta=1.0, alpha=2.0, beta=1.5, gamma=0.5, total=5.0)
        state = mental_state_classifier.classify(powers)
        assert "theta_beta_ratio" in state.features
        assert "alpha_gamma_ratio" in state.features


# ===========================================================================
# Neural Decoder Tests
# ===========================================================================

class TestNeuralDecoder:
    """Verification of thought-to-FizzBuzz neural decoding."""

    def test_decodes_to_valid_class(self, neural_decoder):
        powers = BandPowers(theta=1.0, alpha=2.0, beta=1.5, gamma=0.5, total=5.0)
        state = MentalState(label="focused", confidence=0.8, features={})
        result = neural_decoder.decode(15, state, powers)
        assert result.label in FIZZBUZZ_CLASSES

    def test_fizzbuzz_for_divisible_by_15(self, neural_decoder):
        powers = BandPowers(theta=1.0, alpha=1.0, beta=1.0, gamma=1.0, total=4.0)
        state = MentalState(label="meditative", confidence=0.9, features={})
        result = neural_decoder.decode(15, state, powers)
        assert result.label == "FizzBuzz"

    def test_confidence_stored_in_result(self, neural_decoder):
        powers = BandPowers(theta=1.0, alpha=1.0, beta=1.0, gamma=1.0, total=4.0)
        state = MentalState(label="focused", confidence=0.8, features={})
        result = neural_decoder.decode(7, state, powers)
        assert result.confidence > 0


# ===========================================================================
# Dashboard Tests
# ===========================================================================

class TestBrainwaveDashboard:
    """Verification of the ASCII dashboard rendering."""

    def test_render_produces_output(self):
        result = DecodingResult(
            label="Fizz",
            confidence=0.85,
            mental_state=MentalState(label="relaxed", confidence=0.7, features={}),
            band_powers=BandPowers(theta=1.0, alpha=3.0, beta=1.5, gamma=0.5, total=6.0),
        )
        output = BrainwaveDashboard.render(result)
        assert "FIZZBRAINWAVE" in output
        assert "Fizz" in output


# ===========================================================================
# Middleware Tests
# ===========================================================================

class TestBrainwaveMiddleware:
    """Verification of the BCI pipeline middleware integration."""

    def test_implements_imiddleware(self):
        middleware = BrainwaveMiddleware()
        assert isinstance(middleware, IMiddleware)

    def test_get_name(self):
        middleware = BrainwaveMiddleware()
        assert middleware.get_name() == "BrainwaveMiddleware"

    def test_get_priority(self):
        middleware = BrainwaveMiddleware()
        assert middleware.get_priority() == 268

    def test_process_sets_metadata(self, make_context):
        middleware = BrainwaveMiddleware()
        ctx = make_context(7)
        result = middleware.process(ctx, lambda c: c)
        assert "brainwave_label" in result.metadata
        assert "brainwave_confidence" in result.metadata
        assert "brainwave_mental_state" in result.metadata

    def test_process_wraps_exceptions(self, make_context):
        """Unexpected exceptions are wrapped in BrainwaveMiddlewareError."""
        def bad_handler(ctx):
            raise RuntimeError("simulated failure")
        middleware = BrainwaveMiddleware()
        # We pass a handler that returns normally, but mock the signal gen to fail
        middleware._signal_gen = MagicMock()
        middleware._signal_gen.generate.side_effect = RuntimeError("signal failure")
        ctx = make_context(1)
        with pytest.raises(BrainwaveMiddlewareError):
            middleware.process(ctx, lambda c: c)


# ===========================================================================
# Exception Hierarchy Tests
# ===========================================================================

class TestExceptionHierarchy:
    """Verification of the FizzBrainwave exception hierarchy."""

    def test_base_exception_inherits_fizzbuzz_error(self):
        from enterprise_fizzbuzz.domain.exceptions._base import FizzBuzzError
        assert issubclass(FizzBrainwaveError, FizzBuzzError)

    def test_eeg_signal_error_message(self):
        err = EEGSignalError("Fp1", 1.5, 3.0)
        assert "Fp1" in str(err)
        assert "1.50" in str(err)

    def test_artifact_rejection_error_rate(self):
        err = ArtifactRejectionError(0.75, 0.5)
        assert "75.0%" in str(err)

    def test_neural_decoding_error_has_context(self):
        err = NeuralDecodingError(0.1, 0.25)
        assert err.context["confidence"] == 0.1
