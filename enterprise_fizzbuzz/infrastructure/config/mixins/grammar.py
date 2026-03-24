"""Grammar configuration properties."""

from __future__ import annotations

from typing import Any


class GrammarConfigMixin:
    """Configuration properties for the grammar subsystem."""

    # ----------------------------------------------------------------
    # FizzGrammar -- Formal Grammar & Parser Generator
    # ----------------------------------------------------------------

    @property
    def grammar_enabled(self) -> bool:
        """Whether the FizzGrammar subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("grammar", {}).get("enabled", False)

    @property
    def grammar_dashboard_width(self) -> int:
        """Dashboard width for the FizzGrammar dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("grammar", {}).get("dashboard", {}).get("width", 60)

