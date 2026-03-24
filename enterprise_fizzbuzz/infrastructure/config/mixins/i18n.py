"""I18N configuration properties."""

from __future__ import annotations

from typing import Any


class I18nConfigMixin:
    """Configuration properties for the i18n subsystem."""

    @property
    def i18n_enabled(self) -> bool:
        """Whether the internationalization subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("i18n", {}).get("enabled", True)

    @property
    def i18n_locale(self) -> str:
        """The active locale code (e.g. 'en', 'fr', 'tlh')."""
        self._ensure_loaded()
        return self._raw_config.get("i18n", {}).get("locale", "en")

    @property
    def i18n_locale_directory(self) -> str:
        """Path to the directory containing .fizztranslation files."""
        self._ensure_loaded()
        return self._raw_config.get("i18n", {}).get("locale_directory", "./locales")

    @property
    def i18n_strict_mode(self) -> bool:
        """Whether missing translation keys should raise errors."""
        self._ensure_loaded()
        return self._raw_config.get("i18n", {}).get("strict_mode", False)

    @property
    def i18n_fallback_chain(self) -> list[str]:
        """Global fallback chain for locale resolution."""
        self._ensure_loaded()
        return self._raw_config.get("i18n", {}).get("fallback_chain", ["en"])

    @property
    def i18n_log_missing_keys(self) -> bool:
        """Whether to log warnings for missing translation keys."""
        self._ensure_loaded()
        return self._raw_config.get("i18n", {}).get("log_missing_keys", True)

