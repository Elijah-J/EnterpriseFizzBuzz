"""FizzWindow configuration properties."""

from __future__ import annotations

from typing import Any


class FizzwindowConfigMixin:
    """Configuration properties for the FizzWindow windowing system."""

    @property
    def fizzwindow_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzwindow", {}).get("enabled", False)

    @property
    def fizzwindow_mode(self) -> str:
        self._ensure_loaded()
        return self._raw_config.get("fizzwindow", {}).get("mode", "floating")

    @property
    def fizzwindow_theme(self) -> str:
        self._ensure_loaded()
        return self._raw_config.get("fizzwindow", {}).get("theme", "enterprise-dark")

    @property
    def fizzwindow_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzwindow", {}).get("width", 1920))

    @property
    def fizzwindow_height(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzwindow", {}).get("height", 1080))

    @property
    def fizzwindow_monitors(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzwindow", {}).get("monitors", 1))

    @property
    def fizzwindow_fps_limit(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzwindow", {}).get("fps_limit", 60))

    @property
    def fizzwindow_dpi(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzwindow", {}).get("dpi", 96))

    @property
    def fizzwindow_font(self) -> str:
        self._ensure_loaded()
        return self._raw_config.get("fizzwindow", {}).get("font", "FizzMono")

    @property
    def fizzwindow_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzwindow", {}).get("dashboard_width", 72))
