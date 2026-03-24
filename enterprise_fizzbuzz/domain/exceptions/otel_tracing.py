"""
Enterprise FizzBuzz Platform - FizzOTel — OpenTelemetry-Compatible Distributed Tracing Errors
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class OTelError(FizzBuzzError):
    """Base exception for all FizzOTel distributed tracing errors.

    The OpenTelemetry specification defines a comprehensive error
    taxonomy for telemetry pipelines. This exception hierarchy mirrors
    that taxonomy, because when your FizzBuzz tracing subsystem fails,
    you need enterprise-grade error categorization to understand whether
    the failure was in sampling, span lifecycle, or export — even though
    the fix is always "restart the CLI."
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code="EFP-OT00",
            context=kwargs,
        )


class OTelSpanError(OTelError):
    """Raised when a span lifecycle operation fails.

    This includes invalid trace IDs, malformed W3C traceparent headers,
    attempts to end an already-ended span, or any other violation of
    the span state machine. In production OpenTelemetry, these errors
    are silently swallowed. In Enterprise FizzBuzz, they are promoted
    to full exceptions because silent failures are anathema to our
    zero-tolerance-for-ambiguity policy.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.error_code = "EFP-OT01"


class OTelExportError(OTelError):
    """Raised when span export fails.

    Export failures can occur when the OTLP JSON serialization encounters
    an unserializable attribute, when the Zipkin format conversion fails,
    or when the ConsoleExporter runs out of terminal width. Each of these
    scenarios is equally catastrophic for FizzBuzz observability.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.error_code = "EFP-OT02"


class OTelSamplingError(OTelError):
    """Raised when the probabilistic sampler encounters an invalid state.

    A sampling rate outside [0.0, 1.0] would violate the fundamental
    axioms of probability theory, and the Enterprise FizzBuzz Platform
    refuses to operate in a universe where P(sample) > 1.0 or P(sample) < 0.0.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.error_code = "EFP-OT03"

