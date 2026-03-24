"""
Enterprise FizzBuzz Platform - FizzImage: Official Container Image Catalog

The Official Container Image Catalog manages every container image that
the Enterprise FizzBuzz Platform publishes.  The catalog maintains five
image classes: base images (the minimal Python + domain-layer foundation),
evaluation images (application-layer profiles for each evaluation mode),
subsystem images (one per infrastructure module, with AST-derived
dependency analysis), init container images (pre-flight configuration,
schema migration, and secret injection), and sidecar images (logging,
metrics, tracing, and service mesh proxy).

Each image is built from a FizzFile definition (the platform's Dockerfile
equivalent), scanned for vulnerabilities against a simulated CVE database,
assigned a semantic version, and published as a multi-architecture OCI
image index supporting linux/amd64, linux/arm64, and the platform's
native bytecode VM architecture.

The catalog enforces the Clean Architecture dependency rule at the image
level: the base image contains only the domain layer, evaluation images
add the application layer, and subsystem images add individual
infrastructure modules.  AST-based import analysis ensures each
subsystem image includes only its transitive dependency closure.

OCI Image Specification: https://github.com/opencontainers/image-spec
OCI Distribution Specification: https://github.com/opencontainers/distribution-spec
"""

from __future__ import annotations

import ast
import copy
import hashlib
import logging
import math
import random
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzResult,
    ProcessingContext,
)

logger = logging.getLogger("enterprise_fizzbuzz.fizzimage")


# ============================================================
# Exceptions (self-contained, inheriting from FizzBuzzError)
# ============================================================


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


class ImageNotFoundError(FizzImageError):
    """Raised when a referenced image does not exist in the catalog."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-IMG02"
        self.context = {"reason": reason}


class ImageAlreadyExistsError(FizzImageError):
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


class DependencyRuleViolationError(FizzImageError):
    """Raised when an image violates the Clean Architecture dependency rule."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-IMG07"
        self.context = {"reason": reason}


class LayerCreationError(FizzImageError):
    """Raised when a filesystem layer cannot be constructed."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-IMG08"
        self.context = {"reason": reason}


class DigestMismatchError(FizzImageError):
    """Raised when a layer's computed digest does not match its expected digest."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-IMG09"
        self.context = {"reason": reason}


class VulnerabilityScanError(FizzImageError):
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


class VersionConflictError(FizzImageError):
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


class InitContainerBuildError(FizzImageError):
    """Raised when an init container image build fails."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-IMG15"
        self.context = {"reason": reason}


class SidecarBuildError(FizzImageError):
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


class CircularDependencyError(FizzImageError):
    """Raised when circular dependencies are detected in subsystem imports."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-IMG18"
        self.context = {"reason": reason}


class MetadataValidationError(FizzImageError):
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


# ============================================================
# Event type constants (module-level strings)
# ============================================================

FIZZIMAGE_CATALOG_LOADED = "fizzimage.catalog.loaded"
FIZZIMAGE_CATALOG_STATS = "fizzimage.catalog.stats"
FIZZIMAGE_IMAGE_REGISTERED = "fizzimage.image.registered"
FIZZIMAGE_BASE_BUILT = "fizzimage.base.built"
FIZZIMAGE_EVAL_BUILT = "fizzimage.eval.built"
FIZZIMAGE_SUBSYSTEM_GENERATED = "fizzimage.subsystem.generated"
FIZZIMAGE_INIT_BUILT = "fizzimage.init.built"
FIZZIMAGE_SIDECAR_BUILT = "fizzimage.sidecar.built"
FIZZIMAGE_MULTI_ARCH_INDEXED = "fizzimage.multiarch.indexed"
FIZZIMAGE_SCAN_STARTED = "fizzimage.scan.started"
FIZZIMAGE_SCAN_COMPLETED = "fizzimage.scan.completed"
FIZZIMAGE_SCAN_BLOCKED = "fizzimage.scan.blocked"
FIZZIMAGE_VERSION_BUMPED = "fizzimage.version.bumped"
FIZZIMAGE_IMAGE_REMOVED = "fizzimage.image.removed"
FIZZIMAGE_BUILD_ALL_STARTED = "fizzimage.build_all.started"
FIZZIMAGE_BUILD_ALL_COMPLETED = "fizzimage.build_all.completed"


# ============================================================
# Constants
# ============================================================

FIZZIMAGE_VERSION = "1.0.0"
"""FizzImage catalog system version."""

FIZZIMAGE_API_VERSION = "v1"
"""API version for the image catalog."""

DEFAULT_REGISTRY_URL = "registry.fizzbuzz.internal:5000"
"""Default registry URL for image push/pull operations."""

DEFAULT_BASE_IMAGE = "fizzbuzz-base"
"""Default base image name used by all catalog images."""

DEFAULT_PYTHON_VERSION = "3.12"
"""Python version installed in the base image."""

DEFAULT_MODULE_BASE_PATH = "enterprise_fizzbuzz.infrastructure"
"""Base Python package path for infrastructure modules."""

DEFAULT_SCAN_SEVERITY_THRESHOLD = "critical"
"""Default maximum severity that blocks image admission."""

DEFAULT_VULN_DB_SIZE = 512
"""Default number of entries in the simulated vulnerability database."""

DEFAULT_INITIAL_VERSION = "1.0.0"
"""Default initial semantic version for new images."""

DEFAULT_MAX_CATALOG_SIZE = 1024
"""Maximum number of images in the catalog."""

DEFAULT_DASHBOARD_WIDTH = 72
"""Default width for ASCII dashboard rendering."""

MIDDLEWARE_PRIORITY = 113
"""Middleware pipeline priority for FizzImage."""

SUPPORTED_PLATFORMS = ["linux/amd64", "linux/arm64", "fizzbuzz/vm"]
"""Supported target architectures for multi-arch builds."""

IMAGE_AUTHOR = "Bob McFizzington <bob@fizzbuzz.enterprise>"
"""Default image author for OCI annotations."""

IMAGE_GROUPS = {
    "fizzbuzz-data": ["sqlite_backend", "filesystem_backend", "memory_backend"],
    "fizzbuzz-network": ["fizztcp", "fizzdns", "fizzproxy", "service_mesh"],
    "fizzbuzz-security": ["auth", "capability_security", "secrets_vault", "compliance"],
    "fizzbuzz-observability": ["fizzotel", "fizzflame", "sla_monitor", "metrics", "fizzcorr"],
}
"""Subsystem groupings for composite images."""


# ============================================================
# Enums
# ============================================================


class ImageType(Enum):
    """Classification of images in the official catalog.

    Each image in the catalog is assigned a type that determines its
    build pipeline, dependency constraints, and lifecycle policies.
    """

    BASE = "base"
    EVAL = "eval"
    SUBSYSTEM = "subsystem"
    INIT = "init"
    SIDECAR = "sidecar"
    COMPOSITE = "composite"


class ImageProfile(Enum):
    """Evaluation image profiles.

    Each evaluation profile represents a distinct operational mode
    of the FizzBuzz engine, requiring different infrastructure
    module subsets in the image.
    """

    STANDARD = "standard"
    CONFIGURABLE = "configurable"
    CACHED = "cached"
    ML = "ml"


class ArchPlatform(Enum):
    """Supported target architectures for multi-arch builds.

    The catalog produces images for each supported platform,
    aggregated into OCI image indexes for transparent platform
    resolution at pull time.
    """

    LINUX_AMD64 = "linux/amd64"
    LINUX_ARM64 = "linux/arm64"
    FIZZBUZZ_VM = "fizzbuzz/vm"


class ScanSeverity(Enum):
    """Vulnerability severity levels for catalog scanning.

    Severities follow the CVSS v3.x classification scheme,
    mapping score ranges to categorical severity labels.
    """

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NEGLIGIBLE = "negligible"


class VersionBump(Enum):
    """Semantic version bump classification.

    Determines which component of the semantic version to
    increment based on the nature of the change.
    """

    MAJOR = "major"
    MINOR = "minor"
    PATCH = "patch"


class BuildStatus(Enum):
    """Status of an image build operation.

    Tracks the lifecycle of a build from initial registration
    through scanning, publishing, and final status.
    """

    PENDING = "pending"
    BUILDING = "building"
    SCANNING = "scanning"
    PUBLISHING = "publishing"
    COMPLETE = "complete"
    FAILED = "failed"
    BLOCKED = "blocked"


class InitPolicy(Enum):
    """Failure policy for init containers.

    Determines the recovery behavior when an init container
    exits with a non-zero status during pre-flight execution.
    """

    RESTART_ON_FAILURE = "restart"
    ABORT_ON_FAILURE = "abort"
    IGNORE_FAILURE = "ignore"


# ============================================================
# Data Classes
# ============================================================


@dataclass
class ImageSpec:
    """Specification for an image to be registered in the catalog.

    Defines the image name, type, base image, dependencies,
    FizzFile instructions, metadata, and target platforms.

    Attributes:
        name: Image name (e.g., "fizzbuzz-base", "fizzbuzz-eval").
        image_type: Classification of the image.
        base_image: Base image reference (empty for base images).
        dependencies: List of dependent image names.
        fizzfile_instructions: FizzFile DSL instructions.
        metadata: OCI annotation metadata.
        target_platforms: Target architectures.
        profile: Evaluation profile (for eval images).
        module_name: Source module name (for subsystem images).
        labels: Additional key-value labels.
    """

    name: str
    image_type: ImageType = ImageType.SUBSYSTEM
    base_image: str = ""
    dependencies: List[str] = field(default_factory=list)
    fizzfile_instructions: List[str] = field(default_factory=list)
    metadata: Optional[ImageMetadata] = None
    target_platforms: List[ArchPlatform] = field(
        default_factory=lambda: list(ArchPlatform)
    )
    profile: Optional[ImageProfile] = None
    module_name: str = ""
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class ImageManifest:
    """Built image manifest with layer and metadata information.

    Represents a fully built and registered image in the catalog,
    including its digest, layers, size, metadata, version, and
    scan status.

    Attributes:
        name: Image name.
        digest: SHA-256 digest of the manifest.
        image_type: Classification of the image.
        layers: Ordered list of layer descriptors.
        total_size: Total size of all layers in bytes.
        metadata: OCI annotation metadata.
        version: Current version tag.
        tags: All assigned tags.
        scan_result: Vulnerability scan result (if scanned).
        build_status: Current build status.
        created_at: When the image was built.
        platform: Target platform.
    """

    name: str
    digest: str = ""
    image_type: ImageType = ImageType.SUBSYSTEM
    layers: List[LayerDescriptor] = field(default_factory=list)
    total_size: int = 0
    metadata: Optional[ImageMetadata] = None
    version: Optional[VersionTag] = None
    tags: List[str] = field(default_factory=list)
    scan_result: Optional[ScanResult] = None
    build_status: BuildStatus = BuildStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    platform: ArchPlatform = ArchPlatform.LINUX_AMD64


@dataclass
class LayerDescriptor:
    """Describes a single layer in an image.

    Each layer represents a filesystem change resulting from a
    FizzFile instruction, identified by its content digest and
    carrying size and instruction metadata.

    Attributes:
        digest: SHA-256 digest of the layer content.
        size: Size of the layer in bytes.
        media_type: OCI media type of the layer.
        instruction: FizzFile instruction that produced this layer.
        created_at: When the layer was created.
        annotations: OCI layer annotations.
    """

    digest: str
    size: int = 0
    media_type: str = "application/vnd.oci.image.layer.v1.tar+gzip"
    instruction: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    annotations: Dict[str, str] = field(default_factory=dict)


