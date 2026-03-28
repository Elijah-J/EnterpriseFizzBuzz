"""
Enterprise FizzBuzz Platform - FizzK8sOperator Errors (EFP-K8S2-00 .. EFP-K8S2-06)
"""

from __future__ import annotations

from ._base import FizzBuzzError


class FizzK8sOperatorError(FizzBuzzError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"FizzK8sOperator: {reason}", error_code="EFP-K8S2-00", context={"reason": reason})

class FizzK8sOperatorCRDError(FizzK8sOperatorError):
    def __init__(self, kind: str, reason: str) -> None:
        super().__init__(f"CRD {kind}: {reason}"); self.error_code = "EFP-K8S2-01"

class FizzK8sOperatorResourceError(FizzK8sOperatorError):
    def __init__(self, kind: str, name: str, reason: str) -> None:
        super().__init__(f"Resource {kind}/{name}: {reason}"); self.error_code = "EFP-K8S2-02"

class FizzK8sOperatorReconcileError(FizzK8sOperatorError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Reconcile: {reason}"); self.error_code = "EFP-K8S2-03"

class FizzK8sOperatorWatchError(FizzK8sOperatorError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Watch: {reason}"); self.error_code = "EFP-K8S2-04"

class FizzK8sOperatorResourceNotFoundError(FizzK8sOperatorError):
    def __init__(self, kind: str, name: str) -> None:
        super().__init__(f"Not found: {kind}/{name}"); self.error_code = "EFP-K8S2-05"

class FizzK8sOperatorConfigError(FizzK8sOperatorError):
    def __init__(self, param: str, reason: str) -> None:
        super().__init__(f"Config {param}: {reason}"); self.error_code = "EFP-K8S2-06"
