"""FizzPKI configuration properties."""
from __future__ import annotations

class FizzpkiConfigMixin:
    @property
    def fizzpki_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzpki", {}).get("enabled", False)
    @property
    def fizzpki_root_ca_cn(self) -> str:
        self._ensure_loaded()
        return self._raw_config.get("fizzpki", {}).get("root_ca_cn", "Enterprise FizzBuzz Root CA")
    @property
    def fizzpki_intermediate_ca_cn(self) -> str:
        self._ensure_loaded()
        return self._raw_config.get("fizzpki", {}).get("intermediate_ca_cn", "Enterprise FizzBuzz Intermediate CA")
    @property
    def fizzpki_cert_validity_days(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzpki", {}).get("cert_validity_days", 365))
    @property
    def fizzpki_default_key_algorithm(self) -> str:
        self._ensure_loaded()
        return self._raw_config.get("fizzpki", {}).get("default_key_algorithm", "ECDSA_P256")
    @property
    def fizzpki_acme_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzpki", {}).get("acme_enabled", True)
    @property
    def fizzpki_transparency_log_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzpki", {}).get("transparency_log_enabled", True)
    @property
    def fizzpki_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzpki", {}).get("dashboard_width", 72))
