"""FizzLinguistics Natural Language Processing Properties"""

from __future__ import annotations

from typing import Any


class FizzLinguisticsConfigMixin:
    """Configuration properties for the FizzLinguistics subsystem."""

    # ----------------------------------------------------------------
    # FizzLinguistics NLP Properties
    # ----------------------------------------------------------------

    @property
    def fizzlinguistics_enabled(self) -> bool:
        """Whether the FizzLinguistics NLP engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzlinguistics", {}).get("enabled", False)

    @property
    def fizzlinguistics_enable_sentiment(self) -> bool:
        """Whether sentiment analysis is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzlinguistics", {}).get("enable_sentiment", True)

    @property
    def fizzlinguistics_enable_perplexity(self) -> bool:
        """Whether perplexity computation is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzlinguistics", {}).get("enable_perplexity", True)

    @property
    def fizzlinguistics_max_sequence_length(self) -> int:
        """Maximum input sequence length for tokenization."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzlinguistics", {}).get("max_sequence_length", 100000))
