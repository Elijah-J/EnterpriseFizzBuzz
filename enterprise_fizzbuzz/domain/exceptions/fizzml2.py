"""Enterprise FizzBuzz Platform - FizzML2 Errors (EFP-ML2-00 .. EFP-ML2-10)"""
from __future__ import annotations
from ._base import FizzBuzzError

class FizzML2Error(FizzBuzzError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"FizzML2 error: {reason}", error_code="EFP-ML2-00", context={"reason": reason})
class FizzML2ModelNotFoundError(FizzML2Error):
    def __init__(self, name: str) -> None:
        super().__init__(f"Model not found: {name}"); self.error_code = "EFP-ML2-01"
class FizzML2TrainingError(FizzML2Error):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Training: {reason}"); self.error_code = "EFP-ML2-02"
class FizzML2ServingError(FizzML2Error):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Serving: {reason}"); self.error_code = "EFP-ML2-03"
class FizzML2EndpointError(FizzML2Error):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Endpoint: {reason}"); self.error_code = "EFP-ML2-04"
class FizzML2PredictionError(FizzML2Error):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Prediction: {reason}"); self.error_code = "EFP-ML2-05"
class FizzML2FeatureError(FizzML2Error):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Feature: {reason}"); self.error_code = "EFP-ML2-06"
class FizzML2DatasetError(FizzML2Error):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Dataset: {reason}"); self.error_code = "EFP-ML2-07"
class FizzML2EvaluationError(FizzML2Error):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Evaluation: {reason}"); self.error_code = "EFP-ML2-08"
class FizzML2RegistryError(FizzML2Error):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Registry: {reason}"); self.error_code = "EFP-ML2-09"
class FizzML2ConfigError(FizzML2Error):
    def __init__(self, param: str, reason: str) -> None:
        super().__init__(f"Config {param}: {reason}"); self.error_code = "EFP-ML2-10"
