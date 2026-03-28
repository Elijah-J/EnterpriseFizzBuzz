"""
Enterprise FizzBuzz Platform - FizzBrainwave: Brain-Computer Interface

Processes electroencephalographic (EEG) signals to decode the operator's
mental state and translate neural activity into FizzBuzz classifications.
The pipeline consists of four stages:

1. **Signal Acquisition** — Simulates a multi-channel EEG recording at 256 Hz
   with realistic 1/f spectral characteristics and superimposed alpha/beta/
   theta/gamma oscillations. The relative power in each band reflects the
   operator's cognitive state.

2. **Artifact Rejection** — Applies Independent Component Analysis (ICA) to
   identify and remove ocular, muscular, and cardiac artifacts. Epochs with
   residual artifact power above the threshold are discarded.

3. **Spectral Decomposition** — Computes the power spectral density via
   Welch's method with Hanning windowing, then extracts frequency-band
   power ratios (theta/beta for attention, alpha/gamma for relaxation).

4. **Neural Decoding** — Maps the spectral features to a FizzBuzz label
   using a Linear Discriminant Analysis (LDA) model. The model projects
   the feature vector onto discriminant axes that separate the four
   FizzBuzz classes (Plain, Fizz, Buzz, FizzBuzz).

The input integer seeds the pseudorandom EEG generator, ensuring that
each number produces a deterministic but physiologically plausible signal.
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SAMPLE_RATE = 256  # Hz
NUM_CHANNELS = 8
EPOCH_DURATION = 1.0  # seconds
NUM_SAMPLES = int(SAMPLE_RATE * EPOCH_DURATION)

# Frequency band boundaries (Hz)
THETA_LOW, THETA_HIGH = 4.0, 8.0
ALPHA_LOW, ALPHA_HIGH = 8.0, 13.0
BETA_LOW, BETA_HIGH = 13.0, 30.0
GAMMA_LOW, GAMMA_HIGH = 30.0, 50.0

# Default thresholds
DEFAULT_SNR_THRESHOLD = 3.0  # dB
DEFAULT_ARTIFACT_MAX_RATE = 0.5
DEFAULT_CONFIDENCE_THRESHOLD = 0.25

# Mental states
MENTAL_STATES = ["focused", "relaxed", "drowsy", "meditative"]

# FizzBuzz classes
FIZZBUZZ_CLASSES = ["Plain", "Fizz", "Buzz", "FizzBuzz"]


# ---------------------------------------------------------------------------
# EEG Signal Generation
# ---------------------------------------------------------------------------

@dataclass
class EEGEpoch:
    """A single epoch of multi-channel EEG data.

    Attributes:
        channels: List of channel data arrays, each of length NUM_SAMPLES.
        sample_rate: Sampling rate in Hz.
        duration: Duration in seconds.
        artifact_mask: Boolean per-channel mask; True = artifact-contaminated.
    """
    channels: List[List[float]] = field(default_factory=list)
    sample_rate: int = SAMPLE_RATE
    duration: float = EPOCH_DURATION
    artifact_mask: List[bool] = field(default_factory=list)


class EEGSignalGenerator:
    """Generates synthetic EEG signals with realistic spectral properties.

    The signal is composed of:
    - 1/f pink noise baseline (neural background activity)
    - Sinusoidal oscillations in theta, alpha, beta, gamma bands
    - Optional artifact injection (eye blinks, muscle)

    The input integer seeds the generator to ensure deterministic output
    while producing physiologically plausible spectral envelopes.
    """

    def __init__(
        self,
        num_channels: int = NUM_CHANNELS,
        sample_rate: int = SAMPLE_RATE,
        seed: Optional[int] = None,
    ) -> None:
        self._num_channels = num_channels
        self._sample_rate = sample_rate
        self._rng = random.Random(seed)

    def generate(self, number: int) -> EEGEpoch:
        """Generate an EEG epoch seeded by the given integer.

        The number influences the relative band powers, creating a
        deterministic mapping from integer to spectral profile.
        """
        rng = random.Random(number)
        channels: List[List[float]] = []
        artifact_mask: List[bool] = []

        for ch in range(self._num_channels):
            ch_seed = number * 1000 + ch
            channel_rng = random.Random(ch_seed)
            signal = self._generate_channel(channel_rng, number, ch)
            channels.append(signal)
            # Artifact probability based on channel index and number
            artifact_prob = 0.1 + 0.05 * (ch % 3)
            artifact_mask.append(channel_rng.random() < artifact_prob)

        return EEGEpoch(
            channels=channels,
            sample_rate=self._sample_rate,
            duration=EPOCH_DURATION,
            artifact_mask=artifact_mask,
        )

    def _generate_channel(
        self, rng: random.Random, number: int, channel: int
    ) -> List[float]:
        """Generate a single channel of EEG data."""
        samples = []
        dt = 1.0 / self._sample_rate

        # Band amplitudes derived from number
        theta_amp = 5.0 + 3.0 * math.sin(number * 0.1 + channel)
        alpha_amp = 8.0 + 4.0 * math.cos(number * 0.2 + channel)
        beta_amp = 3.0 + 2.0 * math.sin(number * 0.3 + channel)
        gamma_amp = 1.0 + 0.5 * math.cos(number * 0.4 + channel)

        # Frequency within each band
        theta_freq = THETA_LOW + (THETA_HIGH - THETA_LOW) * ((number % 7) / 7.0)
        alpha_freq = ALPHA_LOW + (ALPHA_HIGH - ALPHA_LOW) * ((number % 11) / 11.0)
        beta_freq = BETA_LOW + (BETA_HIGH - BETA_LOW) * ((number % 13) / 13.0)
        gamma_freq = GAMMA_LOW + (GAMMA_HIGH - GAMMA_LOW) * ((number % 17) / 17.0)

        for i in range(NUM_SAMPLES):
            t = i * dt
            # Oscillatory components
            value = (
                theta_amp * math.sin(2.0 * math.pi * theta_freq * t)
                + alpha_amp * math.sin(2.0 * math.pi * alpha_freq * t)
                + beta_amp * math.sin(2.0 * math.pi * beta_freq * t)
                + gamma_amp * math.sin(2.0 * math.pi * gamma_freq * t)
            )
            # Pink noise approximation (1/f)
            noise = rng.gauss(0.0, 2.0)
            value += noise
            samples.append(value)

        return samples


# ---------------------------------------------------------------------------
# Artifact Rejection
# ---------------------------------------------------------------------------

class ArtifactRejector:
    """Identifies and removes artifact-contaminated channels via ICA.

    In a production BCI system, ICA decomposes multi-channel EEG into
    independent components and removes those correlated with known
    artifact templates (EOG, EMG). Here, the artifact mask from the
    signal generator is used as a proxy for ICA classification.
    """

    def __init__(self, max_rejection_rate: float = DEFAULT_ARTIFACT_MAX_RATE) -> None:
        self._max_rate = max_rejection_rate

    def reject(self, epoch: EEGEpoch) -> Tuple[EEGEpoch, float]:
        """Remove artifact-contaminated channels and return clean epoch.

        Returns:
            Tuple of (cleaned epoch, rejection rate).

        Raises:
            ArtifactRejectionError if rejection rate exceeds maximum.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzbrainwave import ArtifactRejectionError

        clean_channels: List[List[float]] = []
        clean_mask: List[bool] = []
        rejected = sum(1 for m in epoch.artifact_mask if m)
        total = len(epoch.artifact_mask)
        rejection_rate = rejected / max(total, 1)

        if rejection_rate > self._max_rate:
            raise ArtifactRejectionError(rejection_rate, self._max_rate)

        for i, channel in enumerate(epoch.channels):
            if not epoch.artifact_mask[i]:
                clean_channels.append(channel)
                clean_mask.append(False)

        return EEGEpoch(
            channels=clean_channels,
            sample_rate=epoch.sample_rate,
            duration=epoch.duration,
            artifact_mask=clean_mask,
        ), rejection_rate


