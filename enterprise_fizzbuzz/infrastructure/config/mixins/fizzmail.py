"""FizzMail configuration properties."""

from __future__ import annotations

from typing import Any


class FizzmailConfigMixin:
    """Configuration properties for the FizzMail SMTP/IMAP email server subsystem."""

    @property
    def fizzmail_enabled(self) -> bool:
        """Whether the FizzMail email server is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzmail", {}).get("enabled", False)

    @property
    def fizzmail_smtp_port(self) -> int:
        """SMTP listen port."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzmail", {}).get("smtp_port", 2525))

    @property
    def fizzmail_imap_port(self) -> int:
        """IMAP listen port."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzmail", {}).get("imap_port", 1143))

    @property
    def fizzmail_domain(self) -> str:
        """Mail domain for the server."""
        self._ensure_loaded()
        return self._raw_config.get("fizzmail", {}).get("domain", "fizzbuzz.local")

    @property
    def fizzmail_hostname(self) -> str:
        """SMTP hostname for EHLO banner."""
        self._ensure_loaded()
        return self._raw_config.get("fizzmail", {}).get("hostname", "mail.fizzbuzz.local")

    @property
    def fizzmail_enable_tls(self) -> bool:
        """Whether STARTTLS is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzmail", {}).get("enable_tls", True)

    @property
    def fizzmail_enable_auth(self) -> bool:
        """Whether SMTP AUTH is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzmail", {}).get("enable_auth", True)

    @property
    def fizzmail_enable_dkim_sign(self) -> bool:
        """Whether outbound DKIM signing is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzmail", {}).get("enable_dkim_sign", True)

    @property
    def fizzmail_enable_dkim_verify(self) -> bool:
        """Whether inbound DKIM verification is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzmail", {}).get("enable_dkim_verify", True)

    @property
    def fizzmail_enable_spf(self) -> bool:
        """Whether SPF validation is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzmail", {}).get("enable_spf", True)

    @property
    def fizzmail_enable_dmarc(self) -> bool:
        """Whether DMARC evaluation is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzmail", {}).get("enable_dmarc", True)

    @property
    def fizzmail_enable_greylist(self) -> bool:
        """Whether greylisting is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzmail", {}).get("enable_greylist", False)

    @property
    def fizzmail_enable_rbl(self) -> bool:
        """Whether RBL/DNSBL checking is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzmail", {}).get("enable_rbl", False)

    @property
    def fizzmail_max_message_size(self) -> int:
        """Maximum message size in bytes."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzmail", {}).get("max_message_size", 26214400))

    @property
    def fizzmail_max_recipients(self) -> int:
        """Maximum recipients per message."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzmail", {}).get("max_recipients", 100))

    @property
    def fizzmail_retry_max_attempts(self) -> int:
        """Maximum delivery retry attempts."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzmail", {}).get("retry_max_attempts", 5))

    @property
    def fizzmail_quota_default(self) -> int:
        """Default per-mailbox quota in bytes."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzmail", {}).get("quota_default", 104857600))

    @property
    def fizzmail_smart_host(self) -> str:
        """Smart host for outbound relay."""
        self._ensure_loaded()
        return self._raw_config.get("fizzmail", {}).get("smart_host", "")

    @property
    def fizzmail_dkim_selector(self) -> str:
        """DKIM selector name."""
        self._ensure_loaded()
        return self._raw_config.get("fizzmail", {}).get("dkim_selector", "fizzbuzz")

    @property
    def fizzmail_dashboard_width(self) -> int:
        """Dashboard rendering width."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzmail", {}).get("dashboard_width", 72))
