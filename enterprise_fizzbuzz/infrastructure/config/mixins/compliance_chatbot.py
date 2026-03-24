"""Compliance Chatbot configuration properties."""

from __future__ import annotations

from typing import Any


class ComplianceChatbotConfigMixin:
    """Configuration properties for the compliance chatbot subsystem."""

    @property
    def compliance_chatbot_max_history(self) -> int:
        """Maximum conversation turns retained in chatbot session memory."""
        self._ensure_loaded()
        return self._raw_config.get("compliance", {}).get("chatbot", {}).get("max_history", 20)

    @property
    def compliance_chatbot_formality_level(self) -> str:
        """Response formality level for the compliance chatbot."""
        self._ensure_loaded()
        return self._raw_config.get("compliance", {}).get("chatbot", {}).get("formality_level", "maximum")

    @property
    def compliance_chatbot_include_citations(self) -> bool:
        """Whether to include regulatory article citations in chatbot responses."""
        self._ensure_loaded()
        return self._raw_config.get("compliance", {}).get("chatbot", {}).get("include_article_citations", True)

    @property
    def compliance_chatbot_bob_commentary(self) -> bool:
        """Whether to include Bob McFizzington's editorial comments."""
        self._ensure_loaded()
        return self._raw_config.get("compliance", {}).get("chatbot", {}).get("bob_commentary_enabled", True)

    @property
    def compliance_chatbot_dashboard_width(self) -> int:
        """ASCII dashboard width for the compliance chatbot dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("compliance", {}).get("chatbot", {}).get("dashboard_width", 60)

