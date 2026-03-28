"""
Enterprise FizzBuzz Platform - FizzBrainwave Brain-Computer Interface Exceptions

The FizzBrainwave subsystem processes electroencephalographic (EEG) signals to
decode the operator's mental state and translate neural activity into FizzBuzz
classifications. Signal acquisition, artifact rejection, spectral decomposition,
and neural decoding each have distinct failure modes that require specific
recovery strategies at the middleware level.

Error codes: EFP-BW00 through EFP-BW06.
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzBrainwaveError(FizzBuzzError):
    """Base exception for all brain-computer interface subsystem errors."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-BW00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class EEGSignalError(FizzBrainwaveError):
    """Raised when the raw EEG signal cannot be acquired or is corrupted.

    EEG signals are sampled at 256 Hz across multiple electrode channels.
    If the signal-to-noise ratio falls below the minimum threshold, the
    downstream spectral analysis will produce meaningless frequency-band
    power estimates, invalidating any subsequent mental state classification.
    """

    def __init__(self, channel: str, snr: float, threshold: float) -> None:
        super().__init__(
            f"EEG signal on channel '{channel}' has SNR {snr:.2f} dB, "
            f"below the minimum threshold of {threshold:.2f} dB. "
            f"Check electrode impedance and environmental shielding.",
            error_code="EFP-BW01",
            context={"channel": channel, "snr": snr, "threshold": threshold},
        )


class ArtifactRejectionError(FizzBrainwaveError):
    """Raised when artifact rejection removes too many epochs from the recording.

    Eye blinks, muscle contractions, and electrode drift produce artifacts that
    contaminate the EEG signal. The independent component analysis (ICA) pipeline
    identifies and removes these components. If the rejection rate exceeds the
    configured maximum, insufficient clean data remains for reliable classification.
    """

    def __init__(self, rejection_rate: float, max_rate: float) -> None:
        super().__init__(
            f"Artifact rejection rate {rejection_rate:.1%} exceeds maximum "
            f"allowed rate of {max_rate:.1%}. The recording is too contaminated "
            f"for reliable neural decoding.",
            error_code="EFP-BW02",
            context={"rejection_rate": rejection_rate, "max_rate": max_rate},
        )


class SpectralDecompositionError(FizzBrainwaveError):
    """Raised when the FFT-based spectral decomposition produces invalid results.

    The power spectral density is computed via Welch's method with Hanning
    windowing. If the total spectral power is zero or negative (due to numerical
    underflow or a flat-line signal), the frequency-band ratios used for mental
    state classification become undefined.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Spectral decomposition failed: {reason}.",
            error_code="EFP-BW03",
            context={"reason": reason},
        )


class MentalStateClassificationError(FizzBrainwaveError):
    """Raised when the mental state classifier cannot assign a state label.

    The classifier maps frequency-band power ratios (theta/beta, alpha/gamma)
    to discrete mental states: focused, relaxed, drowsy, or meditative. If the
    feature vector falls outside all decision boundaries, no classification
    can be assigned.
    """

    def __init__(self, features: dict[str, float]) -> None:
        super().__init__(
            f"Mental state classification failed: feature vector {features} "
            f"does not match any known state prototype.",
            error_code="EFP-BW04",
            context={"features": features},
        )


class NeuralDecodingError(FizzBrainwaveError):
    """Raised when the thought-to-FizzBuzz decoder fails to produce a valid label.

    The neural decoder applies a linear discriminant analysis (LDA) model to
    the classified mental state and associated spectral features to produce
    a FizzBuzz classification. If the posterior probability of the most likely
    class falls below the confidence threshold, the decoder abstains.
    """

    def __init__(self, confidence: float, threshold: float) -> None:
        super().__init__(
            f"Neural decoding confidence {confidence:.3f} is below the "
            f"threshold of {threshold:.3f}. The decoder cannot reliably "
            f"determine the FizzBuzz classification from the current neural state.",
            error_code="EFP-BW05",
            context={"confidence": confidence, "threshold": threshold},
        )


class BrainwaveMiddlewareError(FizzBrainwaveError):
    """Raised when the brain-computer interface middleware fails during pipeline processing."""

    def __init__(self, number: int, reason: str) -> None:
        super().__init__(
            f"Brainwave middleware failed for number {number}: {reason}.",
            error_code="EFP-BW06",
            context={"number": number, "reason": reason},
        )
