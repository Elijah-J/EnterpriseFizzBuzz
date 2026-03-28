"""Enterprise FizzBuzz Platform - FizzBTF BPF Type Format Errors"""
from __future__ import annotations
from ._base import FizzBuzzError


class FizzBTFError(FizzBuzzError):
    """Base exception for all FizzBTF runtime type introspection errors.

    FizzBTF provides BPF Type Format metadata for the Enterprise FizzBuzz
    Platform, enabling runtime type introspection of kernel and program
    data structures.  When type information is incorrect or missing, the
    entire observability stack loses its ability to interpret raw memory
    as structured data.
    """

    def __init__(self, message: str, *, error_code: str = "EFP-BTF00",
                 context: dict | None = None) -> None:
        super().__init__(message, error_code=error_code, context=context)


class BTFTypeNotFoundError(FizzBTFError):
    """Raised when a BTF type lookup fails by ID.

    The requested type ID does not exist in the BTF registry.  This may
    indicate that the type was never registered, or that the registry
    was rebuilt without including the expected type definitions.
    """

    def __init__(self, type_id: str) -> None:
        super().__init__(
            f"BTF type not found: {type_id}",
            error_code="EFP-BTF01",
            context={"type_id": type_id},
        )
        self.type_id = type_id


class BTFTypeNameNotFoundError(FizzBTFError):
    """Raised when a BTF type lookup fails by name.

    No type with the requested name has been registered.  The name
    resolution path checks all registered types for a matching name
    field, and none were found.
    """

    def __init__(self, name: str) -> None:
        super().__init__(
            f"BTF type name not found: '{name}'",
            error_code="EFP-BTF02",
            context={"name": name},
        )
        self.name = name


class BTFDuplicateTypeError(FizzBTFError):
    """Raised when a duplicate type name is registered.

    The BTF registry enforces unique type names within each BTFKind
    namespace.  Registering a second type with an identical name and
    kind violates this constraint.
    """

    def __init__(self, name: str) -> None:
        super().__init__(
            f"Duplicate BTF type name: '{name}'",
            error_code="EFP-BTF03",
            context={"name": name},
        )


class BTFValidationError(FizzBTFError):
    """Raised when a BTF type definition fails validation.

    Type definitions must have a non-empty name, a valid BTFKind, and
    a non-negative size.  Fields, if present, must each contain at
    minimum a 'name' and 'offset' key.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"BTF type validation failed: {reason}",
            error_code="EFP-BTF04",
            context={"reason": reason},
        )
