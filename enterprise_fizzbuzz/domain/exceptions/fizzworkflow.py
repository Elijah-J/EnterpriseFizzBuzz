"""Enterprise FizzBuzz Platform - FizzWorkflow Errors (EFP-WF00 .. EFP-WF06)"""
from __future__ import annotations
from ._base import FizzBuzzError

class FizzWorkflowError(FizzBuzzError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"FizzWorkflow error: {reason}", error_code="EFP-WF00", context={"reason": reason})
class FizzWorkflowNotFoundError(FizzWorkflowError):
    def __init__(self, name: str) -> None:
        super().__init__(f"Workflow not found: {name}"); self.error_code = "EFP-WF01"
class FizzWorkflowStepError(FizzWorkflowError):
    def __init__(self, step: str, reason: str) -> None:
        super().__init__(f"Step {step}: {reason}"); self.error_code = "EFP-WF02"
class FizzWorkflowCompensationError(FizzWorkflowError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Compensation: {reason}"); self.error_code = "EFP-WF03"
class FizzWorkflowTimeoutError(FizzWorkflowError):
    def __init__(self, instance_id: str) -> None:
        super().__init__(f"Timeout: {instance_id}"); self.error_code = "EFP-WF04"
class FizzWorkflowInstanceError(FizzWorkflowError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Instance: {reason}"); self.error_code = "EFP-WF05"
class FizzWorkflowConfigError(FizzWorkflowError):
    def __init__(self, param: str, reason: str) -> None:
        super().__init__(f"Config {param}: {reason}"); self.error_code = "EFP-WF06"
