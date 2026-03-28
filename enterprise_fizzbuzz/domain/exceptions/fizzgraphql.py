"""Enterprise FizzBuzz Platform - FizzGraphQL Errors (EFP-GQL00 .. EFP-GQL12)"""
from __future__ import annotations
from ._base import FizzBuzzError

class FizzGraphQLError(FizzBuzzError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"FizzGraphQL error: {reason}", error_code="EFP-GQL00", context={"reason": reason})

class FizzGraphQLSchemaError(FizzGraphQLError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Schema: {reason}"); self.error_code = "EFP-GQL01"

class FizzGraphQLTypeError(FizzGraphQLError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Type: {reason}"); self.error_code = "EFP-GQL02"

class FizzGraphQLParseError(FizzGraphQLError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Parse: {reason}"); self.error_code = "EFP-GQL03"

class FizzGraphQLValidationError(FizzGraphQLError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Validation: {reason}"); self.error_code = "EFP-GQL04"

class FizzGraphQLDepthLimitError(FizzGraphQLError):
    def __init__(self, depth: int, limit: int) -> None:
        super().__init__(f"Depth {depth} exceeds limit {limit}"); self.error_code = "EFP-GQL05"

class FizzGraphQLComplexityLimitError(FizzGraphQLError):
    def __init__(self, complexity: int, limit: int) -> None:
        super().__init__(f"Complexity {complexity} exceeds limit {limit}"); self.error_code = "EFP-GQL06"

class FizzGraphQLResolverError(FizzGraphQLError):
    def __init__(self, field: str, reason: str) -> None:
        super().__init__(f"Resolver {field}: {reason}"); self.error_code = "EFP-GQL07"

class FizzGraphQLExecutionError(FizzGraphQLError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Execution: {reason}"); self.error_code = "EFP-GQL08"

class FizzGraphQLSubscriptionError(FizzGraphQLError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Subscription: {reason}"); self.error_code = "EFP-GQL09"

class FizzGraphQLIntrospectionError(FizzGraphQLError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Introspection: {reason}"); self.error_code = "EFP-GQL10"

class FizzGraphQLDataLoaderError(FizzGraphQLError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"DataLoader: {reason}"); self.error_code = "EFP-GQL11"

class FizzGraphQLConfigError(FizzGraphQLError):
    def __init__(self, param: str, reason: str) -> None:
        super().__init__(f"Config {param}: {reason}"); self.error_code = "EFP-GQL12"
