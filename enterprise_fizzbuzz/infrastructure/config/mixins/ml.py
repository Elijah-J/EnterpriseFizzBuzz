"""Anti-Corruption Layer / ML configuration properties"""

from __future__ import annotations

from typing import Any


class MlConfigMixin:
    """Configuration properties for the ml subsystem."""

    # ----------------------------------------------------------------
    # Anti-Corruption Layer / ML configuration properties
    # ----------------------------------------------------------------

    @property
    def ml_decision_threshold(self) -> float:
        """Confidence threshold for ML classification decisions.

        Predictions with confidence above this value are classified as
        matches. The default of 0.5 is the natural decision boundary
        for sigmoid outputs, which is to say: the most obvious possible
        choice, elevated to a configurable parameter for enterprise
        flexibility.
        """
        self._ensure_loaded()
        return self._raw_config.get("ml", {}).get("decision_threshold", 0.5)

    @property
    def ml_ambiguity_margin(self) -> float:
        """Margin around the decision threshold for ambiguity detection.

        If any rule's ML confidence falls within
        [threshold - margin, threshold + margin], the classification
        is flagged as ambiguous. Because when a neural network is only
        55% sure that 9 is divisible by 3, someone should be notified.
        """
        self._ensure_loaded()
        return self._raw_config.get("ml", {}).get("ambiguity_margin", 0.1)

    @property
    def ml_enable_disagreement_tracking(self) -> bool:
        """Whether to cross-check ML predictions against a deterministic baseline.

        When enabled, every ML classification is independently verified
        by a StandardRuleEngine, and any disagreements are logged and
        emitted as events. This is the architectural equivalent of
        hiring a second accountant to double-check the first one's
        addition.
        """
        self._ensure_loaded()
        return self._raw_config.get("ml", {}).get("enable_disagreement_tracking", False)

