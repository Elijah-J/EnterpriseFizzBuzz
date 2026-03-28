"""
Enterprise FizzBuzz Platform - FizzSMTP2 Errors (EFP-SMTP2-00 .. EFP-SMTP2-06)

Exception hierarchy for the FizzSMTP2 SMTP relay subsystem.
"""

from __future__ import annotations

from ._base import FizzBuzzError


class FizzSMTP2Error(FizzBuzzError):
    """Base exception for all FizzSMTP2 errors."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzSMTP2 error: {reason}",
            error_code="EFP-SMTP2-00",
            context={"reason": reason},
        )


class FizzSMTP2QueueError(FizzSMTP2Error):
    """Raised on relay queue failures."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"Queue: {reason}")
        self.error_code = "EFP-SMTP2-01"


class FizzSMTP2DeliveryError(FizzSMTP2Error):
    """Raised on delivery failures."""

    def __init__(self, message_id: str, reason: str) -> None:
        super().__init__(f"Delivery {message_id}: {reason}")
        self.error_code = "EFP-SMTP2-02"


class FizzSMTP2BounceError(FizzSMTP2Error):
    """Raised on bounce processing failures."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"Bounce: {reason}")
        self.error_code = "EFP-SMTP2-03"


class FizzSMTP2RelayError(FizzSMTP2Error):
    """Raised on relay connection failures."""

    def __init__(self, host: str, reason: str) -> None:
        super().__init__(f"Relay {host}: {reason}")
        self.error_code = "EFP-SMTP2-04"


class FizzSMTP2AnalyticsError(FizzSMTP2Error):
    """Raised on deliverability analytics failures."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"Analytics: {reason}")
        self.error_code = "EFP-SMTP2-05"


class FizzSMTP2ConfigError(FizzSMTP2Error):
    """Raised on configuration errors."""

    def __init__(self, param: str, reason: str) -> None:
        super().__init__(f"Config {param}: {reason}")
        self.error_code = "EFP-SMTP2-06"
