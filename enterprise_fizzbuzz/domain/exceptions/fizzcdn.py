"""Enterprise FizzBuzz Platform - FizzCDN CDN Errors (EFP-CDN00 .. EFP-CDN16)"""
from __future__ import annotations
from ._base import FizzBuzzError

class FizzCDNError(FizzBuzzError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"FizzCDN error: {reason}", error_code="EFP-CDN00", context={"reason": reason})

class FizzCDNCacheError(FizzCDNError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Cache: {reason}"); self.error_code = "EFP-CDN01"

class FizzCDNCacheMissError(FizzCDNError):
    def __init__(self, key: str) -> None:
        super().__init__(f"Cache miss: {key}"); self.error_code = "EFP-CDN02"

class FizzCDNOriginError(FizzCDNError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Origin: {reason}"); self.error_code = "EFP-CDN03"

class FizzCDNPoPError(FizzCDNError):
    def __init__(self, pop: str, reason: str) -> None:
        super().__init__(f"PoP {pop}: {reason}"); self.error_code = "EFP-CDN04"

class FizzCDNPoPNotFoundError(FizzCDNError):
    def __init__(self, pop: str) -> None:
        super().__init__(f"PoP not found: {pop}"); self.error_code = "EFP-CDN05"

class FizzCDNPurgeError(FizzCDNError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Purge: {reason}"); self.error_code = "EFP-CDN06"

class FizzCDNRoutingError(FizzCDNError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Routing: {reason}"); self.error_code = "EFP-CDN07"

class FizzCDNTLSError(FizzCDNError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"TLS: {reason}"); self.error_code = "EFP-CDN08"

class FizzCDNPreloadError(FizzCDNError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Preload: {reason}"); self.error_code = "EFP-CDN09"

class FizzCDNEdgeComputeError(FizzCDNError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Edge compute: {reason}"); self.error_code = "EFP-CDN10"

class FizzCDNAnalyticsError(FizzCDNError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Analytics: {reason}"); self.error_code = "EFP-CDN11"

class FizzCDNRangeError(FizzCDNError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Range request: {reason}"); self.error_code = "EFP-CDN12"

class FizzCDNStreamingError(FizzCDNError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Streaming: {reason}"); self.error_code = "EFP-CDN13"

class FizzCDNBandwidthError(FizzCDNError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Bandwidth: {reason}"); self.error_code = "EFP-CDN14"

class FizzCDNStaleError(FizzCDNError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Stale: {reason}"); self.error_code = "EFP-CDN15"

class FizzCDNConfigError(FizzCDNError):
    def __init__(self, param: str, reason: str) -> None:
        super().__init__(f"Config {param}: {reason}"); self.error_code = "EFP-CDN16"