@dataclass
class ScanResult:
    """Vulnerability scan result for an image.

    Summarizes the vulnerabilities found in an image, broken down
    by severity level, with the overall admission decision.

    Attributes:
        image_name: Scanned image name.
        image_digest: Digest of the scanned manifest.
        total_vulnerabilities: Total number of vulnerabilities found.
        critical_count: Number of CRITICAL vulnerabilities.
        high_count: Number of HIGH vulnerabilities.
        medium_count: Number of MEDIUM vulnerabilities.
        low_count: Number of LOW vulnerabilities.
        negligible_count: Number of NEGLIGIBLE vulnerabilities.
        admitted: Whether the image passed the severity threshold.
        vulnerabilities: Detailed vulnerability entries.
        scanned_at: When the scan was performed.
        scan_duration_ms: Duration of the scan in milliseconds.
    """

    image_name: str
    image_digest: str = ""
    total_vulnerabilities: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    negligible_count: int = 0
    admitted: bool = True
    vulnerabilities: List[VulnerabilityEntry] = field(default_factory=list)
    scanned_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    scan_duration_ms: float = 0.0


@dataclass
class VulnerabilityEntry:
    """A single vulnerability finding.

    Attributes:
        cve_id: CVE identifier.
        severity: Severity level.
        package: Affected package name.
        installed_version: Installed version of the package.
        fixed_version: Version that fixes the vulnerability (empty if no fix).
        description: Vulnerability description.
    """

    cve_id: str
    severity: ScanSeverity = ScanSeverity.LOW
    package: str = ""
    installed_version: str = ""
    fixed_version: str = ""
    description: str = ""


@dataclass
class VersionTag:
    """Semantic version tag for an image.

    Attributes:
        major: Major version number.
        minor: Minor version number.
        patch: Patch version number.
        commit_sha: Git commit SHA tag.
        tags: All string tags assigned to this version.
    """

    major: int = 1
    minor: int = 0
    patch: int = 0
    commit_sha: str = ""
    tags: List[str] = field(default_factory=list)

    @property
    def semver(self) -> str:
        """Return the semantic version string."""
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass
class InitContainerSpec:
    """Specification for an init container.

    Defines the init container's image, ordering, shared volumes,
    and failure policy.

    Attributes:
        name: Init container name.
        image: Image reference.
        order: Execution order (lower runs first).
        shared_volumes: List of volume mount paths.
        failure_policy: What to do if the init container fails.
        env: Environment variables.
        args: Entrypoint arguments.
        timeout_seconds: Maximum execution time in seconds.
    """

    name: str
    image: str = ""
    order: int = 0
    shared_volumes: List[str] = field(default_factory=list)
    failure_policy: InitPolicy = InitPolicy.ABORT_ON_FAILURE
    env: List[str] = field(default_factory=list)
    args: List[str] = field(default_factory=list)
    timeout_seconds: int = 300


@dataclass
class ImageIndex:
    """OCI image index (manifest list) for multi-architecture support.

    Maps a single image reference to platform-specific manifests.

    Attributes:
        image_name: Image name this index references.
        digest: SHA-256 digest of the index.
        media_type: OCI media type.
        manifests: Platform-to-manifest mapping.
        annotations: Index annotations.
        created_at: When the index was created.
    """

    image_name: str
    digest: str = ""
    media_type: str = "application/vnd.oci.image.index.v1+json"
    manifests: Dict[str, ImageManifest] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class CatalogStats:
    """Aggregate statistics for the image catalog.

    Attributes:
        total_images: Total images registered in the catalog.
        base_images: Number of base images.
        eval_images: Number of evaluation images.
        subsystem_images: Number of subsystem images.
        init_images: Number of init container images.
        sidecar_images: Number of sidecar images.
        composite_images: Number of composite group images.
        total_layers: Total layers across all images.
        total_size_bytes: Total size of all images in bytes.
        total_scans: Total vulnerability scans performed.
        images_admitted: Images that passed scanning.
        images_blocked: Images blocked by scan policy.
        total_vulnerabilities: Total vulnerabilities found.
        builds_completed: Total successful builds.
        builds_failed: Total failed builds.
    """

    total_images: int = 0
    base_images: int = 0
    eval_images: int = 0
    subsystem_images: int = 0
    init_images: int = 0
    sidecar_images: int = 0
    composite_images: int = 0
    total_layers: int = 0
    total_size_bytes: int = 0
    total_scans: int = 0
    images_admitted: int = 0
    images_blocked: int = 0
    total_vulnerabilities: int = 0
    builds_completed: int = 0
    builds_failed: int = 0


# ============================================================
# ImageMetadata — OCI annotation management
# ============================================================


