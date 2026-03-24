"""
Enterprise FizzBuzz Platform - ── FizzImage: Official Container Image Catalog ──────────────────────
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class FizzImageError(FizzBuzzError):
    """Base exception for FizzImage container image catalog errors."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-IMG00"
        self.context = {"reason": reason}


class CatalogInitializationError(FizzImageError):
    """Raised when the image catalog fails to initialize."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-IMG01"
        self.context = {"reason": reason}


class ImageNotFoundInCatalogError(FizzImageError):
    """Raised when a referenced image does not exist in the catalog."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-IMG02"
        self.context = {"reason": reason}


class ImageAlreadyExistsInCatalogError(FizzImageError):
    """Raised when attempting to register a duplicate image name."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-IMG03"
        self.context = {"reason": reason}


class ImageBuildError(FizzImageError):
    """Raised when image construction fails during FizzFile execution."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-IMG04"
        self.context = {"reason": reason}


class ImageBuildDependencyError(FizzImageError):
    """Raised when an image's base or dependency image is missing."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-IMG05"
        self.context = {"reason": reason}


class FizzFileGenerationError(FizzImageError):
    """Raised when FizzFile DSL generation fails for a module."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-IMG06"
        self.context = {"reason": reason}


class ImageDependencyRuleViolationError(FizzImageError):
    """Raised when an image violates the Clean Architecture dependency rule."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-IMG07"
        self.context = {"reason": reason}


class ImageLayerCreationError(FizzImageError):
    """Raised when a filesystem layer cannot be constructed."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-IMG08"
        self.context = {"reason": reason}


class ImageDigestMismatchError(FizzImageError):
    """Raised when a layer's computed digest does not match its expected digest."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-IMG09"
        self.context = {"reason": reason}


class ImageVulnerabilityScanError(FizzImageError):
    """Raised when the vulnerability scanner encounters an operational failure."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-IMG10"
        self.context = {"reason": reason}


class ImageBlockedByScanError(FizzImageError):
    """Raised when an image is blocked from the catalog due to scan policy violations."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-IMG11"
        self.context = {"reason": reason}


class ImageVersionConflictError(FizzImageError):
    """Raised when a version tag assignment conflicts with an existing version."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-IMG12"
        self.context = {"reason": reason}


class MultiArchBuildError(FizzImageError):
    """Raised when multi-architecture manifest index generation fails."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-IMG13"
        self.context = {"reason": reason}


class PlatformResolutionError(FizzImageError):
    """Raised when a platform cannot be resolved from a manifest index."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-IMG14"
        self.context = {"reason": reason}


class InitContainerImageBuildError(FizzImageError):
    """Raised when an init container image build fails."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-IMG15"
        self.context = {"reason": reason}


class SidecarImageBuildError(FizzImageError):
    """Raised when a sidecar container image build fails."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-IMG16"
        self.context = {"reason": reason}


class CatalogCapacityError(FizzImageError):
    """Raised when the catalog exceeds its maximum image capacity."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-IMG17"
        self.context = {"reason": reason}


class ImageCircularDependencyError(FizzImageError):
    """Raised when circular dependencies are detected in subsystem imports."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-IMG18"
        self.context = {"reason": reason}


class ImageMetadataValidationError(FizzImageError):
    """Raised when image metadata fails OCI annotation validation."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-IMG19"
        self.context = {"reason": reason}


class FizzImageMiddlewareError(FizzImageError):
    """Raised when the FizzImage middleware fails to process an evaluation."""

    def __init__(self, evaluation_number: int, reason: str) -> None:
        super().__init__(
            f"FizzImage middleware error at evaluation {evaluation_number}: {reason}"
        )
        self.error_code = "EFP-IMG20"
        self.context = {"evaluation_number": evaluation_number, "reason": reason}
        self.evaluation_number = evaluation_number