# ---------------------------------------------------------------------------
# Spectral Analysis
# ---------------------------------------------------------------------------

@dataclass
class BandPowers:
    """Power spectral density in each EEG frequency band.

    Attributes:
        theta: Power in the theta band (4-8 Hz).
        alpha: Power in the alpha band (8-13 Hz).
        beta: Power in the beta band (13-30 Hz).
        gamma: Power in the gamma band (30-50 Hz).
        total: Total spectral power.
    """
    theta: float = 0.0
    alpha: float = 0.0
    beta: float = 0.0
    gamma: float = 0.0
    total: float = 0.0

    @property
    def theta_beta_ratio(self) -> float:
        """Theta/beta ratio — indicator of attentional state."""
        if self.beta < 1e-12:
            return 0.0
        return self.theta / self.beta

    @property
    def alpha_gamma_ratio(self) -> float:
        """Alpha/gamma ratio — indicator of relaxation level."""
        if self.gamma < 1e-12:
            return 0.0
        return self.alpha / self.gamma


class SpectralAnalyzer:
    """Computes power spectral density via a simplified Welch's method.

    The power in each frequency band is estimated by summing the squared
    magnitudes of the DFT coefficients within the band boundaries. A
    Hanning window is applied to reduce spectral leakage.
    """

    def __init__(self, sample_rate: int = SAMPLE_RATE) -> None:
        self._sample_rate = sample_rate

    def analyze(self, epoch: EEGEpoch) -> BandPowers:
        """Compute average band powers across all clean channels.

        Raises:
            SpectralDecompositionError if total power is non-positive.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzbrainwave import SpectralDecompositionError

        if not epoch.channels:
            raise SpectralDecompositionError("No channels available after artifact rejection")

        total_powers = BandPowers()
        n_channels = len(epoch.channels)

        for channel in epoch.channels:
            powers = self._compute_band_powers(channel)
            total_powers.theta += powers.theta
            total_powers.alpha += powers.alpha
            total_powers.beta += powers.beta
            total_powers.gamma += powers.gamma
            total_powers.total += powers.total

        # Average across channels
        total_powers.theta /= n_channels
        total_powers.alpha /= n_channels
        total_powers.beta /= n_channels
        total_powers.gamma /= n_channels
        total_powers.total /= n_channels

        if total_powers.total <= 0:
            raise SpectralDecompositionError(
                f"Total spectral power is {total_powers.total:.6f}, expected positive"
            )

        return total_powers

    def _compute_band_powers(self, signal: List[float]) -> BandPowers:
        """Compute band powers for a single channel using DFT."""
        n = len(signal)
        if n == 0:
            return BandPowers()

        # Apply Hanning window
        windowed = [
            signal[i] * 0.5 * (1.0 - math.cos(2.0 * math.pi * i / (n - 1)))
            for i in range(n)
        ]

        # Compute power spectrum via DFT (real-valued)
        freq_resolution = self._sample_rate / n
        theta_power = 0.0
        alpha_power = 0.0
        beta_power = 0.0
        gamma_power = 0.0
        total_power = 0.0

        # Only compute for positive frequencies up to Nyquist
        max_k = n // 2
        for k in range(1, max_k + 1):
            freq = k * freq_resolution
            # DFT coefficient (simplified — only cosine component for speed)
            real_part = 0.0
            imag_part = 0.0
            for i in range(n):
                angle = 2.0 * math.pi * k * i / n
                real_part += windowed[i] * math.cos(angle)
                imag_part -= windowed[i] * math.sin(angle)

            power = (real_part * real_part + imag_part * imag_part) / (n * n)
            total_power += power

            if THETA_LOW <= freq < THETA_HIGH:
                theta_power += power
            elif ALPHA_LOW <= freq < ALPHA_HIGH:
                alpha_power += power
            elif BETA_LOW <= freq < BETA_HIGH:
                beta_power += power
            elif GAMMA_LOW <= freq < GAMMA_HIGH:
                gamma_power += power

        return BandPowers(
            theta=theta_power,
            alpha=alpha_power,
            beta=beta_power,
            gamma=gamma_power,
            total=total_power,
        )


# ---------------------------------------------------------------------------
# Mental State Classification
# ---------------------------------------------------------------------------

@dataclass
class MentalState:
    """Classified mental state with feature vector.

    Attributes:
        label: One of 'focused', 'relaxed', 'drowsy', 'meditative'.
        confidence: Classification confidence in [0, 1].
        features: Feature vector used for classification.
    """
    label: str = "focused"
    confidence: float = 0.0
    features: Dict[str, float] = field(default_factory=dict)


class MentalStateClassifier:
    """Classifies the operator's mental state from spectral features.

    The classifier uses prototype-based nearest-centroid classification.
    Each mental state has a characteristic spectral signature:

    - **Focused**: Low theta/beta ratio, moderate alpha
    - **Relaxed**: High alpha/gamma ratio, low beta
    - **Drowsy**: High theta, low alpha and beta
    - **Meditative**: High alpha, low theta and gamma

    The operator's spectral features are compared to each prototype via
    Euclidean distance, and the nearest prototype determines the label.
    """

    # Prototype feature vectors: [theta/beta ratio, alpha/gamma ratio]
    PROTOTYPES: Dict[str, Tuple[float, float]] = {
        "focused": (0.8, 1.5),
        "relaxed": (1.2, 4.0),
        "drowsy": (2.5, 1.0),
        "meditative": (1.0, 6.0),
    }

    def classify(self, powers: BandPowers) -> MentalState:
        """Classify the mental state from band power ratios.

        Raises:
            MentalStateClassificationError if no prototype is close enough.
        """
        features = {
            "theta_beta_ratio": powers.theta_beta_ratio,
            "alpha_gamma_ratio": powers.alpha_gamma_ratio,
        }

        best_label = "focused"
        best_dist = float("inf")
        total_inv_dist = 0.0
        distances: Dict[str, float] = {}

        for label, (tb_proto, ag_proto) in self.PROTOTYPES.items():
            dist = math.sqrt(
                (features["theta_beta_ratio"] - tb_proto) ** 2
                + (features["alpha_gamma_ratio"] - ag_proto) ** 2
            )
            distances[label] = dist
            if dist < best_dist:
                best_dist = dist
                best_label = label
            if dist > 1e-12:
                total_inv_dist += 1.0 / dist

        # Confidence from inverse-distance weighting
        if total_inv_dist > 0 and best_dist > 1e-12:
            confidence = (1.0 / best_dist) / total_inv_dist
        else:
            confidence = 1.0

        return MentalState(
            label=best_label,
            confidence=confidence,
            features=features,
        )


# ---------------------------------------------------------------------------
# Neural Decoder (Thought-to-FizzBuzz)
# ---------------------------------------------------------------------------

@dataclass
class DecodingResult:
    """Result of the neural decoding process.

    Attributes:
        label: FizzBuzz classification label.
        confidence: Decoder confidence in [0, 1].
        mental_state: The classified mental state used for decoding.
        band_powers: The spectral features used for decoding.
    """
    label: str = "Plain"
    confidence: float = 0.0
    mental_state: Optional[MentalState] = None
    band_powers: Optional[BandPowers] = None


class NeuralDecoder:
    """Translates mental state and spectral features into FizzBuzz labels.

    The decoder applies a simple linear model that maps the 2D feature
    space (theta/beta ratio, alpha/gamma ratio) onto the four FizzBuzz
    classes. The model is equivalent to a Linear Discriminant Analysis
    (LDA) projection with hand-tuned class centroids.

    The mapping uses the mental state as a primary signal and the spectral
    ratios as tiebreakers:

    - focused -> encodes number directly via modular arithmetic
    - relaxed -> biases toward Fizz (divisibility by 3 resonates with
      alpha-band relaxation)
    - drowsy -> biases toward Buzz (theta dominance maps to 5-fold
      periodicity)
    - meditative -> biases toward FizzBuzz (deep alpha maps to 15-fold
      composite divisibility)
    """

    def __init__(self, confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD) -> None:
        self._confidence_threshold = confidence_threshold

    def decode(
        self,
        number: int,
        mental_state: MentalState,
        band_powers: BandPowers,
    ) -> DecodingResult:
        """Decode the neural state into a FizzBuzz classification.

        Raises:
            NeuralDecodingError if confidence is below threshold.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzbrainwave import NeuralDecodingError

        # Compute class scores from spectral features
        scores = self._compute_scores(number, mental_state, band_powers)
        total = sum(scores.values())
        if total < 1e-12:
            total = 1.0

        # Softmax-like normalization
        best_label = max(scores, key=scores.get)  # type: ignore[arg-type]
        confidence = scores[best_label] / total

        if confidence < self._confidence_threshold:
            raise NeuralDecodingError(confidence, self._confidence_threshold)

        return DecodingResult(
            label=best_label,
            confidence=confidence,
            mental_state=mental_state,
            band_powers=band_powers,
        )

    def _compute_scores(
        self,
        number: int,
        state: MentalState,
        powers: BandPowers,
    ) -> Dict[str, float]:
        """Compute raw class scores from neural features."""
        div3 = 1.0 if number % 3 == 0 else 0.0
        div5 = 1.0 if number % 5 == 0 else 0.0
        div15 = 1.0 if number % 15 == 0 else 0.0

        # Base scores from divisibility (ground truth signal)
        scores = {
            "Plain": 1.0 - div3 - div5 + div15,
            "Fizz": div3 - div15 + 0.1 * powers.theta_beta_ratio,
            "Buzz": div5 - div15 + 0.1 * powers.alpha_gamma_ratio,
            "FizzBuzz": div15 + 0.05 * (powers.theta_beta_ratio + powers.alpha_gamma_ratio),
        }

        # Mental state bias
        state_biases = {
            "focused": {"Plain": 0.3},
            "relaxed": {"Fizz": 0.2},
            "drowsy": {"Buzz": 0.2},
            "meditative": {"FizzBuzz": 0.2},
        }
        for label, bias in state_biases.get(state.label, {}).items():
            scores[label] = scores.get(label, 0.0) + bias * state.confidence

        # Ensure non-negative
        min_score = min(scores.values())
        if min_score < 0:
            for label in scores:
                scores[label] -= min_score

        return scores


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class BrainwaveDashboard:
    """Renders an ASCII dashboard of the BCI processing pipeline."""

    @staticmethod
    def render(result: DecodingResult, width: int = 60) -> str:
        lines = []
        border = "+" + "-" * (width - 2) + "+"
        lines.append(border)
        lines.append(f"| {'FIZZBRAINWAVE: NEURAL DECODING DASHBOARD':^{width - 4}} |")
        lines.append(border)

        if result.band_powers:
            bp = result.band_powers
            lines.append(f"|  Theta power : {bp.theta:12.6f}  |  T/B ratio: {bp.theta_beta_ratio:8.4f}  |")
            lines.append(f"|  Alpha power : {bp.alpha:12.6f}  |  A/G ratio: {bp.alpha_gamma_ratio:8.4f}  |")
            lines.append(f"|  Beta power  : {bp.beta:12.6f}  |                          |")
            lines.append(f"|  Gamma power : {bp.gamma:12.6f}  |                          |")

        if result.mental_state:
            ms = result.mental_state
            lines.append(f"|  Mental state: {ms.label:<12}   confidence: {ms.confidence:.4f}      |")

        lines.append(f"|  Decoded label: {result.label:<12}  confidence: {result.confidence:.4f}      |")
        lines.append(border)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Processing Statistics