class ImageMetadata:
    """Manages OCI annotation labels and platform-specific metadata.

    Every image in the catalog carries standard OCI annotations
    (title, description, version, created, authors, source,
    documentation) and platform-specific labels (module, layer,
    dependencies).
    """

    def __init__(
        self,
        title: str,
        description: str,
        version: str,
        module: str = "",
        layer: str = "infrastructure",
        dependencies: Optional[List[str]] = None,
    ) -> None:
        """Initialize image metadata.

        Args:
            title: Human-readable image title.
            description: Human-readable image description.
            version: Packaged software version.
            module: Source infrastructure module name.
            layer: Architecture layer (domain/application/infrastructure).
            dependencies: List of dependency module names.
        """
        self._title = title
        self._description = description
        self._version = version
        self._module = module
        self._layer = layer
        self._dependencies = dependencies or []
        self._created = datetime.now(timezone.utc).isoformat()
        self._authors = IMAGE_AUTHOR
        self._source = "https://github.com/enterprise-fizzbuzz/platform"
        self._documentation = "https://docs.fizzbuzz.enterprise/images"

    @property
    def title(self) -> str:
        """Return the image title."""
        return self._title

    @property
    def description(self) -> str:
        """Return the image description."""
        return self._description

    @property
    def version(self) -> str:
        """Return the version."""
        return self._version

    @property
    def module(self) -> str:
        """Return the source module name."""
        return self._module

    @property
    def layer(self) -> str:
        """Return the architecture layer."""
        return self._layer

    @property
    def dependencies(self) -> List[str]:
        """Return the dependency list."""
        return list(self._dependencies)

    def to_oci_annotations(self) -> Dict[str, str]:
        """Serialize to OCI-standard annotation key-value pairs.

        Returns:
            Dictionary of OCI annotation keys to values, following
            the org.opencontainers.image namespace convention.
        """
        annotations = {
            "org.opencontainers.image.title": self._title,
            "org.opencontainers.image.description": self._description,
            "org.opencontainers.image.version": self._version,
            "org.opencontainers.image.created": self._created,
            "org.opencontainers.image.authors": self._authors,
            "org.opencontainers.image.source": self._source,
            "org.opencontainers.image.documentation": self._documentation,
            "org.opencontainers.image.vendor": "Enterprise FizzBuzz Platform",
        }
        return annotations

    def to_platform_labels(self) -> Dict[str, str]:
        """Serialize to platform-specific label key-value pairs.

        Returns:
            Dictionary of platform label keys to values, using the
            com.fizzbuzz.platform namespace.
        """
        labels = {
            "com.fizzbuzz.platform.module": self._module,
            "com.fizzbuzz.platform.layer": self._layer,
        }
        if self._dependencies:
            labels["com.fizzbuzz.platform.dependencies"] = ",".join(
                self._dependencies
            )
        return labels

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a complete metadata dictionary.

        Returns:
            Dictionary with all metadata fields.
        """
        return {
            "title": self._title,
            "description": self._description,
            "version": self._version,
            "module": self._module,
            "layer": self._layer,
            "dependencies": list(self._dependencies),
            "created": self._created,
            "authors": self._authors,
            "source": self._source,
            "documentation": self._documentation,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ImageMetadata:
        """Deserialize from a metadata dictionary.

        Args:
            data: Dictionary with metadata fields.

        Returns:
            ImageMetadata instance.
        """
        return cls(
            title=data.get("title", ""),
            description=data.get("description", ""),
            version=data.get("version", ""),
            module=data.get("module", ""),
            layer=data.get("layer", "infrastructure"),
            dependencies=data.get("dependencies"),
        )


# ============================================================
# ImageCatalog — central image registry
# ============================================================


class ImageCatalog:
    """Official container image catalog for the Enterprise FizzBuzz Platform.

    Manages the inventory of all official images: base, evaluation,
    subsystem, init container, and sidecar images.  Provides build,
    scan, inspect, and dependency resolution operations across the
    entire catalog.
    """

    def __init__(
        self,
        registry_url: str = DEFAULT_REGISTRY_URL,
        base_image_name: str = DEFAULT_BASE_IMAGE,
        scan_severity_threshold: str = DEFAULT_SCAN_SEVERITY_THRESHOLD,
        max_catalog_size: int = DEFAULT_MAX_CATALOG_SIZE,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize the image catalog.

        Args:
            registry_url: Registry URL for image push/pull.
            base_image_name: Name of the foundation base image.
            scan_severity_threshold: Maximum severity for admission.
            max_catalog_size: Maximum images in the catalog.
            event_bus: Optional event bus for lifecycle events.
        """
        self._registry_url = registry_url
        self._base_image_name = base_image_name
        self._scan_severity_threshold = scan_severity_threshold
        self._max_catalog_size = max_catalog_size
        self._event_bus = event_bus
        self._images: Dict[str, ImageManifest] = {}
        self._specs: Dict[str, ImageSpec] = {}
        self._lock = threading.Lock()
        self._builds_completed = 0
        self._builds_failed = 0
        self._total_scans = 0
        self._images_admitted = 0
        self._images_blocked = 0
        self._total_vulnerabilities = 0
        logger.info(
            "ImageCatalog initialized (registry=%s, max_size=%d)",
            registry_url,
            max_catalog_size,
        )

    @property
    def registry_url(self) -> str:
        """Return the registry URL."""
        return self._registry_url

    @property
    def base_image_name(self) -> str:
        """Return the base image name."""
        return self._base_image_name

    def register_image(self, spec: ImageSpec) -> ImageManifest:
        """Register a new image specification in the catalog.

        Creates an initial manifest in PENDING status from the
        provided specification.

        Args:
            spec: Image specification to register.

        Returns:
            The initial ImageManifest for the registered image.

        Raises:
            ImageAlreadyExistsError: If image name already exists.
            CatalogCapacityError: If catalog is at maximum capacity.
        """
        with self._lock:
            if spec.name in self._images:
                raise ImageAlreadyExistsError(
                    f"Image '{spec.name}' already exists in the catalog"
                )
            if len(self._images) >= self._max_catalog_size:
                raise CatalogCapacityError(
                    f"Catalog capacity exceeded ({self._max_catalog_size} images)"
                )

            manifest = ImageManifest(
                name=spec.name,
                image_type=spec.image_type,
                build_status=BuildStatus.PENDING,
                metadata=spec.metadata,
            )
            self._images[spec.name] = manifest
            self._specs[spec.name] = spec

        self._emit_event(FIZZIMAGE_IMAGE_REGISTERED, {"image_name": spec.name})
        logger.info("Image registered: %s (type=%s)", spec.name, spec.image_type.value)
        return manifest

    def build_image(self, image_name: str) -> ImageManifest:
        """Build a registered image.

        Executes the image's FizzFile instructions, generates layers,
        computes the manifest digest, and transitions to COMPLETE.

        Args:
            image_name: Name of the image to build.

        Returns:
            The built ImageManifest with layers and digest.

        Raises:
            ImageNotFoundError: If image is not registered.
            ImageBuildError: If the build fails.
        """
        with self._lock:
            if image_name not in self._images:
                raise ImageNotFoundError(
                    f"Image '{image_name}' not found in catalog"
                )
            manifest = self._images[image_name]
            spec = self._specs.get(image_name)

        if manifest.build_status == BuildStatus.COMPLETE:
            return manifest

        try:
            manifest.build_status = BuildStatus.BUILDING

            # Generate layers from FizzFile instructions
            instructions = spec.fizzfile_instructions if spec else []
            if not instructions:
                instructions = [f"FROM {self._base_image_name}"]

            layers = []
            for instruction in instructions:
                layer = self._create_layer(instruction)
                layers.append(layer)

            manifest.layers = layers
            manifest.total_size = sum(l.size for l in layers)
            manifest.digest = self._compute_manifest_digest(manifest)
            manifest.build_status = BuildStatus.COMPLETE
            self._builds_completed += 1

            with self._lock:
                self._images[image_name] = manifest

            self._emit_event(
                FIZZIMAGE_BASE_BUILT
                if manifest.image_type == ImageType.BASE
                else FIZZIMAGE_EVAL_BUILT,
                {"image_name": image_name, "digest": manifest.digest},
            )

            logger.info(
                "Image built: %s (layers=%d, size=%d bytes)",
                image_name,
                len(layers),
                manifest.total_size,
            )
            return manifest

        except FizzImageError:
            manifest.build_status = BuildStatus.FAILED
            self._builds_failed += 1
            raise
        except Exception as exc:
            manifest.build_status = BuildStatus.FAILED
            self._builds_failed += 1
            raise ImageBuildError(
                f"Failed to build image '{image_name}': {exc}"
            ) from exc

    def build_all(self) -> List[ImageManifest]:
        """Build all registered images in dependency order.

        Resolves the build order based on inter-image dependencies,
        then builds each image sequentially.

        Returns:
            List of built ImageManifest objects.
        """
        self._emit_event(FIZZIMAGE_BUILD_ALL_STARTED, {})
        build_order = self._resolve_build_order()
        results = []
        for image_name in build_order:
            manifest = self.build_image(image_name)
            results.append(manifest)
        self._emit_event(
            FIZZIMAGE_BUILD_ALL_COMPLETED,
            {"images_built": len(results)},
        )
        return results

    def get_image(self, image_name: str) -> ImageManifest:
        """Retrieve an image manifest by name.

        Args:
            image_name: Image name to look up.

        Returns:
            The ImageManifest for the requested image.

        Raises:
            ImageNotFoundError: If image is not registered.
        """
        with self._lock:
            if image_name not in self._images:
                raise ImageNotFoundError(
                    f"Image '{image_name}' not found in catalog"
                )
            return self._images[image_name]

    def list_images(self) -> List[ImageManifest]:
        """List all images in the catalog.

        Returns:
            List of all ImageManifest objects.
        """
        with self._lock:
            return list(self._images.values())

    def inspect_image(self, image_name: str) -> Dict[str, Any]:
        """Inspect an image, returning detailed information.

        Args:
            image_name: Image name to inspect.

        Returns:
            Dictionary containing all image details.

        Raises:
            ImageNotFoundError: If image is not registered.
        """
        manifest = self.get_image(image_name)
        spec = self._specs.get(image_name)

        result: Dict[str, Any] = {
            "name": manifest.name,
            "digest": manifest.digest,
            "type": manifest.image_type.value,
            "status": manifest.build_status.value,
            "total_size": manifest.total_size,
            "layer_count": len(manifest.layers),
            "created_at": manifest.created_at.isoformat(),
            "platform": manifest.platform.value,
            "tags": list(manifest.tags),
        }

        if manifest.metadata:
            result["metadata"] = manifest.metadata.to_dict()

        if manifest.version:
            result["version"] = manifest.version.semver

        if manifest.scan_result:
            result["scan"] = {
                "total_vulnerabilities": manifest.scan_result.total_vulnerabilities,
                "critical": manifest.scan_result.critical_count,
                "high": manifest.scan_result.high_count,
                "medium": manifest.scan_result.medium_count,
                "low": manifest.scan_result.low_count,
                "admitted": manifest.scan_result.admitted,
            }

        if spec:
            result["dependencies"] = list(spec.dependencies)
            result["base_image"] = spec.base_image

        result["layers"] = [
            {
                "digest": layer.digest,
                "size": layer.size,
                "instruction": layer.instruction,
            }
            for layer in manifest.layers
        ]

        return result

    def get_dependencies(self, image_name: str) -> List[str]:
        """Get the dependency list for an image.

        Args:
            image_name: Image name.

        Returns:
            List of dependency image names.

        Raises:
            ImageNotFoundError: If image is not registered.
        """
        with self._lock:
            if image_name not in self._specs:
                raise ImageNotFoundError(
                    f"Image '{image_name}' not found in catalog"
                )
            spec = self._specs[image_name]
        return list(spec.dependencies)

    def scan_all(self) -> List[ScanResult]:
        """Run vulnerability scanning on all built images.

        Returns:
            List of ScanResult objects for all scanned images.
        """
        results = []
        for manifest in self.list_images():
            if manifest.build_status == BuildStatus.COMPLETE:
                # Use the catalog scanner if attached, otherwise skip
                result = ScanResult(
                    image_name=manifest.name,
                    image_digest=manifest.digest,
                    admitted=True,
                )
                manifest.scan_result = result
                self._total_scans += 1
                self._images_admitted += 1
                results.append(result)
        return results

    def remove_image(self, image_name: str) -> None:
        """Remove an image from the catalog.

        Args:
            image_name: Image name to remove.

        Raises:
            ImageNotFoundError: If image is not registered.
        """
        with self._lock:
            if image_name not in self._images:
                raise ImageNotFoundError(
                    f"Image '{image_name}' not found in catalog"
                )
            del self._images[image_name]
            self._specs.pop(image_name, None)

        self._emit_event(FIZZIMAGE_IMAGE_REMOVED, {"image_name": image_name})
        logger.info("Image removed: %s", image_name)

    def get_stats(self) -> CatalogStats:
        """Compute aggregate catalog statistics.

        Returns:
            CatalogStats with current metrics.
        """
        with self._lock:
            images = list(self._images.values())

        stats = CatalogStats(
            total_images=len(images),
            total_layers=sum(len(m.layers) for m in images),
            total_size_bytes=sum(m.total_size for m in images),
            total_scans=self._total_scans,
            images_admitted=self._images_admitted,
            images_blocked=self._images_blocked,
            total_vulnerabilities=self._total_vulnerabilities,
            builds_completed=self._builds_completed,
            builds_failed=self._builds_failed,
        )

        for m in images:
            if m.image_type == ImageType.BASE:
                stats.base_images += 1
            elif m.image_type == ImageType.EVAL:
                stats.eval_images += 1
            elif m.image_type == ImageType.SUBSYSTEM:
                stats.subsystem_images += 1
            elif m.image_type == ImageType.INIT:
                stats.init_images += 1
            elif m.image_type == ImageType.SIDECAR:
                stats.sidecar_images += 1
            elif m.image_type == ImageType.COMPOSITE:
                stats.composite_images += 1

        return stats

    def _resolve_build_order(self) -> List[str]:
        """Resolve the build order using topological sort.

        Returns:
            List of image names in dependency-safe build order.
        """
        with self._lock:
            specs = dict(self._specs)

        # Build adjacency for topological sort
        in_degree: Dict[str, int] = {name: 0 for name in specs}
        dependents: Dict[str, List[str]] = defaultdict(list)

        for name, spec in specs.items():
            for dep in spec.dependencies:
                if dep in specs:
                    in_degree[name] += 1
                    dependents[dep].append(name)

        # Kahn's algorithm
        queue = [name for name, degree in in_degree.items() if degree == 0]
        order: List[str] = []

        while queue:
            current = queue.pop(0)
            order.append(current)
            for dependent in dependents.get(current, []):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        # Append any remaining (circular) entries
        for name in specs:
            if name not in order:
                order.append(name)

        return order

    def _create_layer(self, instruction: str) -> LayerDescriptor:
        """Create a layer descriptor from a FizzFile instruction.

        Args:
            instruction: FizzFile instruction string.

        Returns:
            LayerDescriptor with computed digest and size.
        """
        content = instruction.encode("utf-8")
        digest = "sha256:" + hashlib.sha256(content).hexdigest()
        size = len(content) * 64  # Simulated layer size
        return LayerDescriptor(
            digest=digest,
            size=size,
            instruction=instruction,
        )

    def _compute_manifest_digest(self, manifest: ImageManifest) -> str:
        """Compute the SHA-256 digest of a manifest.

        Args:
            manifest: ImageManifest to compute digest for.

        Returns:
            Digest string in 'sha256:<hex>' format.
        """
        hasher = hashlib.sha256()
        hasher.update(manifest.name.encode("utf-8"))
        for layer in manifest.layers:
            hasher.update(layer.digest.encode("utf-8"))
        return "sha256:" + hasher.hexdigest()

    def _emit_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Emit an event through the event bus if available.

        Args:
            event_type: Event type identifier.
            data: Event data payload.
        """
        if self._event_bus and hasattr(self._event_bus, "publish"):
            try:
                self._event_bus.publish(event_type, data)
            except Exception:
                pass


# ============================================================
# BaseImageBuilder
# ============================================================


class BaseImageBuilder:
    """Builds the fizzbuzz-base foundation image.

    Constructs the minimal base image from its FizzFile definition,
    executing each instruction as an overlay layer and pushing the
    result to the registry.  Validates that the base image contains
    no infrastructure module dependencies.
    """

    def __init__(
        self,
        catalog: ImageCatalog,
        base_image_name: str = DEFAULT_BASE_IMAGE,
        python_version: str = DEFAULT_PYTHON_VERSION,
    ) -> None:
        """Initialize the base image builder.

        Args:
            catalog: Image catalog for registration.
            base_image_name: Name for the base image.
            python_version: Python version to install.
        """
        self._catalog = catalog
        self._base_image_name = base_image_name
        self._python_version = python_version

    @property
    def base_image_name(self) -> str:
        """Return the base image name."""
        return self._base_image_name

    def build(self) -> ImageManifest:
        """Build the base image.

        Generates the FizzFile, registers the image spec, and
        builds it through the catalog.

        Returns:
            Built ImageManifest for the base image.
        """
        fizzfile = self.generate_fizzfile()
        instructions = [
            line.strip()
            for line in fizzfile.strip().split("\n")
            if line.strip() and not line.strip().startswith("#")
        ]

        metadata = ImageMetadata(
            title="Enterprise FizzBuzz Base Image",
            description=(
                "Foundation image containing the Python runtime, "
                "domain layer models, exceptions, and interfaces."
            ),
            version=FIZZIMAGE_VERSION,
            module="",
            layer="domain",
        )

        spec = ImageSpec(
            name=self._base_image_name,
            image_type=ImageType.BASE,
            base_image="scratch",
            fizzfile_instructions=instructions,
            metadata=metadata,
        )

        try:
            self._catalog.register_image(spec)
        except ImageAlreadyExistsError:
            pass

        manifest = self._catalog.build_image(self._base_image_name)

        # Validate the dependency rule
        self.validate_dependency_rule(manifest)

        return manifest

    def generate_fizzfile(self) -> str:
        """Generate the FizzFile for the base image.

        Returns:
            FizzFile DSL string for the base image.
        """
        return (
            f"FROM scratch\n"
            f"LABEL maintainer=\"{IMAGE_AUTHOR}\"\n"
            f"ENV PYTHON_VERSION={self._python_version}\n"
            f"RUN install-python {self._python_version}\n"
            f"COPY enterprise_fizzbuzz/domain /app/enterprise_fizzbuzz/domain\n"
            f"ENV PYTHONPATH=/app\n"
            f"ENTRYPOINT [\"python\", \"-m\", \"enterprise_fizzbuzz\"]\n"
        )

    def validate_dependency_rule(self, manifest: ImageManifest) -> bool:
        """Validate that the base image obeys the dependency rule.

        The base image must contain only the domain layer. Any
        reference to application or infrastructure modules violates
        the Clean Architecture dependency rule.

        Args:
            manifest: Built manifest to validate.

        Returns:
            True if the dependency rule is satisfied.

        Raises:
            DependencyRuleViolationError: If violations are detected.
        """
        for layer in manifest.layers:
            instruction = layer.instruction.lower()
            if "infrastructure" in instruction and "copy" in instruction:
                raise DependencyRuleViolationError(
                    f"Base image layer references infrastructure: "
                    f"{layer.instruction}"
                )
        return True

    def _create_base_layers(self) -> List[LayerDescriptor]:
        """Create the base image layer stack.

        Returns:
            Ordered list of LayerDescriptor objects.
        """
        layer_defs = [
            ("python-runtime", f"RUN install-python {self._python_version}"),
            ("domain-models", "COPY enterprise_fizzbuzz/domain/models.py /app/"),
            ("domain-exceptions", "COPY enterprise_fizzbuzz/domain/exceptions.py /app/"),
            ("domain-interfaces", "COPY enterprise_fizzbuzz/domain/interfaces.py /app/"),
        ]

        layers = []
        for name, instruction in layer_defs:
            content = f"{name}:{instruction}".encode("utf-8")
            digest = "sha256:" + hashlib.sha256(content).hexdigest()
            layers.append(
                LayerDescriptor(
                    digest=digest,
                    size=len(content) * 64,
                    instruction=instruction,
                )
            )
        return layers

    def _compute_layer_digest(self, content: bytes) -> str:
        """Compute the SHA-256 digest of layer content.

        Args:
            content: Raw layer content bytes.

        Returns:
            Digest string in 'sha256:<hex>' format.
        """
        return "sha256:" + hashlib.sha256(content).hexdigest()


# ============================================================
# EvalImageBuilder
# ============================================================


class EvalImageBuilder:
    """Builds fizzbuzz-eval profile images.

    Extends fizzbuzz-base with the application layer (service builder,
    rule factories, strategy ports) and the minimal infrastructure
    required for each evaluation profile.  Each profile is independently
    versioned and tagged.
    """

    PROFILE_DEPS = {
        ImageProfile.STANDARD: ["rule_engine"],
        ImageProfile.CONFIGURABLE: ["rule_engine", "config"],
        ImageProfile.CACHED: ["rule_engine", "cache"],
        ImageProfile.ML: ["rule_engine", "ml_engine"],
    }

    PROFILE_ENTRYPOINTS = {
        ImageProfile.STANDARD: ["python", "-m", "enterprise_fizzbuzz", "--profile", "standard"],
        ImageProfile.CONFIGURABLE: ["python", "-m", "enterprise_fizzbuzz", "--profile", "configurable"],
        ImageProfile.CACHED: ["python", "-m", "enterprise_fizzbuzz", "--profile", "cached"],
        ImageProfile.ML: ["python", "-m", "enterprise_fizzbuzz", "--profile", "ml"],
    }

    def __init__(
        self,
        catalog: ImageCatalog,
        base_builder: BaseImageBuilder,
    ) -> None:
        """Initialize the evaluation image builder.

        Args:
            catalog: Image catalog for registration.
            base_builder: Base image builder for base image reference.
        """
        self._catalog = catalog
        self._base_builder = base_builder

    def build_profile(self, profile: ImageProfile) -> ImageManifest:
        """Build an evaluation profile image.

        Args:
            profile: Evaluation profile to build.

        Returns:
            Built ImageManifest for the profile image.
        """
        image_name = f"fizzbuzz-eval-{profile.value}"
        fizzfile = self.generate_fizzfile(profile)
        instructions = [
            line.strip()
            for line in fizzfile.strip().split("\n")
            if line.strip() and not line.strip().startswith("#")
        ]

        metadata = ImageMetadata(
            title=f"FizzBuzz Eval Image ({profile.value})",
            description=(
                f"Evaluation runtime image for the {profile.value} profile, "
                f"extending the base image with application layer components."
            ),
            version=FIZZIMAGE_VERSION,
            layer="application",
        )

        spec = ImageSpec(
            name=image_name,
            image_type=ImageType.EVAL,
            base_image=self._base_builder.base_image_name,
            dependencies=[self._base_builder.base_image_name],
            fizzfile_instructions=instructions,
            metadata=metadata,
            profile=profile,
        )

        try:
            self._catalog.register_image(spec)
        except ImageAlreadyExistsError:
            pass

        return self._catalog.build_image(image_name)

    def build_all_profiles(self) -> List[ImageManifest]:
        """Build all evaluation profile images.

        Returns:
            List of built ImageManifest objects.
        """
        results = []
        for profile in ImageProfile:
            manifest = self.build_profile(profile)
            results.append(manifest)
        return results

    def generate_fizzfile(self, profile: ImageProfile) -> str:
        """Generate the FizzFile for an evaluation profile.

        Args:
            profile: Evaluation profile.

        Returns:
            FizzFile DSL string.
        """
        base = self._base_builder.base_image_name
        deps = self._get_profile_dependencies(profile)
        entrypoint = self._get_profile_entrypoint(profile)

        lines = [
            f"FROM {base}",
            f"LABEL profile=\"{profile.value}\"",
            "COPY enterprise_fizzbuzz/application /app/enterprise_fizzbuzz/application",
        ]
        for dep in deps:
            lines.append(
                f"COPY enterprise_fizzbuzz/infrastructure/{dep}.py "
                f"/app/enterprise_fizzbuzz/infrastructure/{dep}.py"
            )
        entrypoint_str = ", ".join(f'"{arg}"' for arg in entrypoint)
        lines.append(f"ENTRYPOINT [{entrypoint_str}]")
        return "\n".join(lines) + "\n"

    def _get_profile_dependencies(self, profile: ImageProfile) -> List[str]:
        """Get infrastructure module dependencies for a profile.

        Args:
            profile: Evaluation profile.

        Returns:
            List of module names.
        """
        return list(self.PROFILE_DEPS.get(profile, []))

    def _get_profile_entrypoint(self, profile: ImageProfile) -> List[str]:
        """Get the container entrypoint for a profile.

        Args:
            profile: Evaluation profile.

        Returns:
            List of entrypoint command components.
        """
        return list(self.PROFILE_ENTRYPOINTS.get(profile, ["python"]))


# ============================================================
# SubsystemImageGenerator
# ============================================================


class SubsystemImageGenerator:
    """Generates per-subsystem container images.

    Analyzes each infrastructure module's import graph via AST
    parsing, determines the minimal dependency set, resolves
    transitive dependencies, and generates a FizzFile that installs
    only those dependencies on top of fizzbuzz-base.  Related
    subsystems are grouped into composite images where independent
    packaging would create excessive inter-container communication
    overhead.
    """

    def __init__(
        self,
        catalog: ImageCatalog,
        base_image_name: str = DEFAULT_BASE_IMAGE,
        module_base_path: str = DEFAULT_MODULE_BASE_PATH,
    ) -> None:
        """Initialize the subsystem image generator.

        Args:
            catalog: Image catalog for registration.
            base_image_name: Name of the base image.
            module_base_path: Base Python package path for modules.
        """
        self._catalog = catalog
        self._base_image_name = base_image_name
        self._module_base_path = module_base_path
        self._dependency_cache: Dict[str, List[str]] = {}

    def analyze_module(self, module_name: str) -> List[str]:
        """Analyze a module's import dependencies via AST parsing.

        Extracts import statements from the module source and
        identifies dependencies on other infrastructure modules.

        Args:
            module_name: Module name to analyze.

        Returns:
            List of dependency module names.
        """
        if module_name in self._dependency_cache:
            return list(self._dependency_cache[module_name])

        imports = self._ast_extract_imports(module_name)
        self._dependency_cache[module_name] = imports
        return imports

    def generate_fizzfile(self, module_name: str) -> str:
        """Generate a FizzFile for a subsystem image.

        Args:
            module_name: Module name to generate FizzFile for.

        Returns:
            FizzFile DSL string.
        """
        deps = self._resolve_transitive_deps(module_name)
        lines = [
            f"FROM {self._base_image_name}",
            f"LABEL module=\"{module_name}\"",
            f"LABEL subsystem=\"true\"",
        ]

        # Copy the module itself
        lines.append(
            f"COPY enterprise_fizzbuzz/infrastructure/{module_name}.py "
            f"/app/enterprise_fizzbuzz/infrastructure/{module_name}.py"
        )

        # Copy transitive dependencies
        for dep in sorted(deps):
            if dep != module_name:
                lines.append(
                    f"COPY enterprise_fizzbuzz/infrastructure/{dep}.py "
                    f"/app/enterprise_fizzbuzz/infrastructure/{dep}.py"
                )

        lines.append(
            f"ENTRYPOINT [\"python\", \"-m\", "
            f"\"enterprise_fizzbuzz.infrastructure.{module_name}\"]"
        )
        return "\n".join(lines) + "\n"

    def build_subsystem_image(self, module_name: str) -> ImageManifest:
        """Build a container image for a single subsystem module.

        Args:
            module_name: Module name to build image for.

        Returns:
            Built ImageManifest.
        """
        image_name = f"fizzbuzz-{module_name}"
        fizzfile = self.generate_fizzfile(module_name)
        instructions = [
            line.strip()
            for line in fizzfile.strip().split("\n")
            if line.strip() and not line.strip().startswith("#")
        ]

        deps = self.analyze_module(module_name)

        metadata = ImageMetadata(
            title=f"FizzBuzz {module_name} Subsystem Image",
            description=(
                f"Container image for the {module_name} infrastructure module "
                f"with {len(deps)} direct dependencies."
            ),
            version=FIZZIMAGE_VERSION,
            module=module_name,
            dependencies=deps,
        )

        spec = ImageSpec(
            name=image_name,
            image_type=ImageType.SUBSYSTEM,
            base_image=self._base_image_name,
            dependencies=[self._base_image_name],
            fizzfile_instructions=instructions,
            metadata=metadata,
            module_name=module_name,
        )

        try:
            self._catalog.register_image(spec)
        except ImageAlreadyExistsError:
            pass

        manifest = self._catalog.build_image(image_name)

        self._catalog._emit_event(
            FIZZIMAGE_SUBSYSTEM_GENERATED,
            {"module": module_name, "image": image_name},
        )

        return manifest

    def build_all_subsystem_images(self) -> List[ImageManifest]:
        """Build images for all known subsystem modules.

        Returns:
            List of built ImageManifest objects.
        """
        results = []
        for group_name, modules in IMAGE_GROUPS.items():
            for module_name in modules:
                manifest = self.build_subsystem_image(module_name)
                results.append(manifest)
        return results

    def detect_circular_groups(self) -> List[List[str]]:
        """Detect groups of modules with circular dependencies.

        Uses depth-first search to find strongly connected components
        of size greater than one.

        Returns:
            List of module name groups with circular dependencies.
        """
        all_modules: Set[str] = set()
        for modules in IMAGE_GROUPS.values():
            all_modules.update(modules)

        graph: Dict[str, Set[str]] = {}
        for module in all_modules:
            deps = set(self.analyze_module(module))
            graph[module] = deps & all_modules

        # Tarjan-like SCC detection
        visited: Set[str] = set()
        stack: List[str] = []
        on_stack: Set[str] = set()
        index_map: Dict[str, int] = {}
        lowlink: Dict[str, int] = {}
        index_counter = [0]
        sccs: List[List[str]] = []

        def strongconnect(node: str) -> None:
            index_map[node] = index_counter[0]
            lowlink[node] = index_counter[0]
            index_counter[0] += 1
            stack.append(node)
            on_stack.add(node)

            for neighbor in graph.get(node, set()):
                if neighbor not in index_map:
                    strongconnect(neighbor)
                    lowlink[node] = min(lowlink[node], lowlink[neighbor])
                elif neighbor in on_stack:
                    lowlink[node] = min(lowlink[node], index_map[neighbor])

            if lowlink[node] == index_map[node]:
                scc: List[str] = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    scc.append(w)
                    if w == node:
                        break
                if len(scc) > 1:
                    sccs.append(scc)

        for module in all_modules:
            if module not in index_map:
                strongconnect(module)

        return sccs

    def get_image_groups(self) -> Dict[str, List[str]]:
        """Return the subsystem image groupings.

        Returns:
            Dictionary mapping group names to module lists.
        """
        return dict(IMAGE_GROUPS)

    def _resolve_transitive_deps(self, module_name: str) -> Set[str]:
        """Resolve transitive dependencies for a module.

        Args:
            module_name: Module to resolve dependencies for.

        Returns:
            Set of all transitively required module names.
        """
        resolved: Set[str] = set()
        queue = [module_name]

        while queue:
            current = queue.pop(0)
            if current in resolved:
                continue
            resolved.add(current)
            direct_deps = self.analyze_module(current)
            for dep in direct_deps:
                if dep not in resolved:
                    queue.append(dep)

        return resolved

    def _ast_extract_imports(self, module_name: str) -> List[str]:
        """Extract import statements from a module using AST parsing.

        Simulates AST analysis by deriving plausible dependencies
        from the module name and known subsystem groupings.

        Args:
            module_name: Module name to analyze.

        Returns:
            List of dependency module names.
        """
        # Simulate AST import analysis based on known groupings
        deps: List[str] = []
        for group_name, modules in IMAGE_GROUPS.items():
            if module_name in modules:
                for peer in modules:
                    if peer != module_name:
                        deps.append(peer)
                break
        return deps


# ============================================================
# InitContainerBuilder
# ============================================================


class InitContainerBuilder:
    """Builds init container images for pre-flight setup.

    Creates specialized images for configuration loading, schema
    migration, and secret injection.  Init containers execute
    before the main container and share data via volumes.
    """

    INIT_TYPES = ["config", "schema", "secrets"]

    def __init__(
        self,
        catalog: ImageCatalog,
        base_image_name: str = DEFAULT_BASE_IMAGE,
    ) -> None:
        """Initialize the init container builder.

        Args:
            catalog: Image catalog for registration.
            base_image_name: Name of the base image.
        """
        self._catalog = catalog
        self._base_image_name = base_image_name

    def build_config_init(self) -> ImageManifest:
        """Build the configuration init container image.

        Generates config files from templates and writes them to
        a shared volume before the main container starts.

        Returns:
            Built ImageManifest.
        """
        return self._build_init("config", order=0)

    def build_schema_init(self) -> ImageManifest:
        """Build the schema migration init container image.

        Applies database schema migrations before the main
        container starts.

        Returns:
            Built ImageManifest.
        """
        return self._build_init("schema", order=1)

    def build_secrets_init(self) -> ImageManifest:
        """Build the secrets init container image.

        Fetches secrets from the vault and writes them to a
        shared volume before the main container starts.

        Returns:
            Built ImageManifest.
        """
        return self._build_init("secrets", order=2)

    def build_all_inits(self) -> List[ImageManifest]:
        """Build all init container images.

        Returns:
            List of built ImageManifest objects.
        """
        return [
            self.build_config_init(),
            self.build_schema_init(),
            self.build_secrets_init(),
        ]

    def generate_fizzfile(self, init_type: str) -> str:
        """Generate the FizzFile for an init container.

        Args:
            init_type: Type of init container (config/schema/secrets).

        Returns:
            FizzFile DSL string.
        """
        lines = [
            f"FROM {self._base_image_name}",
            f"LABEL init.type=\"{init_type}\"",
            f"LABEL init.order=\"{self.INIT_TYPES.index(init_type) if init_type in self.INIT_TYPES else 0}\"",
            f"COPY init/{init_type}.py /init/{init_type}.py",
            f"ENTRYPOINT [\"python\", \"/init/{init_type}.py\"]",
        ]
        return "\n".join(lines) + "\n"

    def get_init_spec(self, init_type: str) -> InitContainerSpec:
        """Get the specification for an init container.

        Args:
            init_type: Type of init container.

        Returns:
            InitContainerSpec for the init container.
        """
        order_map = {"config": 0, "schema": 1, "secrets": 2}
        volume_map = {
            "config": ["/etc/fizzbuzz/config"],
            "schema": ["/var/lib/fizzbuzz/schema"],
            "secrets": ["/run/secrets"],
        }
        timeout_map = {"config": 60, "schema": 300, "secrets": 120}

        return InitContainerSpec(
            name=f"fizzbuzz-init-{init_type}",
            image=f"{self._catalog.registry_url}/fizzbuzz-init-{init_type}:latest",
            order=order_map.get(init_type, 0),
            shared_volumes=volume_map.get(init_type, []),
            timeout_seconds=timeout_map.get(init_type, 300),
        )

    def _build_init(self, init_type: str, order: int = 0) -> ImageManifest:
        """Build an init container image.

        Args:
            init_type: Type of init container.
            order: Execution order.

        Returns:
            Built ImageManifest.
        """
        image_name = f"fizzbuzz-init-{init_type}"
        fizzfile = self.generate_fizzfile(init_type)
        instructions = [
            line.strip()
            for line in fizzfile.strip().split("\n")
            if line.strip() and not line.strip().startswith("#")
        ]

        metadata = ImageMetadata(
            title=f"FizzBuzz Init Container ({init_type})",
            description=(
                f"Init container image for {init_type} pre-flight setup. "
                f"Runs to completion before the main container starts."
            ),
            version=FIZZIMAGE_VERSION,
        )

        spec = ImageSpec(
            name=image_name,
            image_type=ImageType.INIT,
            base_image=self._base_image_name,
            dependencies=[self._base_image_name],
            fizzfile_instructions=instructions,
            metadata=metadata,
        )

        try:
            self._catalog.register_image(spec)
        except ImageAlreadyExistsError:
            pass

        manifest = self._catalog.build_image(image_name)

        self._catalog._emit_event(
            FIZZIMAGE_INIT_BUILT,
            {"init_type": init_type, "image": image_name},
        )

        return manifest


# ============================================================
# SidecarImageBuilder
# ============================================================


class SidecarImageBuilder:
    """Builds sidecar container images for cross-cutting concerns.

    Creates specialized images for logging, metrics, tracing, and
    proxy sidecars.  Sidecar containers run alongside the main
    container and communicate via shared volumes or Unix sockets.
    """

    SIDECAR_TYPES = ["logging", "metrics", "tracing", "proxy"]

    SIDECAR_PORTS = {
        "logging": 5170,
        "metrics": 9090,
        "tracing": 4317,
        "proxy": 15001,
    }

    def __init__(
        self,
        catalog: ImageCatalog,
        base_image_name: str = DEFAULT_BASE_IMAGE,
    ) -> None:
        """Initialize the sidecar image builder.

        Args:
            catalog: Image catalog for registration.
            base_image_name: Name of the base image.
        """
        self._catalog = catalog
        self._base_image_name = base_image_name

    def build_log_sidecar(self) -> ImageManifest:
        """Build the logging sidecar image.

        The logging sidecar collects structured log output from the
        main container via a shared volume and forwards it to the
        configured log aggregation backend.

        Returns:
            Built ImageManifest.
        """
        return self._build_sidecar("logging")

    def build_metrics_sidecar(self) -> ImageManifest:
        """Build the metrics sidecar image.

        The metrics sidecar exposes a Prometheus-compatible /metrics
        endpoint that aggregates FizzBuzz evaluation metrics.

        Returns:
            Built ImageManifest.
        """
        return self._build_sidecar("metrics")

    def build_trace_sidecar(self) -> ImageManifest:
        """Build the tracing sidecar image.

        The tracing sidecar runs an OpenTelemetry Collector that
        receives spans via OTLP on localhost:4317 and exports to
        the configured tracing backend.

        Returns:
            Built ImageManifest.
        """
        return self._build_sidecar("tracing")

    def build_proxy_sidecar(self) -> ImageManifest:
        """Build the proxy sidecar image.

        The proxy sidecar intercepts inbound and outbound network
        traffic for service mesh integration, providing mTLS,
        circuit breaking, and load balancing.

        Returns:
            Built ImageManifest.
        """
        return self._build_sidecar("proxy")

    def build_all_sidecars(self) -> List[ImageManifest]:
        """Build all sidecar images.

        Returns:
            List of built ImageManifest objects.
        """
        return [
            self.build_log_sidecar(),
            self.build_metrics_sidecar(),
            self.build_trace_sidecar(),
            self.build_proxy_sidecar(),
        ]

    def generate_fizzfile(self, sidecar_type: str) -> str:
        """Generate the FizzFile for a sidecar image.

        Args:
            sidecar_type: Type of sidecar (logging/metrics/tracing/proxy).

        Returns:
            FizzFile DSL string.
        """
        port = self.SIDECAR_PORTS.get(sidecar_type, 8080)
        lines = [
            f"FROM {self._base_image_name}",
            f"LABEL sidecar.type=\"{sidecar_type}\"",
            f"LABEL sidecar.port=\"{port}\"",
            f"COPY sidecar/{sidecar_type}.py /sidecar/{sidecar_type}.py",
            f"ENV SIDECAR_PORT={port}",
            f"ENTRYPOINT [\"python\", \"/sidecar/{sidecar_type}.py\"]",
        ]
        return "\n".join(lines) + "\n"

    def _build_sidecar(self, sidecar_type: str) -> ImageManifest:
        """Build a sidecar container image.

        Args:
            sidecar_type: Type of sidecar.

        Returns:
            Built ImageManifest.
        """
        image_name = f"fizzbuzz-sidecar-{sidecar_type}"
        fizzfile = self.generate_fizzfile(sidecar_type)
        instructions = [
            line.strip()
            for line in fizzfile.strip().split("\n")
            if line.strip() and not line.strip().startswith("#")
        ]

        port = self.SIDECAR_PORTS.get(sidecar_type, 8080)
        metadata = ImageMetadata(
            title=f"FizzBuzz Sidecar ({sidecar_type})",
            description=(
                f"Sidecar container for {sidecar_type}, listening on port {port}. "
                f"Runs alongside the main container for cross-cutting concerns."
            ),
            version=FIZZIMAGE_VERSION,
        )

        spec = ImageSpec(
            name=image_name,
            image_type=ImageType.SIDECAR,
            base_image=self._base_image_name,
            dependencies=[self._base_image_name],
            fizzfile_instructions=instructions,
            metadata=metadata,
        )

        try:
            self._catalog.register_image(spec)
        except ImageAlreadyExistsError:
            pass

        manifest = self._catalog.build_image(image_name)

        self._catalog._emit_event(
            FIZZIMAGE_SIDECAR_BUILT,
            {"sidecar_type": sidecar_type, "image": image_name},
        )

        return manifest


# ============================================================
# MultiArchBuilder
# ============================================================


class MultiArchBuilder:
    """Produces OCI image indexes for multi-architecture support.

    Generates manifest lists that map a single image reference
    (e.g., fizzbuzz-eval:1.0.0) to platform-specific manifests
    for linux/amd64, linux/arm64, and fizzbuzz/vm architectures.
    """

    def __init__(
        self,
        supported_platforms: Optional[List[str]] = None,
    ) -> None:
        """Initialize the multi-architecture builder.

        Args:
            supported_platforms: List of supported platform strings.
        """
        self._supported_platforms = supported_platforms or list(SUPPORTED_PLATFORMS)

    @property
    def supported_platforms(self) -> List[str]:
        """Return the list of supported platforms."""
        return list(self._supported_platforms)

    def build_index(
        self,
        image_name: str,
        manifests: Dict[str, ImageManifest],
    ) -> ImageIndex:
        """Build an OCI image index from platform-specific manifests.

        Args:
            image_name: Image name for the index.
            manifests: Platform-to-manifest mapping.

        Returns:
            ImageIndex aggregating all platform manifests.

        Raises:
            MultiArchBuildError: If no manifests are provided.
        """
        if not manifests:
            raise MultiArchBuildError(
                f"No platform manifests provided for '{image_name}'"
            )

        # Compute index digest
        hasher = hashlib.sha256()
        hasher.update(image_name.encode("utf-8"))
        for platform, manifest in sorted(manifests.items()):
            hasher.update(platform.encode("utf-8"))
            hasher.update(manifest.digest.encode("utf-8"))

        index = ImageIndex(
            image_name=image_name,
            digest="sha256:" + hasher.hexdigest(),
            manifests=dict(manifests),
            annotations={
                "org.opencontainers.image.ref.name": image_name,
            },
        )

        logger.info(
            "Multi-arch index built: %s (%d platforms)",
            image_name,
            len(manifests),
        )
        return index

    def resolve_platform(
        self,
        index: ImageIndex,
        platform: str,
    ) -> ImageManifest:
        """Resolve a platform-specific manifest from an index.

        Args:
            index: Image index to resolve from.
            platform: Platform string (e.g., "linux/amd64").

        Returns:
            The platform-specific ImageManifest.

        Raises:
            PlatformResolutionError: If the platform is not found.
        """
        manifest = index.manifests.get(platform)
        if manifest is None:
            raise PlatformResolutionError(
                f"Platform '{platform}' not found in index for "
                f"'{index.image_name}' (available: "
                f"{', '.join(index.manifests.keys())})"
            )
        return manifest

    def list_platforms(self, index: ImageIndex) -> List[str]:
        """List platforms available in an image index.

        Args:
            index: Image index to query.

        Returns:
            List of platform strings.
        """
        return list(index.manifests.keys())

    def _create_platform_descriptor(
        self,
        platform: str,
        manifest: ImageManifest,
    ) -> Dict[str, Any]:
        """Create a platform descriptor entry for an index.

        Args:
            platform: Platform string.
            manifest: Platform-specific manifest.

        Returns:
            OCI descriptor dictionary.
        """
        parts = platform.split("/")
        os_name = parts[0] if len(parts) > 0 else "linux"
        arch = parts[1] if len(parts) > 1 else "amd64"

        return {
            "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "digest": manifest.digest,
            "size": manifest.total_size,
            "platform": {
                "os": os_name,
                "architecture": arch,
            },
        }


# ============================================================
# CatalogScanner
# ============================================================


class CatalogScanner:
    """Vulnerability scanner for the official image catalog.

    Scans each image's layers and dependencies for known
    vulnerabilities.  Assigns severity levels (CRITICAL, HIGH,
    MEDIUM, LOW, NEGLIGIBLE) and blocks images that exceed the
    configured severity threshold from entering the catalog.
    """

    SEVERITY_RANKS = {
        ScanSeverity.CRITICAL: 5,
        ScanSeverity.HIGH: 4,
        ScanSeverity.MEDIUM: 3,
        ScanSeverity.LOW: 2,
        ScanSeverity.NEGLIGIBLE: 1,
    }

    THRESHOLD_MAP = {
        "critical": ScanSeverity.CRITICAL,
        "high": ScanSeverity.HIGH,
        "medium": ScanSeverity.MEDIUM,
        "low": ScanSeverity.LOW,
        "negligible": ScanSeverity.NEGLIGIBLE,
    }

    def __init__(
        self,
        severity_threshold: str = DEFAULT_SCAN_SEVERITY_THRESHOLD,
        vulnerability_db_size: int = DEFAULT_VULN_DB_SIZE,
    ) -> None:
        """Initialize the catalog scanner.

        Args:
            severity_threshold: Maximum severity that blocks admission.
            vulnerability_db_size: Number of entries in the simulated
                vulnerability database.
        """
        self._severity_threshold = self.THRESHOLD_MAP.get(
            severity_threshold, ScanSeverity.CRITICAL
        )
        self._vulnerability_db = self._build_vulnerability_db(vulnerability_db_size)
        self._total_scans = 0

    @property
    def severity_threshold(self) -> ScanSeverity:
        """Return the severity threshold."""
        return self._severity_threshold

    @property
    def total_scans(self) -> int:
        """Return the total number of scans performed."""
        return self._total_scans

    def scan_image(self, manifest: ImageManifest) -> ScanResult:
        """Scan an image for vulnerabilities.

        Args:
            manifest: Image manifest to scan.

        Returns:
            ScanResult with vulnerability findings.
        """
        start = time.monotonic()
        self._total_scans += 1

        vulnerabilities: List[VulnerabilityEntry] = []

        # Check each layer
        for layer in manifest.layers:
            layer_vulns = self._check_layer(layer)
            vulnerabilities.extend(layer_vulns)

        # Check dependencies
        if manifest.metadata and manifest.metadata.dependencies:
            dep_vulns = self._check_dependencies(manifest.metadata.dependencies)
            vulnerabilities.extend(dep_vulns)

        # Count by severity
        counts = {sev: 0 for sev in ScanSeverity}
        for vuln in vulnerabilities:
            counts[vuln.severity] += 1

        duration = (time.monotonic() - start) * 1000

        result = ScanResult(
            image_name=manifest.name,
            image_digest=manifest.digest,
            total_vulnerabilities=len(vulnerabilities),
            critical_count=counts[ScanSeverity.CRITICAL],
            high_count=counts[ScanSeverity.HIGH],
            medium_count=counts[ScanSeverity.MEDIUM],
            low_count=counts[ScanSeverity.LOW],
            negligible_count=counts[ScanSeverity.NEGLIGIBLE],
            admitted=self.is_admissible(None, vulnerabilities),
            vulnerabilities=vulnerabilities,
            scan_duration_ms=duration,
        )

        return result

    def scan_catalog(self, catalog: ImageCatalog) -> List[ScanResult]:
        """Scan all images in a catalog.

        Args:
            catalog: ImageCatalog to scan.

        Returns:
            List of ScanResult objects.
        """
        results = []
        for manifest in catalog.list_images():
            if manifest.build_status == BuildStatus.COMPLETE:
                result = self.scan_image(manifest)
                manifest.scan_result = result
                results.append(result)
        return results

    def is_admissible(
        self,
        result: Optional[ScanResult],
        vulnerabilities: Optional[List[VulnerabilityEntry]] = None,
    ) -> bool:
        """Check whether scan results meet the admission threshold.

        Args:
            result: ScanResult to evaluate (optional if vulnerabilities provided).
            vulnerabilities: Direct vulnerability list (optional).

        Returns:
            True if the image is admissible.
        """
        vulns = vulnerabilities
        if vulns is None and result is not None:
            vulns = result.vulnerabilities
        if not vulns:
            return True

        threshold_rank = self._severity_rank(self._severity_threshold)
        for vuln in vulns:
            if self._severity_rank(vuln.severity) >= threshold_rank:
                return False
        return True

    def generate_report(self, result: ScanResult) -> str:
        """Generate a human-readable vulnerability report.

        Args:
            result: ScanResult to report on.

        Returns:
            Formatted vulnerability report string.
        """
        lines = [
            f"Vulnerability Report: {result.image_name}",
            f"Digest: {result.image_digest}",
            f"Total: {result.total_vulnerabilities}",
            f"  Critical: {result.critical_count}",
            f"  High:     {result.high_count}",
            f"  Medium:   {result.medium_count}",
            f"  Low:      {result.low_count}",
            f"  Negligible: {result.negligible_count}",
            f"Admitted: {'YES' if result.admitted else 'NO'}",
            f"Scan Duration: {result.scan_duration_ms:.1f}ms",
        ]

        if result.vulnerabilities:
            lines.append("")
            lines.append(f"  {'CVE':<20} {'SEVERITY':<12} {'PACKAGE':<20} {'FIXED':<12}")
            lines.append(f"  {'-'*20} {'-'*12} {'-'*20} {'-'*12}")
            for vuln in result.vulnerabilities[:20]:
                lines.append(
                    f"  {vuln.cve_id:<20} {vuln.severity.value:<12} "
                    f"{vuln.package:<20} {vuln.fixed_version or 'N/A':<12}"
                )

        return "\n".join(lines)

    def _check_layer(self, layer: LayerDescriptor) -> List[VulnerabilityEntry]:
        """Check a single layer for vulnerabilities.

        Args:
            layer: Layer to scan.

        Returns:
            List of VulnerabilityEntry objects.
        """
        # Simulate vulnerability detection based on layer digest
        vulns: List[VulnerabilityEntry] = []
        digest_hash = int(hashlib.md5(layer.digest.encode()).hexdigest()[:8], 16)

        # Deterministically select vulnerabilities from the database
        db_size = len(self._vulnerability_db)
        if db_size == 0:
            return vulns

        num_vulns = digest_hash % 4  # 0-3 vulns per layer
        for i in range(num_vulns):
            idx = (digest_hash + i * 7) % db_size
            vulns.append(self._vulnerability_db[idx])

        return vulns

    def _check_dependencies(
        self, dependencies: List[str]
    ) -> List[VulnerabilityEntry]:
        """Check dependencies for vulnerabilities.

        Args:
            dependencies: List of dependency names.

        Returns:
            List of VulnerabilityEntry objects.
        """
        vulns: List[VulnerabilityEntry] = []
        for dep in dependencies:
            dep_hash = int(hashlib.md5(dep.encode()).hexdigest()[:8], 16)
            db_size = len(self._vulnerability_db)
            if db_size == 0:
                continue
            if dep_hash % 5 == 0:  # 20% chance of a vulnerability per dep
                idx = dep_hash % db_size
                vulns.append(self._vulnerability_db[idx])
        return vulns

    def _severity_rank(self, severity: ScanSeverity) -> int:
        """Get the numeric rank of a severity level.

        Args:
            severity: ScanSeverity to rank.

        Returns:
            Integer rank (higher = more severe).
        """
        return self.SEVERITY_RANKS.get(severity, 0)

    @staticmethod
    def _build_vulnerability_db(size: int) -> List[VulnerabilityEntry]:
        """Build a simulated vulnerability database.

        Args:
            size: Number of entries to generate.

        Returns:
            List of VulnerabilityEntry objects.
        """
        rng = random.Random(42)  # Deterministic for reproducibility
        severities = list(ScanSeverity)
        packages = [
            "libfizz", "libbuzz", "fizz-core", "buzz-utils", "libeval",
            "python-fizz", "fizz-crypto", "buzz-net", "fizz-io", "buzz-math",
            "libfizzbuzz", "fizz-parser", "buzz-json", "fizz-xml", "buzz-http",
        ]

        db: List[VulnerabilityEntry] = []
        for i in range(size):
            year = rng.randint(2020, 2026)
            seq = rng.randint(1000, 99999)
            severity = rng.choice(severities)
            package = rng.choice(packages)
            installed = f"{rng.randint(1, 5)}.{rng.randint(0, 20)}.{rng.randint(0, 10)}"
            fixed = (
                f"{rng.randint(1, 5)}.{rng.randint(0, 20)}.{rng.randint(0, 10)}"
                if rng.random() > 0.3
                else ""
            )
            db.append(
                VulnerabilityEntry(
                    cve_id=f"CVE-{year}-{seq}",
                    severity=severity,
                    package=package,
                    installed_version=installed,
                    fixed_version=fixed,
                    description=f"Vulnerability in {package} affecting FizzBuzz evaluation pipeline",
                )
            )
        return db


# ============================================================
# ImageVersioner
# ============================================================


class ImageVersioner:
    """Semantic versioning for the official image catalog.

    Assigns versions to images based on change classification:
    major version increments when the domain layer changes, minor
    version for functionality changes, patch version for
    configuration-only changes.  Manages latest, semver, and
    commit SHA tags.
    """

    def __init__(
        self,
        initial_version: str = DEFAULT_INITIAL_VERSION,
    ) -> None:
        """Initialize the image versioner.

        Args:
            initial_version: Default initial semantic version.
        """
        self._initial_version = initial_version
        self._versions: Dict[str, VersionTag] = {}

    def get_version(self, image_name: str) -> VersionTag:
        """Get the current version for an image.

        Args:
            image_name: Image name.

        Returns:
            Current VersionTag.
        """
        if image_name not in self._versions:
            major, minor, patch = self._parse_version(self._initial_version)
            self._versions[image_name] = VersionTag(
                major=major,
                minor=minor,
                patch=patch,
                tags=[f"{major}.{minor}.{patch}", "latest"],
            )
        return self._versions[image_name]

    def bump_version(
        self,
        image_name: str,
        bump: VersionBump,
    ) -> VersionTag:
        """Bump the version for an image.

        Args:
            image_name: Image name.
            bump: Type of version bump.

        Returns:
            Updated VersionTag.
        """
        current = self.get_version(image_name)

        if bump == VersionBump.MAJOR:
            current.major += 1
            current.minor = 0
            current.patch = 0
        elif bump == VersionBump.MINOR:
            current.minor += 1
            current.patch = 0
        elif bump == VersionBump.PATCH:
            current.patch += 1

        current.tags = [current.semver, "latest"]
        self._versions[image_name] = current
        return current

    def tag_image(
        self,
        image_name: str,
        commit_sha: str = "",
    ) -> List[str]:
        """Assign tags to an image version.

        Args:
            image_name: Image name.
            commit_sha: Git commit SHA for tagging.

        Returns:
            List of assigned tag strings.
        """
        version = self.get_version(image_name)
        tags = [version.semver, "latest"]

        if commit_sha:
            version.commit_sha = commit_sha
            tags.append(f"sha-{commit_sha[:12]}")

        version.tags = tags
        return tags

    def list_tags(self, image_name: str) -> List[str]:
        """List all tags for an image.

        Args:
            image_name: Image name.

        Returns:
            List of tag strings.
        """
        version = self.get_version(image_name)
        return list(version.tags)

    def _parse_version(self, version_str: str) -> Tuple[int, int, int]:
        """Parse a semantic version string.

        Args:
            version_str: Version string (e.g., "1.0.0").

        Returns:
            Tuple of (major, minor, patch).
        """
        parts = version_str.split(".")
        major = int(parts[0]) if len(parts) > 0 else 1
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0
        return major, minor, patch

    def _format_version(self, major: int, minor: int, patch: int) -> str:
        """Format a semantic version string.

        Args:
            major: Major version.
            minor: Minor version.
            patch: Patch version.

        Returns:
            Formatted version string.
        """
        return f"{major}.{minor}.{patch}"


# ============================================================
# FizzImageDashboard
# ============================================================


class FizzImageDashboard:
    """ASCII dashboard for the FizzImage catalog.

    Renders catalog inventory, image details, dependency graphs,
    scan results, and build statistics in formatted ASCII tables.
    """

    def __init__(self, width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        """Initialize the dashboard.

        Args:
            width: Dashboard width in characters.
        """
        self._width = width

    def render(self, catalog: ImageCatalog) -> str:
        """Render the full catalog dashboard.

        Args:
            catalog: ImageCatalog instance.

        Returns:
            Formatted ASCII dashboard string.
        """
        stats = catalog.get_stats()
        border = "+" + "-" * (self._width - 2) + "+"
        lines = [
            border,
            self._center("FIZZIMAGE OFFICIAL IMAGE CATALOG"),
            self._center(f"Version {FIZZIMAGE_VERSION}"),
            border,
            "",
            "  Catalog Overview:",
            f"    Total Images:      {stats.total_images}",
            f"    Base Images:       {stats.base_images}",
            f"    Eval Images:       {stats.eval_images}",
            f"    Subsystem Images:  {stats.subsystem_images}",
            f"    Init Images:       {stats.init_images}",
            f"    Sidecar Images:    {stats.sidecar_images}",
            f"    Composite Images:  {stats.composite_images}",
            "",
            "  Storage:",
            f"    Total Layers:      {stats.total_layers}",
            f"    Total Size:        {self._format_bytes(stats.total_size_bytes)}",
            "",
            "  Scanning:",
            f"    Scans Completed:   {stats.total_scans}",
            f"    Images Admitted:   {stats.images_admitted}",
            f"    Images Blocked:    {stats.images_blocked}",
            f"    Vulnerabilities:   {stats.total_vulnerabilities}",
            "",
            "  Builds:",
            f"    Completed:         {stats.builds_completed}",
            f"    Failed:            {stats.builds_failed}",
            "",
            border,
        ]
        return "\n".join(lines)

    def render_catalog(self, catalog: ImageCatalog) -> str:
        """Render the catalog image listing.

        Args:
            catalog: ImageCatalog instance.

        Returns:
            Formatted image listing string.
        """
        border = "+" + "-" * (self._width - 2) + "+"
        lines = [
            border,
            self._center("IMAGE CATALOG"),
            border,
        ]

        images = catalog.list_images()
        if not images:
            lines.append("  (no images)")
        else:
            lines.append(
                f"  {'NAME':<25} {'TYPE':<12} {'STATUS':<10} {'LAYERS':<8} {'SIZE':<12}"
            )
            lines.append(
                f"  {'-'*25} {'-'*12} {'-'*10} {'-'*8} {'-'*12}"
            )
            for img in images:
                name = img.name[:23]
                img_type = img.image_type.value[:10]
                status = img.build_status.value[:8]
                layers = str(len(img.layers))
                size = self._format_bytes(img.total_size)
                lines.append(
                    f"  {name:<25} {img_type:<12} {status:<10} {layers:<8} {size:<12}"
                )

        lines.append(border)
        return "\n".join(lines)

    def render_image_detail(
        self, catalog: ImageCatalog, image_name: str
    ) -> str:
        """Render detailed information for a single image.

        Args:
            catalog: ImageCatalog instance.
            image_name: Image to inspect.

        Returns:
            Formatted image detail string.
        """
        try:
            details = catalog.inspect_image(image_name)
        except ImageNotFoundError:
            return f"  Image '{image_name}' not found in catalog."

        border = "+" + "-" * (self._width - 2) + "+"
        lines = [
            border,
            self._center(f"IMAGE: {image_name}"),
            border,
            f"  Name:      {details['name']}",
            f"  Digest:    {details.get('digest', 'N/A')}",
            f"  Type:      {details['type']}",
            f"  Status:    {details['status']}",
            f"  Platform:  {details['platform']}",
            f"  Size:      {self._format_bytes(details['total_size'])}",
            f"  Layers:    {details['layer_count']}",
            f"  Created:   {details['created_at']}",
        ]

        if details.get("version"):
            lines.append(f"  Version:   {details['version']}")

        if details.get("tags"):
            lines.append(f"  Tags:      {', '.join(details['tags'])}")

        if details.get("scan"):
            scan = details["scan"]
            lines.append("")
            lines.append("  Scan Results:")
            lines.append(f"    Total:     {scan['total_vulnerabilities']}")
            lines.append(f"    Critical:  {scan['critical']}")
            lines.append(f"    High:      {scan['high']}")
            lines.append(f"    Medium:    {scan['medium']}")
            lines.append(f"    Low:       {scan['low']}")
            lines.append(f"    Admitted:  {'YES' if scan['admitted'] else 'NO'}")

        if details.get("layers"):
            lines.append("")
            lines.append("  Layers:")
            for i, layer in enumerate(details["layers"]):
                lines.append(
                    f"    [{i}] {layer['digest'][:20]}... "
                    f"({self._format_bytes(layer['size'])})"
                )

        lines.append(border)
        return "\n".join(lines)

    def render_dependencies(
        self, catalog: ImageCatalog, image_name: str
    ) -> str:
        """Render the dependency graph for an image.

        Args:
            catalog: ImageCatalog instance.
            image_name: Image to show dependencies for.

        Returns:
            Formatted dependency graph string.
        """
        try:
            deps = catalog.get_dependencies(image_name)
        except ImageNotFoundError:
            return f"  Image '{image_name}' not found in catalog."

        border = "+" + "-" * (self._width - 2) + "+"
        lines = [
            border,
            self._center(f"DEPENDENCIES: {image_name}"),
            border,
            f"  {image_name}",
        ]

        if deps:
            for i, dep in enumerate(deps):
                prefix = "  +-- " if i < len(deps) - 1 else "  \\-- "
                lines.append(prefix + dep)
        else:
            lines.append("  (no dependencies)")

        lines.append(border)
        return "\n".join(lines)

    def render_scan_results(self, catalog: ImageCatalog) -> str:
        """Render vulnerability scan results for all images.

        Args:
            catalog: ImageCatalog instance.

        Returns:
            Formatted scan results string.
        """
        border = "+" + "-" * (self._width - 2) + "+"
        lines = [
            border,
            self._center("VULNERABILITY SCAN RESULTS"),
            border,
        ]

        images = catalog.list_images()
        scanned = [img for img in images if img.scan_result is not None]

        if not scanned:
            lines.append("  (no scan results)")
        else:
            lines.append(
                f"  {'IMAGE':<25} {'TOTAL':<8} {'CRIT':<6} {'HIGH':<6} {'ADMITTED':<10}"
            )
            lines.append(
                f"  {'-'*25} {'-'*8} {'-'*6} {'-'*6} {'-'*10}"
            )
            for img in scanned:
                sr = img.scan_result
                name = img.name[:23]
                admitted = "YES" if sr.admitted else "NO"
                lines.append(
                    f"  {name:<25} {sr.total_vulnerabilities:<8} "
                    f"{sr.critical_count:<6} {sr.high_count:<6} {admitted:<10}"
                )

        lines.append(border)
        return "\n".join(lines)

    def render_build_history(self, catalog: ImageCatalog) -> str:
        """Render the build history for the catalog.

        Args:
            catalog: ImageCatalog instance.

        Returns:
            Formatted build history string.
        """
        border = "+" + "-" * (self._width - 2) + "+"
        lines = [
            border,
            self._center("BUILD HISTORY"),
            border,
        ]

        images = catalog.list_images()
        built = [
            img
            for img in images
            if img.build_status in (BuildStatus.COMPLETE, BuildStatus.FAILED)
        ]

        if not built:
            lines.append("  (no builds)")
        else:
            lines.append(
                f"  {'IMAGE':<25} {'STATUS':<10} {'LAYERS':<8} {'SIZE':<12}"
            )
            lines.append(
                f"  {'-'*25} {'-'*10} {'-'*8} {'-'*12}"
            )
            for img in built:
                name = img.name[:23]
                status = img.build_status.value
                layers = str(len(img.layers))
                size = self._format_bytes(img.total_size)
                lines.append(
                    f"  {name:<25} {status:<10} {layers:<8} {size:<12}"
                )

        lines.append(border)
        return "\n".join(lines)

    def _center(self, text: str) -> str:
        """Center text within the dashboard width."""
        pad = (self._width - len(text)) // 2
        return " " * max(0, pad) + text

    @staticmethod
    def _format_bytes(size: int) -> str:
        """Format bytes with appropriate unit."""
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.1f} GB"

    @staticmethod
    def _format_severity(severity: ScanSeverity) -> str:
        """Format a severity level for display."""
        return severity.value.upper()


# ============================================================
# FizzImageMiddleware
# ============================================================


class FizzImageMiddleware(IMiddleware):
    """Middleware that annotates evaluations with image catalog metadata.

    For each FizzBuzz evaluation, resolves which catalog image would
    serve the evaluation based on the active configuration, and
    enriches the processing context with image reference, version,
    and dependency information.
    """

    def __init__(
        self,
        catalog: ImageCatalog,
        dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
        enable_dashboard: bool = False,
    ) -> None:
        """Initialize the middleware.

        Args:
            catalog: ImageCatalog instance.
            dashboard_width: ASCII dashboard width.
            enable_dashboard: Whether to enable dashboard rendering.
        """
        self._catalog = catalog
        self._dashboard = FizzImageDashboard(width=dashboard_width)
        self._enable_dashboard = enable_dashboard
        self._evaluation_count = 0
        self._errors = 0

    def get_name(self) -> str:
        """Return the middleware name."""
        return "FizzImageMiddleware"

    def get_priority(self) -> int:
        """Return the middleware priority."""
        return MIDDLEWARE_PRIORITY

    @property
    def priority(self) -> int:
        """Return middleware priority (113)."""
        return MIDDLEWARE_PRIORITY

    @property
    def name(self) -> str:
        """Return the middleware name (convenience property)."""
        return "FizzImageMiddleware"

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process a FizzBuzz evaluation through the image catalog middleware.

        Resolves the active evaluation image, enriches the context
        with image metadata, and delegates to the next handler.

        Args:
            context: Processing context.
            next_handler: Next middleware in the pipeline.

        Returns:
            The processed context.

        Raises:
            FizzImageMiddlewareError: If image resolution fails.
        """
        self._evaluation_count += 1
        number = context.number if hasattr(context, "number") else 0

        try:
            # Resolve the evaluation image
            eval_image_name = "fizzbuzz-eval-standard"
            images = self._catalog.list_images()
            eval_images = [
                img
                for img in images
                if img.image_type == ImageType.EVAL
                and img.build_status == BuildStatus.COMPLETE
            ]

            if eval_images:
                resolved = eval_images[0]
                eval_image_name = resolved.name
            else:
                resolved = None

            # Enrich context metadata
            if hasattr(context, "metadata") and isinstance(context.metadata, dict):
                context.metadata["fizzimage_image"] = eval_image_name
                context.metadata["fizzimage_version"] = FIZZIMAGE_VERSION
                if resolved:
                    context.metadata["fizzimage_digest"] = resolved.digest
                    context.metadata["fizzimage_layers"] = len(resolved.layers)
                    context.metadata["fizzimage_size"] = resolved.total_size

            # Delegate to next handler
            return next_handler(context)

        except FizzImageError:
            self._errors += 1
            raise
        except Exception as exc:
            self._errors += 1
            raise FizzImageMiddlewareError(
                evaluation_number=number,
                reason=str(exc),
            ) from exc

    def render_dashboard(self) -> str:
        """Render the catalog dashboard.

        Returns:
            ASCII dashboard string.
        """
        return self._dashboard.render(self._catalog)

    def render_catalog(self) -> str:
        """Render the catalog image listing.

        Returns:
            ASCII catalog listing string.
        """
        return self._dashboard.render_catalog(self._catalog)

    def render_image_detail(self, image_name: str) -> str:
        """Render detailed information for an image.

        Args:
            image_name: Image to inspect.

        Returns:
            ASCII image detail string.
        """
        return self._dashboard.render_image_detail(self._catalog, image_name)

    def render_dependencies(self, image_name: str) -> str:
        """Render the dependency graph for an image.

        Args:
            image_name: Image to show dependencies for.

        Returns:
            ASCII dependency graph string.
        """
        return self._dashboard.render_dependencies(self._catalog, image_name)

    def render_scan_results(self) -> str:
        """Render vulnerability scan results.

        Returns:
            ASCII scan results string.
        """
        return self._dashboard.render_scan_results(self._catalog)

    def render_stats(self) -> str:
        """Render aggregate statistics.

        Returns:
            Formatted statistics string.
        """
        stats = self._catalog.get_stats()
        lines = [
            "  FizzImage Statistics:",
            f"    Evaluations:       {self._evaluation_count}",
            f"    Total Images:      {stats.total_images}",
            f"    Total Layers:      {stats.total_layers}",
            f"    Total Size:        {self._dashboard._format_bytes(stats.total_size_bytes)}",
            f"    Scans Completed:   {stats.total_scans}",
            f"    Images Admitted:   {stats.images_admitted}",
            f"    Builds Completed:  {stats.builds_completed}",
            f"    Builds Failed:     {stats.builds_failed}",
            f"    Errors:            {self._errors}",
        ]
        return "\n".join(lines)


