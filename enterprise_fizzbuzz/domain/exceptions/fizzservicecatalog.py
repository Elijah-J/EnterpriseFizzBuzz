"""Enterprise FizzBuzz Platform - FizzServiceCatalog Errors (EFP-SVC00..05)"""
from __future__ import annotations
from ._base import FizzBuzzError

class FizzServiceCatalogError(FizzBuzzError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"FizzServiceCatalog: {reason}", error_code="EFP-SVC00", context={"reason": reason})
class FizzServiceCatalogNotFoundError(FizzServiceCatalogError):
    def __init__(self, service_id: str) -> None:
        super().__init__(f"Service not found: {service_id}"); self.error_code = "EFP-SVC01"
class FizzServiceCatalogHealthError(FizzServiceCatalogError):
    def __init__(self, service_id: str, reason: str) -> None:
        super().__init__(f"Health {service_id}: {reason}"); self.error_code = "EFP-SVC02"
class FizzServiceCatalogDiscoveryError(FizzServiceCatalogError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Discovery: {reason}"); self.error_code = "EFP-SVC03"
class FizzServiceCatalogDependencyError(FizzServiceCatalogError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Dependency: {reason}"); self.error_code = "EFP-SVC04"
class FizzServiceCatalogConfigError(FizzServiceCatalogError):
    def __init__(self, p: str, r: str) -> None:
        super().__init__(f"Config {p}: {r}"); self.error_code = "EFP-SVC05"