# ---------------------------------------------------------------------------

@dataclass
class BrainwaveStatistics:
    """Aggregate statistics for the brainwave processing pipeline."""
    total_processed: int = 0
    total_artifacts_rejected: int = 0
    avg_snr: float = 0.0
    state_counts: Dict[str, int] = field(default_factory=lambda: {s: 0 for s in MENTAL_STATES})
    label_counts: Dict[str, int] = field(default_factory=lambda: {c: 0 for c in FIZZBUZZ_CLASSES})


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class BrainwaveMiddleware(IMiddleware):
    """Pipeline middleware that classifies FizzBuzz via brain-computer interface.

    Generates synthetic EEG, performs artifact rejection and spectral analysis,
    classifies the mental state, and decodes the result into a FizzBuzz label.
    """

    def __init__(
        self,
        signal_generator: Optional[EEGSignalGenerator] = None,
        artifact_rejector: Optional[ArtifactRejector] = None,
        spectral_analyzer: Optional[SpectralAnalyzer] = None,
        mental_state_classifier: Optional[MentalStateClassifier] = None,
        neural_decoder: Optional[NeuralDecoder] = None,
        enable_dashboard: bool = False,
    ) -> None:
        self._signal_gen = signal_generator or EEGSignalGenerator()
        self._artifact_rej = artifact_rejector or ArtifactRejector()
        self._spectral = spectral_analyzer or SpectralAnalyzer()
        self._classifier = mental_state_classifier or MentalStateClassifier()
        self._decoder = neural_decoder or NeuralDecoder()
        self._enable_dashboard = enable_dashboard
        self._stats = BrainwaveStatistics()
        self._last_result: Optional[DecodingResult] = None

    @property
    def statistics(self) -> BrainwaveStatistics:
        return self._stats

    @property
    def last_result(self) -> Optional[DecodingResult]:
        return self._last_result

    def get_name(self) -> str:
        return "BrainwaveMiddleware"

    def get_priority(self) -> int:
        return 268

    def process(
        self, context: ProcessingContext, next_handler: Callable[..., Any]
    ) -> ProcessingContext:
        from enterprise_fizzbuzz.domain.exceptions.fizzbrainwave import BrainwaveMiddlewareError

        context = next_handler(context)

        try:
            # Stage 1: Signal acquisition
            epoch = self._signal_gen.generate(context.number)

            # Stage 2: Artifact rejection
            clean_epoch, rejection_rate = self._artifact_rej.reject(epoch)

            # Stage 3: Spectral analysis
            powers = self._spectral.analyze(clean_epoch)

            # Stage 4: Mental state classification
            mental_state = self._classifier.classify(powers)

            # Stage 5: Neural decoding
            result = self._decoder.decode(context.number, mental_state, powers)

            self._last_result = result
            self._stats.total_processed += 1
            self._stats.state_counts[mental_state.label] = (
                self._stats.state_counts.get(mental_state.label, 0) + 1
            )
            self._stats.label_counts[result.label] = (
                self._stats.label_counts.get(result.label, 0) + 1
            )

            context.metadata["brainwave_label"] = result.label
            context.metadata["brainwave_confidence"] = result.confidence
            context.metadata["brainwave_mental_state"] = mental_state.label
            context.metadata["brainwave_rejection_rate"] = rejection_rate

        except BrainwaveMiddlewareError:
            raise
        except Exception as exc:
            raise BrainwaveMiddlewareError(context.number, str(exc)) from exc

        return context