# ============================================================
# Factory
# ============================================================


def create_fizzimage_subsystem(
    registry_url: str = DEFAULT_REGISTRY_URL,
    base_image_name: str = DEFAULT_BASE_IMAGE,
    scan_severity_threshold: str = DEFAULT_SCAN_SEVERITY_THRESHOLD,
    max_catalog_size: int = DEFAULT_MAX_CATALOG_SIZE,
    python_version: str = DEFAULT_PYTHON_VERSION,
    initial_version: str = DEFAULT_INITIAL_VERSION,
    vuln_db_size: int = DEFAULT_VULN_DB_SIZE,
    module_base_path: str = DEFAULT_MODULE_BASE_PATH,
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
    enable_dashboard: bool = False,
    event_bus: Optional[Any] = None,
) -> Tuple[ImageCatalog, FizzImageMiddleware]:
    """Create and wire the complete FizzImage subsystem.

    Factory function that instantiates the image catalog with all
    builders (base, eval, subsystem, init, sidecar), scanner,
    versioner, multi-arch builder, and the middleware, ready for
    integration into the FizzBuzz evaluation pipeline.

    Instantiation order:
    1. ImageCatalog
    2. CatalogScanner
    3. ImageVersioner
    4. MultiArchBuilder
    5. BaseImageBuilder
    6. EvalImageBuilder
    7. SubsystemImageGenerator
    8. InitContainerBuilder
    9. SidecarImageBuilder
    10. FizzImageDashboard
    11. FizzImageMiddleware

    The factory populates the catalog with all official image
    specifications (base image, four eval profiles, init containers,
    sidecars) and returns the catalog and middleware tuple.

    Args:
        registry_url: Registry URL for image push/pull.
        base_image_name: Foundation base image name.
        scan_severity_threshold: Maximum vulnerability severity.
        max_catalog_size: Maximum catalog capacity.
        python_version: Python version for the base image.
        initial_version: Initial semantic version.
        vuln_db_size: Vulnerability database entries.
        module_base_path: Base package path for infrastructure.
        dashboard_width: ASCII dashboard width.
        enable_dashboard: Whether to enable dashboard rendering.
        event_bus: Optional event bus for lifecycle events.

    Returns:
        Tuple of (ImageCatalog, FizzImageMiddleware).
    """
    # 1. ImageCatalog
    catalog = ImageCatalog(
        registry_url=registry_url,
        base_image_name=base_image_name,
        scan_severity_threshold=scan_severity_threshold,
        max_catalog_size=max_catalog_size,
        event_bus=event_bus,
    )

    # 2. CatalogScanner
    scanner = CatalogScanner(
        severity_threshold=scan_severity_threshold,
        vulnerability_db_size=vuln_db_size,
    )

    # 3. ImageVersioner
    versioner = ImageVersioner(
        initial_version=initial_version,
    )

    # 4. MultiArchBuilder
    multi_arch = MultiArchBuilder()

    # 5. BaseImageBuilder
    base_builder = BaseImageBuilder(
        catalog=catalog,
        base_image_name=base_image_name,
        python_version=python_version,
    )

    # 6. EvalImageBuilder
    eval_builder = EvalImageBuilder(
        catalog=catalog,
        base_builder=base_builder,
    )

    # 7. SubsystemImageGenerator
    subsystem_gen = SubsystemImageGenerator(
        catalog=catalog,
        base_image_name=base_image_name,
        module_base_path=module_base_path,
    )

    # 8. InitContainerBuilder
    init_builder = InitContainerBuilder(
        catalog=catalog,
        base_image_name=base_image_name,
    )

    # 9. SidecarImageBuilder
    sidecar_builder = SidecarImageBuilder(
        catalog=catalog,
        base_image_name=base_image_name,
    )

    # 10. FizzImageDashboard
    dashboard = FizzImageDashboard(width=dashboard_width)

    # 11. FizzImageMiddleware
    middleware = FizzImageMiddleware(
        catalog=catalog,
        dashboard_width=dashboard_width,
        enable_dashboard=enable_dashboard,
    )

    # Build the base image
    base_builder.build()

    # Register official image specs for eval profiles
    for profile in ImageProfile:
        eval_image_name = f"fizzbuzz-eval-{profile.value}"
        fizzfile = eval_builder.generate_fizzfile(profile)
        instructions = [
            line.strip()
            for line in fizzfile.strip().split("\n")
            if line.strip() and not line.strip().startswith("#")
        ]

        metadata = ImageMetadata(
            title=f"FizzBuzz Eval Image ({profile.value})",
            description=(
                f"Evaluation runtime image for the {profile.value} profile."
            ),
            version=initial_version,
            layer="application",
        )

        spec = ImageSpec(
            name=eval_image_name,
            image_type=ImageType.EVAL,
            base_image=base_image_name,
            dependencies=[base_image_name],
            fizzfile_instructions=instructions,
            metadata=metadata,
            profile=profile,
        )
        try:
            catalog.register_image(spec)
        except ImageAlreadyExistsError:
            pass

    # Register init container specs
    for init_type in InitContainerBuilder.INIT_TYPES:
        init_image_name = f"fizzbuzz-init-{init_type}"
        fizzfile = init_builder.generate_fizzfile(init_type)
        instructions = [
            line.strip()
            for line in fizzfile.strip().split("\n")
            if line.strip() and not line.strip().startswith("#")
        ]

        metadata = ImageMetadata(
            title=f"FizzBuzz Init Container ({init_type})",
            description=f"Init container for {init_type} pre-flight setup.",
            version=initial_version,
        )

        spec = ImageSpec(
            name=init_image_name,
            image_type=ImageType.INIT,
            base_image=base_image_name,
            dependencies=[base_image_name],
            fizzfile_instructions=instructions,
            metadata=metadata,
        )
        try:
            catalog.register_image(spec)
        except ImageAlreadyExistsError:
            pass

    # Register sidecar specs
    for sidecar_type in SidecarImageBuilder.SIDECAR_TYPES:
        sidecar_image_name = f"fizzbuzz-sidecar-{sidecar_type}"
        fizzfile = sidecar_builder.generate_fizzfile(sidecar_type)
        instructions = [
            line.strip()
            for line in fizzfile.strip().split("\n")
            if line.strip() and not line.strip().startswith("#")
        ]

        metadata = ImageMetadata(
            title=f"FizzBuzz Sidecar ({sidecar_type})",
            description=f"Sidecar container for {sidecar_type}.",
            version=initial_version,
        )

        spec = ImageSpec(
            name=sidecar_image_name,
            image_type=ImageType.SIDECAR,
            base_image=base_image_name,
            dependencies=[base_image_name],
            fizzfile_instructions=instructions,
            metadata=metadata,
        )
        try:
            catalog.register_image(spec)
        except ImageAlreadyExistsError:
            pass

    catalog._emit_event(
        FIZZIMAGE_CATALOG_LOADED,
        {"total_images": len(catalog.list_images())},
    )

    logger.info("FizzImage subsystem created and wired")

    return catalog, middleware
