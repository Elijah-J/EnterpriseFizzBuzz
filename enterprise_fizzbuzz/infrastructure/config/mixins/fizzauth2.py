"""FizzAuth2 configuration properties."""
from __future__ import annotations

class Fizzauth2ConfigMixin:
    @property
    def fizzauth2_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzauth2", {}).get("enabled", False)
    @property
    def fizzauth2_issuer(self) -> str:
        self._ensure_loaded()
        return self._raw_config.get("fizzauth2", {}).get("issuer", "https://auth.fizzbuzz.local")
    @property
    def fizzauth2_token_ttl(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzauth2", {}).get("token_ttl", 3600))
    @property
    def fizzauth2_refresh_ttl(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzauth2", {}).get("refresh_ttl", 86400))
    @property
    def fizzauth2_code_ttl(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzauth2", {}).get("code_ttl", 300))
    @property
    def fizzauth2_require_pkce(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzauth2", {}).get("require_pkce", True)
    @property
    def fizzauth2_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzauth2", {}).get("dashboard_width", 72))
