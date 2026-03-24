"""
Enterprise FizzBuzz Platform - FizzRegistry: OCI Distribution-Compliant Image Registry

A complete OCI Distribution-compliant image registry with push, pull,
tag, and catalog APIs, backed by content-addressable blob storage and
manifest management.  Alongside the registry, a FizzFile DSL -- the
platform's Dockerfile equivalent -- defines a build language with
instructions specific to FizzBuzz containers.

The implementation follows the OCI Distribution Specification (v1.0.0):
clients upload blobs by digest, then upload manifests referencing those
digests.  Pulling an image is the reverse: fetch the manifest, then
fetch each referenced blob.  Content-addressable storage ensures
deduplication, integrity verification, and efficient distribution.

OCI Distribution Specification: https://github.com/opencontainers/distribution-spec
OCI Image Specification: https://github.com/opencontainers/image-spec
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import io
import logging
import math
import os
import re
import struct
import threading
import time
import uuid
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from enterprise_fizzbuzz.domain.exceptions import (
    BlobCorruptionError,
    BlobNotFoundError,
    BlobStoreFullError,
    FizzFileParseError,
    FizzFileMissingFromError,
    GarbageCollectionError,
    ImageBuildError,
    ImageSignatureError,
    LayerCacheMissError,
    ManifestExistsError,
    ManifestNotFoundError,
    ManifestValidationError,
    RegistryDashboardError,
    RegistryError,
    RegistryMiddlewareError,
    RepositoryLimitError,
    RepositoryNotFoundError,
    TagLimitError,
    TagNotFoundError,
    VulnerabilityScanError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzResult,
    ProcessingContext,
)

logger = logging.getLogger("enterprise_fizzbuzz.fizzregistry")


# ============================================================
# Constants
# ============================================================

OCI_MANIFEST_MEDIA_TYPE = "application/vnd.oci.image.manifest.v1+json"
"""OCI image manifest media type per the OCI image spec."""

OCI_INDEX_MEDIA_TYPE = "application/vnd.oci.image.index.v1+json"
"""OCI image index (multi-arch manifest list) media type."""

OCI_CONFIG_MEDIA_TYPE = "application/vnd.oci.image.config.v1+json"
"""OCI image configuration media type."""

OCI_LAYER_MEDIA_TYPE = "application/vnd.oci.image.layer.v1.tar"
"""OCI uncompressed layer media type."""

OCI_LAYER_GZIP_MEDIA_TYPE = "application/vnd.oci.image.layer.v1.tar+gzip"
"""OCI gzip-compressed layer media type."""

OCI_SIGNATURE_MEDIA_TYPE = "application/vnd.dev.cosign.simplesigning.v1+json"
"""Cosign-style image signature media type."""

DEFAULT_MAX_BLOBS = 4096
"""Default maximum number of blobs in the blob store."""

DEFAULT_MAX_REPOS = 256
"""Default maximum number of repositories in the registry."""

DEFAULT_MAX_TAGS = 1024
"""Default maximum number of tags per repository."""

DEFAULT_GC_GRACE_PERIOD = 86400.0
"""Default garbage collection grace period in seconds (24 hours)."""

DEFAULT_DASHBOARD_WIDTH = 72
"""Default width for ASCII dashboard rendering."""

MIDDLEWARE_PRIORITY = 110
"""Middleware pipeline priority for the registry middleware."""

DIGEST_ALGORITHM = "sha256"
"""Digest algorithm used for content addressing."""

DIGEST_PREFIX = "sha256:"
"""Prefix for SHA-256 digest strings."""

SCRATCH_IMAGE = "scratch"
"""Special base image name indicating an empty base layer."""

FIZZFILE_COMMENT = "#"
"""Comment character in FizzFile syntax."""

FIZZFILE_CONTINUATION = "\\"
"""Line continuation character in FizzFile syntax."""

DEFAULT_BUILD_TAG = "latest"
"""Default tag for built images when no tag is specified."""

SCHEMA_VERSION = 2
"""OCI manifest schema version."""

MAX_INSTRUCTION_CACHE_SIZE = 512
"""Maximum entries in the image builder instruction cache."""


# ============================================================
# Enums
# ============================================================


class ManifestSchemaVersion(Enum):
    """OCI manifest schema versions.

    The OCI image specification defines schema version 2 as the
    current standard.  Schema version 1 is retained for backward
    compatibility with Docker Image Manifest V2, Schema 1.
    """

    V1 = 1
    V2 = 2


class ImagePlatformOS(Enum):
    """Operating system identifiers for multi-architecture image indexes.

    Each manifest in an OCI image index specifies the operating
    system it targets.  The registry resolves the correct manifest
    for the requesting client's platform.
    """

    LINUX = "linux"
    WINDOWS = "windows"
    DARWIN = "darwin"
    FREEBSD = "freebsd"
    FIZZBUZZ_OS = "fizzbuzz-os"


class ImagePlatformArch(Enum):
    """CPU architecture identifiers for multi-architecture image indexes.

    Each manifest in an OCI image index specifies the CPU
    architecture it targets.  Combined with the OS, this enables
    platform-specific image resolution.
    """

    AMD64 = "amd64"
    ARM64 = "arm64"
    ARM = "arm"
    PPC64LE = "ppc64le"
    S390X = "s390x"
    FIZZ_ARCH = "fizz-arch"


class TagState(Enum):
    """Lifecycle states for image tags in a repository.

    Tags are mutable references to manifest digests.  A tag
    transitions through these states during its lifecycle.
    """

    ACTIVE = auto()
    DEPRECATED = auto()
    DELETED = auto()


class GCPhase(Enum):
    """Phases of the mark-and-sweep garbage collection algorithm.

    The garbage collector operates in two distinct phases: MARK
    traverses all manifests to identify referenced blobs, and
    SWEEP removes all unreferenced blobs that have exceeded
    the grace period.
    """

    IDLE = auto()
    MARK = auto()
    SWEEP = auto()
    COMPLETE = auto()


class SignatureStatus(Enum):
    """Verification status for image signatures.

    Image signatures attest to the provenance and integrity of
    a manifest.  The verification process yields one of these
    statuses.
    """

    UNSIGNED = auto()
    SIGNED = auto()
    VERIFIED = auto()
    INVALID = auto()
    EXPIRED = auto()


class VulnerabilitySeverity(Enum):
    """Severity classification for vulnerability findings.

    Vulnerabilities discovered during image scanning are
    classified according to their potential impact on the
    FizzBuzz evaluation pipeline.
    """

    CRITICAL = auto()
    HIGH = auto()
    MEDIUM = auto()
    LOW = auto()
    NEGLIGIBLE = auto()
    UNKNOWN = auto()


class FizzFileInstruction(Enum):
    """Instruction types supported by the FizzFile build DSL.

    FizzFile is the platform's Dockerfile equivalent, providing
    a declarative build language for FizzBuzz container images.
    """

    FROM = "FROM"
    FIZZ = "FIZZ"
    BUZZ = "BUZZ"
    RUN = "RUN"
    COPY = "COPY"
    ENV = "ENV"
    ENTRYPOINT = "ENTRYPOINT"
    LABEL = "LABEL"


class BuildPhase(Enum):
    """Phases of the image build lifecycle.

    The image builder processes FizzFile instructions through
    these phases to produce a complete OCI image.
    """

    INITIALIZING = auto()
    PARSING = auto()
    RESOLVING_BASE = auto()
    EXECUTING = auto()
    COMMITTING = auto()
    PUSHING = auto()
    COMPLETE = auto()
    FAILED = auto()


class RegistryOperation(Enum):
    """Registry API operation types for metrics and auditing.

    Every registry API call is classified by operation type to
    enable request counting, latency tracking, and audit logging.
    """

    BLOB_HEAD = auto()
    BLOB_GET = auto()
    BLOB_PUT = auto()
    BLOB_DELETE = auto()
    MANIFEST_GET = auto()
    MANIFEST_PUT = auto()
    MANIFEST_DELETE = auto()
    MANIFEST_HEAD = auto()
    TAG_LIST = auto()
    CATALOG = auto()


# ============================================================
# Dataclasses
# ============================================================


@dataclass
class OCIDescriptor:
    """Content descriptor per the OCI image specification.

    A descriptor identifies a piece of content by its media type,
    digest, and size.  Descriptors are the building blocks of
    manifests: they point to config blobs and layer blobs without
    embedding the content directly.

    Attributes:
        media_type: IANA media type of the referenced content.
        digest: SHA-256 digest of the content in 'sha256:<hex>' format.
        size: Size of the content in bytes.
        annotations: Optional key-value metadata annotations.
        platform: Optional platform specification for image indexes.
    """

    media_type: str
    digest: str
    size: int
    annotations: Dict[str, str] = field(default_factory=dict)
    platform: Optional[OCIPlatform] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to OCI-compliant dictionary."""
        result: Dict[str, Any] = {
            "mediaType": self.media_type,
            "digest": self.digest,
            "size": self.size,
        }
        if self.annotations:
            result["annotations"] = dict(self.annotations)
        if self.platform is not None:
            result["platform"] = self.platform.to_dict()
        return result


@dataclass
class OCIPlatform:
    """Platform specification for multi-architecture image indexes.

    Identifies the OS and architecture combination that a
    manifest targets, enabling the registry to serve the correct
    image variant for each client platform.

    Attributes:
        os: Operating system (e.g., 'linux', 'fizzbuzz-os').
        architecture: CPU architecture (e.g., 'amd64', 'fizz-arch').
        variant: Optional architecture variant (e.g., 'v8' for arm64).
        os_version: Optional OS version string.
        os_features: Optional list of required OS features.
    """

    os: str = "fizzbuzz-os"
    architecture: str = "fizz-arch"
    variant: str = ""
    os_version: str = ""
    os_features: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to OCI-compliant dictionary."""
        result: Dict[str, Any] = {
            "os": self.os,
            "architecture": self.architecture,
        }
        if self.variant:
            result["variant"] = self.variant
        if self.os_version:
            result["os.version"] = self.os_version
        if self.os_features:
            result["os.features"] = list(self.os_features)
        return result


@dataclass
class OCIManifest:
    """OCI image manifest describing a single image.

    An OCI manifest references a config blob (containing runtime
    configuration) and an ordered list of layer blobs (containing
    filesystem content).  Together, these define a complete
    container image.

    Attributes:
        schema_version: OCI manifest schema version (always 2).
        media_type: Manifest media type.
        config: Descriptor pointing to the image config blob.
        layers: Ordered list of descriptors pointing to layer blobs.
        annotations: Optional manifest-level annotations.
    """

    schema_version: int = SCHEMA_VERSION
    media_type: str = OCI_MANIFEST_MEDIA_TYPE
    config: Optional[OCIDescriptor] = None
    layers: List[OCIDescriptor] = field(default_factory=list)
    annotations: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to OCI-compliant dictionary."""
        result: Dict[str, Any] = {
            "schemaVersion": self.schema_version,
            "mediaType": self.media_type,
        }
        if self.config is not None:
            result["config"] = self.config.to_dict()
        result["layers"] = [layer.to_dict() for layer in self.layers]
        if self.annotations:
            result["annotations"] = dict(self.annotations)
        return result

    def compute_digest(self) -> str:
        """Compute the SHA-256 digest of the manifest content."""
        import json
        content = json.dumps(self.to_dict(), sort_keys=True).encode("utf-8")
        return DIGEST_PREFIX + hashlib.sha256(content).hexdigest()

    @property
    def total_size(self) -> int:
        """Total size of all referenced blobs."""
        config_size = self.config.size if self.config else 0
        return config_size + sum(layer.size for layer in self.layers)


@dataclass
class OCIImageIndex:
    """OCI image index (multi-architecture manifest list).

    An image index contains a list of manifest descriptors, each
    targeting a specific platform.  When a client pulls an image
    by tag, the registry returns the index, and the client selects
    the manifest matching its platform.

    Attributes:
        schema_version: OCI schema version (always 2).
        media_type: Image index media type.
        manifests: List of manifest descriptors with platform info.
        annotations: Optional index-level annotations.
    """

    schema_version: int = SCHEMA_VERSION
    media_type: str = OCI_INDEX_MEDIA_TYPE
    manifests: List[OCIDescriptor] = field(default_factory=list)
    annotations: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to OCI-compliant dictionary."""
        return {
            "schemaVersion": self.schema_version,
            "mediaType": self.media_type,
            "manifests": [m.to_dict() for m in self.manifests],
            "annotations": dict(self.annotations) if self.annotations else {},
        }


@dataclass
class RootFS:
    """Root filesystem specification for an OCI image config.

    Identifies the layer diff_ids that compose the container's
    root filesystem.  The runtime uses this to verify that all
    required layers are present before starting the container.

    Attributes:
        type: Filesystem type (always 'layers').
        diff_ids: Ordered list of layer diff_id digests.
    """

    type: str = "layers"
    diff_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to OCI-compliant dictionary."""
        return {
            "type": self.type,
            "diff_ids": list(self.diff_ids),
        }


@dataclass
class HistoryEntry:
    """Build history entry for an OCI image config.

    Records the instruction that produced each layer in the
    image, enabling build reproducibility analysis and layer
    provenance tracking.

    Attributes:
        created: Timestamp when the layer was created.
        created_by: The instruction that produced the layer.
        empty_layer: Whether this instruction produced no layer.
        comment: Optional human-readable comment.
    """

    created: str = ""
    created_by: str = ""
    empty_layer: bool = False
    comment: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to OCI-compliant dictionary."""
        result: Dict[str, Any] = {}
        if self.created:
            result["created"] = self.created
        if self.created_by:
            result["created_by"] = self.created_by
        if self.empty_layer:
            result["empty_layer"] = True
        if self.comment:
            result["comment"] = self.comment
        return result


@dataclass
class ContainerConfig:
    """Default container configuration for an OCI image.

    Specifies the default runtime parameters for containers
    created from this image: entrypoint, command arguments,
    environment variables, working directory, and exposed ports.

    Attributes:
        entrypoint: Default entrypoint command.
        cmd: Default command arguments.
        env: Environment variables as KEY=VALUE strings.
        working_dir: Default working directory path.
        exposed_ports: Ports the container listens on.
        volumes: Declared volume mount points.
        labels: Image metadata labels.
        user: Default user for the container process.
    """

    entrypoint: List[str] = field(default_factory=list)
    cmd: List[str] = field(default_factory=list)
    env: List[str] = field(default_factory=list)
    working_dir: str = "/"
    exposed_ports: Dict[str, Any] = field(default_factory=dict)
    volumes: Dict[str, Any] = field(default_factory=dict)
    labels: Dict[str, str] = field(default_factory=dict)
    user: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to OCI-compliant dictionary."""
        result: Dict[str, Any] = {}
        if self.entrypoint:
            result["Entrypoint"] = list(self.entrypoint)
        if self.cmd:
            result["Cmd"] = list(self.cmd)
        if self.env:
            result["Env"] = list(self.env)
        if self.working_dir:
            result["WorkingDir"] = self.working_dir
        if self.exposed_ports:
            result["ExposedPorts"] = dict(self.exposed_ports)
        if self.volumes:
            result["Volumes"] = dict(self.volumes)
        if self.labels:
            result["Labels"] = dict(self.labels)
        if self.user:
            result["User"] = self.user
        return result


@dataclass
class OCIImageConfig:
    """OCI image configuration blob.

    Contains the runtime configuration for containers created
    from this image, the root filesystem layer references, and
    the build history.  This blob is stored in the blob store
    and referenced by the manifest's config descriptor.

    Attributes:
        architecture: Target CPU architecture.
        os: Target operating system.
        rootfs: Root filesystem layer references.
        history: Build history entries.
        config: Default container configuration.
        created: Image creation timestamp.
        author: Image author.
    """

    architecture: str = "fizz-arch"
    os: str = "fizzbuzz-os"
    rootfs: RootFS = field(default_factory=RootFS)
    history: List[HistoryEntry] = field(default_factory=list)
    config: ContainerConfig = field(default_factory=ContainerConfig)
    created: str = ""
    author: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to OCI-compliant dictionary."""
        result: Dict[str, Any] = {
            "architecture": self.architecture,
            "os": self.os,
            "rootfs": self.rootfs.to_dict(),
        }
        if self.history:
            result["history"] = [h.to_dict() for h in self.history]
        if self.config:
            result["config"] = self.config.to_dict()
        if self.created:
            result["created"] = self.created
        if self.author:
            result["author"] = self.author
        return result

    def compute_digest(self) -> str:
        """Compute the SHA-256 digest of the config content."""
        import json
        content = json.dumps(self.to_dict(), sort_keys=True).encode("utf-8")
        return DIGEST_PREFIX + hashlib.sha256(content).hexdigest()

    def serialize(self) -> bytes:
        """Serialize the config to JSON bytes."""
        import json
        return json.dumps(self.to_dict(), sort_keys=True).encode("utf-8")


@dataclass
class TagReference:
    """A tag referencing a manifest digest within a repository.

    Tags are mutable pointers that give human-readable names to
    manifest digests.  A tag's history tracks all digests it has
    pointed to over time.

    Attributes:
        name: Tag name (e.g., 'latest', 'v1.0.0').
        digest: Current manifest digest the tag points to.
        state: Current lifecycle state of the tag.
        created_at: When the tag was first created.
        updated_at: When the tag was last updated.
        history: List of (digest, timestamp) tuples for all
            previous values of this tag.
    """

    name: str = ""
    digest: str = ""
    state: TagState = TagState.ACTIVE
    created_at: float = 0.0
    updated_at: float = 0.0
    history: List[Tuple[str, float]] = field(default_factory=list)


@dataclass
class FizzFileStep:
    """A parsed instruction from a FizzFile build script.

    Each step represents a single build instruction with its
    arguments, ready for execution by the image builder.

    Attributes:
        instruction: The instruction type (FROM, FIZZ, BUZZ, etc.).
        arguments: The instruction arguments as a raw string.
        line_number: Source line number in the FizzFile.
        original_line: The original unparsed line from the FizzFile.
    """

    instruction: FizzFileInstruction = FizzFileInstruction.FROM
    arguments: str = ""
    line_number: int = 0
    original_line: str = ""


@dataclass
class BuildContext:
    """Context for an image build operation.

    Contains the state accumulated during FizzFile execution,
    including the base image reference, accumulated layers,
    environment variables, and build metadata.

    Attributes:
        base_image: The base image reference from the FROM instruction.
        steps: Parsed FizzFile steps to execute.
        layers: Layer digests accumulated during the build.
        env_vars: Environment variables set by ENV instructions.
        labels: Metadata labels set by LABEL instructions.
        entrypoint: Entrypoint command set by ENTRYPOINT instruction.
        fizz_rules: Fizz rules added by FIZZ instructions.
        buzz_rules: Buzz rules added by BUZZ instructions.
        build_id: Unique identifier for this build.
        phase: Current build phase.
        started_at: Build start timestamp.
        completed_at: Build completion timestamp.
    """

    base_image: str = SCRATCH_IMAGE
    steps: List[FizzFileStep] = field(default_factory=list)
    layers: List[str] = field(default_factory=list)
    env_vars: Dict[str, str] = field(default_factory=dict)
    labels: Dict[str, str] = field(default_factory=dict)
    entrypoint: List[str] = field(default_factory=list)
    fizz_rules: List[Tuple[int, str]] = field(default_factory=list)
    buzz_rules: List[Tuple[int, str]] = field(default_factory=list)
    build_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    phase: BuildPhase = BuildPhase.INITIALIZING
    started_at: float = 0.0
    completed_at: float = 0.0


@dataclass
class ImageSignature:
    """Cosign-style image signature.

    An ECDSA-P256 signature attesting to the integrity and
    provenance of a manifest digest.  Signatures are stored
    as OCI artifacts linked to the signed image.

    Attributes:
        signature_id: Unique identifier for this signature.
        manifest_digest: The digest of the signed manifest.
        signature: The HMAC-SHA256 signature bytes (hex-encoded).
        key_id: Identifier of the signing key.
        signer: Identity of the signer.
        signed_at: Timestamp when the signature was created.
        status: Current verification status.
    """

    signature_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    manifest_digest: str = ""
    signature: str = ""
    key_id: str = ""
    signer: str = "Bob McFizzington"
    signed_at: float = 0.0
    status: SignatureStatus = SignatureStatus.UNSIGNED


@dataclass
class VulnerabilityFinding:
    """A single vulnerability finding from an image scan.

    Represents a known vulnerability (CVE) found in an image
    layer, classified by severity with remediation guidance.

    Attributes:
        cve_id: CVE identifier (e.g., 'CVE-2026-FIZZ-001').
        severity: Severity classification.
        package: Affected package name.
        version: Affected version.
        fixed_version: Version that fixes the vulnerability (if known).
        description: Human-readable description.
        layer_digest: Digest of the layer containing the vulnerability.
    """

    cve_id: str = ""
    severity: VulnerabilitySeverity = VulnerabilitySeverity.UNKNOWN
    package: str = ""
    version: str = ""
    fixed_version: str = ""
    description: str = ""
    layer_digest: str = ""


@dataclass
class VulnerabilityReport:
    """Complete vulnerability scan report for an image.

    Aggregates all findings from scanning an image's layers,
    with summary statistics by severity level.

    Attributes:
        image_ref: The image reference that was scanned.
        scan_id: Unique identifier for this scan.
        findings: List of vulnerability findings.
        scanned_at: Timestamp when the scan was performed.
        scan_duration: Duration of the scan in seconds.
        layers_scanned: Number of layers scanned.
    """

    image_ref: str = ""
    scan_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    findings: List[VulnerabilityFinding] = field(default_factory=list)
    scanned_at: float = 0.0
    scan_duration: float = 0.0
    layers_scanned: int = 0

    @property
    def critical_count(self) -> int:
        """Count of CRITICAL severity findings."""
        return sum(1 for f in self.findings if f.severity == VulnerabilitySeverity.CRITICAL)

    @property
    def high_count(self) -> int:
        """Count of HIGH severity findings."""
        return sum(1 for f in self.findings if f.severity == VulnerabilitySeverity.HIGH)

    @property
    def medium_count(self) -> int:
        """Count of MEDIUM severity findings."""
        return sum(1 for f in self.findings if f.severity == VulnerabilitySeverity.MEDIUM)

    @property
    def low_count(self) -> int:
        """Count of LOW severity findings."""
        return sum(1 for f in self.findings if f.severity == VulnerabilitySeverity.LOW)

    @property
    def total_count(self) -> int:
        """Total number of findings."""
        return len(self.findings)

    @property
    def has_critical(self) -> bool:
        """Whether any CRITICAL findings exist."""
        return self.critical_count > 0


@dataclass
class GCReport:
    """Report from a garbage collection run.

    Documents the blobs marked, swept, and reclaimed during
    a garbage collection cycle.

    Attributes:
        gc_id: Unique identifier for this GC run.
        phase: Final phase of the GC run.
        blobs_marked: Number of blobs marked as referenced.
        blobs_swept: Number of unreferenced blobs removed.
        bytes_reclaimed: Total bytes freed by the sweep.
        duration: Duration of the GC run in seconds.
        started_at: Timestamp when the GC started.
        errors: List of error messages encountered during GC.
    """

    gc_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    phase: GCPhase = GCPhase.IDLE
    blobs_marked: int = 0
    blobs_swept: int = 0
    bytes_reclaimed: int = 0
    duration: float = 0.0
    started_at: float = 0.0
    errors: List[str] = field(default_factory=list)


@dataclass
class RegistryStats:
    """Aggregate statistics for the image registry.

    Provides a snapshot of the registry's current state for
    dashboard rendering and monitoring.

    Attributes:
        total_blobs: Number of blobs in the store.
        total_bytes: Total storage consumed by blobs.
        total_repos: Number of repositories.
        total_tags: Total number of tags across all repositories.
        total_manifests: Total number of manifests.
        total_pushes: Cumulative push operations.
        total_pulls: Cumulative pull operations.
        total_deletes: Cumulative delete operations.
        gc_runs: Number of GC cycles completed.
        gc_bytes_reclaimed: Total bytes reclaimed by all GC runs.
        images_signed: Number of images with signatures.
        images_scanned: Number of images that have been scanned.
        cache_hits: Image builder layer cache hits.
        cache_misses: Image builder layer cache misses.
    """

    total_blobs: int = 0
    total_bytes: int = 0
    total_repos: int = 0
    total_tags: int = 0
    total_manifests: int = 0
    total_pushes: int = 0
    total_pulls: int = 0
    total_deletes: int = 0
    gc_runs: int = 0
    gc_bytes_reclaimed: int = 0
    images_signed: int = 0
    images_scanned: int = 0
    cache_hits: int = 0
    cache_misses: int = 0

    @property
    def cache_hit_rate(self) -> float:
        """Cache hit rate as a percentage."""
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return 0.0
        return (self.cache_hits / total) * 100.0

    @property
    def dedup_ratio(self) -> float:
        """Deduplication ratio (blobs stored / blobs referenced)."""
        if self.total_manifests == 0:
            return 1.0
        return min(1.0, self.total_blobs / max(1, self.total_manifests))


# ============================================================
# Singleton Metaclass
# ============================================================


class _BlobStoreMeta(type):
    """Metaclass implementing the singleton pattern for BlobStore.

    The blob store is a global content-addressable store.  Only one
    instance should exist per process to ensure deduplication
    invariants hold.
    """

    _instances: Dict[type, Any] = {}
    _lock = threading.Lock()

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        if cls not in cls._instances:
            with cls._lock:
                if cls not in cls._instances:
                    instance = super().__call__(*args, **kwargs)
                    cls._instances[cls] = instance
        return cls._instances[cls]

    @classmethod
    def reset(mcs) -> None:
        """Reset all singleton instances (testing only)."""
        mcs._instances.clear()


# ============================================================
# BlobStore — Content-Addressable Storage
# ============================================================


class BlobStore(metaclass=_BlobStoreMeta):
    """Content-addressable storage for image blobs.

    Stores arbitrary binary blobs indexed by their SHA-256 digest.
    Deduplication is automatic: uploading a blob with an existing
    digest is a no-op.  Reference counting tracks the number of
    manifests referencing each blob to enable garbage collection.

    The blob store is implemented as a singleton to ensure that
    all registry operations share a single content-addressable
    namespace, maintaining deduplication invariants across
    concurrent image push and pull operations.
    """

    def __init__(
        self,
        max_blobs: int = DEFAULT_MAX_BLOBS,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._blobs: Dict[str, bytes] = {}
        self._blob_media_types: Dict[str, str] = {}
        self._ref_counts: Dict[str, int] = defaultdict(int)
        self._created_at: Dict[str, float] = {}
        self._max_blobs = max_blobs
        self._event_bus = event_bus
        self._lock = threading.Lock()
        self._total_pushes = 0
        self._total_pulls = 0
        logger.info("BlobStore initialized: max_blobs=%d", max_blobs)

    @staticmethod
    def compute_digest(data: bytes) -> str:
        """Compute the SHA-256 digest of the given data.

        Args:
            data: Binary content to hash.

        Returns:
            Digest string in 'sha256:<hex>' format.
        """
        return DIGEST_PREFIX + hashlib.sha256(data).hexdigest()

    def exists(self, digest: str) -> bool:
        """Check whether a blob with the given digest exists.

        Args:
            digest: SHA-256 digest to check.

        Returns:
            True if the blob exists in the store.
        """
        with self._lock:
            return digest in self._blobs

    def get(self, digest: str) -> bytes:
        """Retrieve blob content by digest.

        Args:
            digest: SHA-256 digest of the blob to retrieve.

        Returns:
            The blob content as bytes.

        Raises:
            BlobNotFoundError: If no blob with the given digest exists.
            BlobCorruptionError: If the stored content does not match
                the expected digest.
        """
        with self._lock:
            if digest not in self._blobs:
                raise BlobNotFoundError(digest)
            data = self._blobs[digest]
            # Verify integrity on read
            computed = self.compute_digest(data)
            if computed != digest:
                raise BlobCorruptionError(
                    digest, f"Expected {digest}, computed {computed}"
                )
            self._total_pulls += 1
            return data

    def put(self, data: bytes, media_type: str = OCI_LAYER_MEDIA_TYPE) -> str:
        """Store a blob, returning its computed digest.

        If a blob with the same digest already exists, this is a
        no-op and the existing digest is returned (deduplication).

        Args:
            data: Binary content to store.
            media_type: IANA media type of the content.

        Returns:
            The SHA-256 digest of the stored blob.

        Raises:
            BlobStoreFullError: If the store has reached its capacity.
        """
        digest = self.compute_digest(data)
        with self._lock:
            if digest in self._blobs:
                # Deduplication: blob already exists
                self._total_pushes += 1
                return digest
            if len(self._blobs) >= self._max_blobs:
                raise BlobStoreFullError(
                    self._max_blobs,
                    f"Cannot store new blob, {len(self._blobs)} blobs at capacity",
                )
            self._blobs[digest] = data
            self._blob_media_types[digest] = media_type
            self._created_at[digest] = time.time()
            self._total_pushes += 1
        self._emit_event(EventType.REG_BLOB_PUSHED, {"digest": digest, "size": len(data)})
        logger.debug("Blob stored: %s (%d bytes)", digest, len(data))
        return digest

    def delete(self, digest: str) -> None:
        """Delete a blob by digest.

        Args:
            digest: SHA-256 digest of the blob to delete.

        Raises:
            BlobNotFoundError: If no blob with the given digest exists.
        """
        with self._lock:
            if digest not in self._blobs:
                raise BlobNotFoundError(digest)
            del self._blobs[digest]
            self._blob_media_types.pop(digest, None)
            self._created_at.pop(digest, None)
            self._ref_counts.pop(digest, None)
        self._emit_event(EventType.REG_BLOB_DELETED, {"digest": digest})
        logger.debug("Blob deleted: %s", digest)

    def stat(self, digest: str) -> Tuple[int, str]:
        """Return the size and media type of a blob.

        Args:
            digest: SHA-256 digest of the blob.

        Returns:
            Tuple of (size_in_bytes, media_type).

        Raises:
            BlobNotFoundError: If no blob with the given digest exists.
        """
        with self._lock:
            if digest not in self._blobs:
                raise BlobNotFoundError(digest)
            return len(self._blobs[digest]), self._blob_media_types.get(
                digest, OCI_LAYER_MEDIA_TYPE
            )

    def increment_ref(self, digest: str) -> None:
        """Increment the reference count for a blob.

        Args:
            digest: SHA-256 digest of the blob.
        """
        with self._lock:
            self._ref_counts[digest] += 1

    def decrement_ref(self, digest: str) -> None:
        """Decrement the reference count for a blob.

        Args:
            digest: SHA-256 digest of the blob.
        """
        with self._lock:
            if self._ref_counts[digest] > 0:
                self._ref_counts[digest] -= 1

    def get_ref_count(self, digest: str) -> int:
        """Return the reference count for a blob.

        Args:
            digest: SHA-256 digest of the blob.

        Returns:
            The current reference count.
        """
        with self._lock:
            return self._ref_counts.get(digest, 0)

    def get_unreferenced(self, grace_period: float = DEFAULT_GC_GRACE_PERIOD) -> List[str]:
        """Return digests of unreferenced blobs past the grace period.

        Args:
            grace_period: Minimum age in seconds before an unreferenced
                blob is eligible for collection.

        Returns:
            List of digest strings eligible for garbage collection.
        """
        now = time.time()
        result = []
        with self._lock:
            for digest in list(self._blobs.keys()):
                if self._ref_counts.get(digest, 0) == 0:
                    created = self._created_at.get(digest, 0.0)
                    if now - created >= grace_period:
                        result.append(digest)
        return result

    @property
    def blob_count(self) -> int:
        """Return the number of blobs in the store."""
        with self._lock:
            return len(self._blobs)

    @property
    def total_bytes(self) -> int:
        """Return the total bytes consumed by all blobs."""
        with self._lock:
            return sum(len(data) for data in self._blobs.values())

    @property
    def digests(self) -> List[str]:
        """Return all digest strings in the store."""
        with self._lock:
            return list(self._blobs.keys())

    @property
    def total_pushes(self) -> int:
        """Return the cumulative number of push operations."""
        return self._total_pushes

    @property
    def total_pulls(self) -> int:
        """Return the cumulative number of pull operations."""
        return self._total_pulls

    def _emit_event(self, event_type: EventType, data: Dict[str, Any]) -> None:
        """Emit an event to the event bus if available."""
        if self._event_bus is not None:
            try:
                self._event_bus.publish(event_type, data)
            except Exception:
                pass


# ============================================================
# Repository — Tag Management
# ============================================================


class Repository:
    """Repository managing tags and manifest references.

    A repository is a named collection of tagged manifest
    references within the registry.  Tags are mutable pointers
    giving human-readable names to manifest digests.  Each
    repository maintains a history of tag assignments for
    audit and rollback purposes.
    """

    def __init__(
        self,
        name: str,
        max_tags: int = DEFAULT_MAX_TAGS,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._name = name
        self._tags: Dict[str, TagReference] = {}
        self._manifests: Dict[str, OCIManifest] = {}
        self._max_tags = max_tags
        self._event_bus = event_bus
        self._created_at = time.time()
        self._lock = threading.Lock()
        logger.debug("Repository created: %s", name)

    @property
    def name(self) -> str:
        """Return the repository name."""
        return self._name

    @property
    def tag_count(self) -> int:
        """Return the number of active tags."""
        with self._lock:
            return sum(
                1 for t in self._tags.values() if t.state == TagState.ACTIVE
            )

    @property
    def manifest_count(self) -> int:
        """Return the number of stored manifests."""
        with self._lock:
            return len(self._manifests)

    @property
    def created_at(self) -> float:
        """Return the repository creation timestamp."""
        return self._created_at

    def put_manifest(self, reference: str, manifest: OCIManifest) -> str:
        """Store a manifest by tag or digest reference.

        If the reference is a tag name, a TagReference is created
        or updated.  If the reference is a digest, the manifest is
        stored directly by digest.

        Args:
            reference: Tag name or digest string.
            manifest: The OCI manifest to store.

        Returns:
            The manifest digest.

        Raises:
            TagLimitError: If the repository has reached its tag limit.
        """
        digest = manifest.compute_digest()
        now = time.time()

        with self._lock:
            # Store manifest by digest
            self._manifests[digest] = manifest

            # If reference is a tag (not a digest), update the tag
            if not reference.startswith(DIGEST_PREFIX):
                if reference not in self._tags:
                    active_count = sum(
                        1 for t in self._tags.values() if t.state == TagState.ACTIVE
                    )
                    if active_count >= self._max_tags:
                        raise TagLimitError(
                            self._name,
                            self._max_tags,
                            f"Cannot create tag '{reference}'",
                        )
                    self._tags[reference] = TagReference(
                        name=reference,
                        digest=digest,
                        state=TagState.ACTIVE,
                        created_at=now,
                        updated_at=now,
                        history=[(digest, now)],
                    )
                    self._emit_event(
                        EventType.REG_TAG_CREATED,
                        {"repository": self._name, "tag": reference, "digest": digest},
                    )
                else:
                    tag = self._tags[reference]
                    tag.history.append((digest, now))
                    tag.digest = digest
                    tag.updated_at = now
                    tag.state = TagState.ACTIVE

        self._emit_event(
            EventType.REG_MANIFEST_PUSHED,
            {"repository": self._name, "reference": reference, "digest": digest},
        )
        logger.debug(
            "Manifest stored: %s:%s -> %s", self._name, reference, digest
        )
        return digest

    def get_manifest(self, reference: str) -> OCIManifest:
        """Retrieve a manifest by tag or digest reference.

        Args:
            reference: Tag name or digest string.

        Returns:
            The OCI manifest.

        Raises:
            TagNotFoundError: If the reference is a tag that does not exist.
            ManifestNotFoundError: If the manifest digest is not found.
        """
        with self._lock:
            digest = self._resolve_reference(reference)
            if digest not in self._manifests:
                raise ManifestNotFoundError(f"{self._name}:{reference}")
            self._emit_event(
                EventType.REG_MANIFEST_PULLED,
                {"repository": self._name, "reference": reference, "digest": digest},
            )
            return copy.deepcopy(self._manifests[digest])

    def delete_manifest(self, reference: str) -> str:
        """Delete a manifest by tag or digest reference.

        If the reference is a tag, the tag is marked as DELETED
        and the manifest is removed if no other tags reference it.

        Args:
            reference: Tag name or digest string.

        Returns:
            The digest of the deleted manifest.

        Raises:
            TagNotFoundError: If the reference is a tag that does not exist.
            ManifestNotFoundError: If the manifest is not found.
        """
        with self._lock:
            digest = self._resolve_reference(reference)

            # If reference is a tag, mark it deleted
            if not reference.startswith(DIGEST_PREFIX) and reference in self._tags:
                self._tags[reference].state = TagState.DELETED
                self._emit_event(
                    EventType.REG_TAG_DELETED,
                    {"repository": self._name, "tag": reference},
                )

            # Check if any active tags still reference this digest
            still_referenced = any(
                t.digest == digest and t.state == TagState.ACTIVE
                for t in self._tags.values()
            )

            if not still_referenced and digest in self._manifests:
                del self._manifests[digest]

        self._emit_event(
            EventType.REG_MANIFEST_DELETED,
            {"repository": self._name, "reference": reference, "digest": digest},
        )
        logger.debug("Manifest deleted: %s:%s", self._name, reference)
        return digest

    def list_tags(self) -> List[str]:
        """Return all active tag names in the repository.

        Returns:
            Sorted list of active tag names.
        """
        with self._lock:
            return sorted(
                t.name for t in self._tags.values() if t.state == TagState.ACTIVE
            )

    def get_tag(self, tag_name: str) -> TagReference:
        """Retrieve a tag reference by name.

        Args:
            tag_name: The tag name.

        Returns:
            The TagReference object.

        Raises:
            TagNotFoundError: If the tag does not exist.
        """
        with self._lock:
            if tag_name not in self._tags:
                raise TagNotFoundError(self._name, tag_name)
            return copy.deepcopy(self._tags[tag_name])

    def has_tag(self, tag_name: str) -> bool:
        """Check whether a tag exists and is active.

        Args:
            tag_name: The tag name to check.

        Returns:
            True if the tag exists and is active.
        """
        with self._lock:
            tag = self._tags.get(tag_name)
            return tag is not None and tag.state == TagState.ACTIVE

    def get_manifest_digests(self) -> List[str]:
        """Return all manifest digests in the repository.

        Returns:
            List of manifest digest strings.
        """
        with self._lock:
            return list(self._manifests.keys())

    def tag_history(self, tag_name: str) -> List[Tuple[str, float]]:
        """Return the history of a tag.

        Args:
            tag_name: The tag name.

        Returns:
            List of (digest, timestamp) tuples.

        Raises:
            TagNotFoundError: If the tag does not exist.
        """
        with self._lock:
            if tag_name not in self._tags:
                raise TagNotFoundError(self._name, tag_name)
            return list(self._tags[tag_name].history)

    def _resolve_reference(self, reference: str) -> str:
        """Resolve a tag or digest reference to a digest.

        Args:
            reference: Tag name or digest string.

        Returns:
            The resolved digest string.

        Raises:
            TagNotFoundError: If the reference is a tag that does not exist.
        """
        if reference.startswith(DIGEST_PREFIX):
            return reference
        tag = self._tags.get(reference)
        if tag is None or tag.state == TagState.DELETED:
            raise TagNotFoundError(self._name, reference)
        return tag.digest

    def _emit_event(self, event_type: EventType, data: Dict[str, Any]) -> None:
        """Emit an event to the event bus if available."""
        if self._event_bus is not None:
            try:
                self._event_bus.publish(event_type, data)
            except Exception:
                pass


# ============================================================
# RegistryAPI — OCI Distribution Endpoints
# ============================================================


class RegistryAPI:
    """OCI Distribution Specification API implementation.

    Implements the core registry operations defined by the OCI
    Distribution Specification: blob push/pull/delete/head,
    manifest push/pull/delete/head, repository catalog, and
    tag listing.

    The API manages repositories as first-class resources,
    auto-creating repositories on first push and enforcing
    a configurable repository limit.
    """

    def __init__(
        self,
        blob_store: BlobStore,
        max_repos: int = DEFAULT_MAX_REPOS,
        max_tags: int = DEFAULT_MAX_TAGS,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._blob_store = blob_store
        self._repos: Dict[str, Repository] = {}
        self._max_repos = max_repos
        self._max_tags = max_tags
        self._event_bus = event_bus
        self._lock = threading.Lock()
        self._op_counts: Dict[RegistryOperation, int] = defaultdict(int)
        logger.info(
            "RegistryAPI initialized: max_repos=%d, max_tags=%d",
            max_repos,
            max_tags,
        )

    def _get_or_create_repo(self, name: str) -> Repository:
        """Get an existing repository or create a new one.

        Args:
            name: Repository name.

        Returns:
            The Repository instance.

        Raises:
            RepositoryLimitError: If the maximum repository count is reached.
        """
        with self._lock:
            if name not in self._repos:
                if len(self._repos) >= self._max_repos:
                    raise RepositoryLimitError(
                        self._max_repos,
                        f"Cannot create repository '{name}'",
                    )
                self._repos[name] = Repository(
                    name=name,
                    max_tags=self._max_tags,
                    event_bus=self._event_bus,
                )
                self._emit_event(
                    EventType.REG_REPO_CREATED, {"repository": name}
                )
                logger.debug("Repository auto-created: %s", name)
            return self._repos[name]

    def _get_repo(self, name: str) -> Repository:
        """Get an existing repository.

        Args:
            name: Repository name.

        Returns:
            The Repository instance.

        Raises:
            RepositoryNotFoundError: If the repository does not exist.
        """
        with self._lock:
            if name not in self._repos:
                raise RepositoryNotFoundError(name)
            return self._repos[name]

    # --- Blob operations ---

    def head_blob(self, repository: str, digest: str) -> Tuple[int, str]:
        """Check blob existence and return metadata (HEAD).

        Args:
            repository: Repository name.
            digest: Blob digest.

        Returns:
            Tuple of (size, media_type).

        Raises:
            BlobNotFoundError: If the blob does not exist.
        """
        self._op_counts[RegistryOperation.BLOB_HEAD] += 1
        return self._blob_store.stat(digest)

    def get_blob(self, repository: str, digest: str) -> bytes:
        """Retrieve blob content (GET).

        Args:
            repository: Repository name.
            digest: Blob digest.

        Returns:
            Blob content as bytes.

        Raises:
            BlobNotFoundError: If the blob does not exist.
        """
        self._op_counts[RegistryOperation.BLOB_GET] += 1
        return self._blob_store.get(digest)

    def put_blob(
        self,
        repository: str,
        data: bytes,
        media_type: str = OCI_LAYER_MEDIA_TYPE,
    ) -> str:
        """Store a blob (PUT).

        Auto-creates the repository if it does not exist.

        Args:
            repository: Repository name.
            data: Blob content.
            media_type: IANA media type.

        Returns:
            The computed digest.

        Raises:
            BlobStoreFullError: If the store is at capacity.
        """
        self._op_counts[RegistryOperation.BLOB_PUT] += 1
        self._get_or_create_repo(repository)
        return self._blob_store.put(data, media_type)

    def delete_blob(self, repository: str, digest: str) -> None:
        """Delete a blob (DELETE).

        Args:
            repository: Repository name.
            digest: Blob digest.

        Raises:
            BlobNotFoundError: If the blob does not exist.
        """
        self._op_counts[RegistryOperation.BLOB_DELETE] += 1
        self._blob_store.delete(digest)

    # --- Manifest operations ---

    def put_manifest(
        self,
        repository: str,
        reference: str,
        manifest: OCIManifest,
    ) -> str:
        """Store a manifest (PUT).

        Validates that all referenced blobs exist in the store
        before accepting the manifest.  Auto-creates the
        repository if it does not exist.

        Args:
            repository: Repository name.
            reference: Tag name or digest.
            manifest: The OCI manifest to store.

        Returns:
            The manifest digest.

        Raises:
            ManifestValidationError: If referenced blobs are missing.
            RepositoryLimitError: If the repository limit is reached.
        """
        self._op_counts[RegistryOperation.MANIFEST_PUT] += 1

        # Validate referential integrity
        if manifest.config is not None:
            if not self._blob_store.exists(manifest.config.digest):
                raise ManifestValidationError(
                    f"{repository}:{reference}",
                    f"Config blob not found: {manifest.config.digest}",
                )

        for layer_desc in manifest.layers:
            if not self._blob_store.exists(layer_desc.digest):
                raise ManifestValidationError(
                    f"{repository}:{reference}",
                    f"Layer blob not found: {layer_desc.digest}",
                )

        repo = self._get_or_create_repo(repository)
        digest = repo.put_manifest(reference, manifest)

        # Update blob reference counts
        if manifest.config is not None:
            self._blob_store.increment_ref(manifest.config.digest)
        for layer_desc in manifest.layers:
            self._blob_store.increment_ref(layer_desc.digest)

        return digest

    def get_manifest(self, repository: str, reference: str) -> OCIManifest:
        """Retrieve a manifest (GET).

        Args:
            repository: Repository name.
            reference: Tag name or digest.

        Returns:
            The OCI manifest.

        Raises:
            RepositoryNotFoundError: If the repository does not exist.
            ManifestNotFoundError: If the manifest is not found.
        """
        self._op_counts[RegistryOperation.MANIFEST_GET] += 1
        repo = self._get_repo(repository)
        return repo.get_manifest(reference)

    def head_manifest(self, repository: str, reference: str) -> str:
        """Check manifest existence and return its digest (HEAD).

        Args:
            repository: Repository name.
            reference: Tag name or digest.

        Returns:
            The manifest digest.

        Raises:
            RepositoryNotFoundError: If the repository does not exist.
            ManifestNotFoundError: If the manifest is not found.
        """
        self._op_counts[RegistryOperation.MANIFEST_HEAD] += 1
        repo = self._get_repo(repository)
        manifest = repo.get_manifest(reference)
        return manifest.compute_digest()

    def delete_manifest(self, repository: str, reference: str) -> str:
        """Delete a manifest (DELETE).

        Decrements blob reference counts for the deleted manifest.

        Args:
            repository: Repository name.
            reference: Tag name or digest.

        Returns:
            The digest of the deleted manifest.

        Raises:
            RepositoryNotFoundError: If the repository does not exist.
            ManifestNotFoundError: If the manifest is not found.
        """
        self._op_counts[RegistryOperation.MANIFEST_DELETE] += 1
        repo = self._get_repo(repository)

        # Get manifest before deletion to update ref counts
        try:
            manifest = repo.get_manifest(reference)
            digest = repo.delete_manifest(reference)

            # Decrement ref counts
            if manifest.config is not None:
                self._blob_store.decrement_ref(manifest.config.digest)
            for layer_desc in manifest.layers:
                self._blob_store.decrement_ref(layer_desc.digest)

            return digest
        except (TagNotFoundError, ManifestNotFoundError):
            raise ManifestNotFoundError(f"{repository}:{reference}")

    # --- Catalog and tags ---

    def catalog(self) -> List[str]:
        """Return the registry catalog (list of repository names).

        Returns:
            Sorted list of repository names.
        """
        self._op_counts[RegistryOperation.CATALOG] += 1
        with self._lock:
            return sorted(self._repos.keys())

    def list_tags(self, repository: str) -> List[str]:
        """List tags for a repository.

        Args:
            repository: Repository name.

        Returns:
            Sorted list of tag names.

        Raises:
            RepositoryNotFoundError: If the repository does not exist.
        """
        self._op_counts[RegistryOperation.TAG_LIST] += 1
        repo = self._get_repo(repository)
        return repo.list_tags()

    # --- Stats ---

    @property
    def repo_count(self) -> int:
        """Return the number of repositories."""
        with self._lock:
            return len(self._repos)

    @property
    def op_counts(self) -> Dict[RegistryOperation, int]:
        """Return operation counts by type."""
        return dict(self._op_counts)

    def get_repo(self, name: str) -> Repository:
        """Public accessor for repository objects.

        Args:
            name: Repository name.

        Returns:
            The Repository instance.

        Raises:
            RepositoryNotFoundError: If the repository does not exist.
        """
        return self._get_repo(name)

    def _emit_event(self, event_type: EventType, data: Dict[str, Any]) -> None:
        """Emit an event to the event bus if available."""
        if self._event_bus is not None:
            try:
                self._event_bus.publish(event_type, data)
            except Exception:
                pass


# ============================================================
# FizzFile Parser — Build DSL
# ============================================================


class FizzFileParser:
    """Parser for the FizzFile container image build DSL.

    FizzFile is the platform's Dockerfile equivalent, providing
    a declarative build language for constructing FizzBuzz
    container images.  The parser tokenizes and validates
    FizzFile syntax, producing a list of FizzFileStep objects
    ready for execution by the ImageBuilder.

    Supported instructions:
        FROM <image>[:<tag>]
        FIZZ <divisor> <word>
        BUZZ <divisor> <word>
        RUN <command>
        COPY <src> <dest>
        ENV <key>=<value>
        ENTRYPOINT [<args>]
        LABEL <key>=<value>

    Comments begin with '#'.  Line continuation uses '\\'.
    """

    _INSTRUCTION_PATTERN = re.compile(
        r"^\s*(FROM|FIZZ|BUZZ|RUN|COPY|ENV|ENTRYPOINT|LABEL)\s+(.*)",
        re.IGNORECASE,
    )

    def __init__(self) -> None:
        self._steps: List[FizzFileStep] = []
        self._errors: List[str] = []

    def parse(self, content: str) -> List[FizzFileStep]:
        """Parse a FizzFile and return a list of build steps.

        Args:
            content: FizzFile content as a string.

        Returns:
            List of parsed FizzFileStep objects.

        Raises:
            FizzFileMissingFromError: If the first instruction is not FROM.
            FizzFileParseError: If syntax errors are encountered.
        """
        self._steps = []
        self._errors = []

        lines = self._preprocess(content)

        if not lines:
            raise FizzFileMissingFromError("FizzFile is empty")

        for line_number, line_text in lines:
            self._parse_line(line_number, line_text)

        if self._errors:
            raise FizzFileParseError(
                self._errors[0][0] if isinstance(self._errors[0], tuple) else 1,
                "; ".join(str(e) for e in self._errors),
            )

        # Validate FROM is first
        if not self._steps:
            raise FizzFileMissingFromError("No instructions found")
        if self._steps[0].instruction != FizzFileInstruction.FROM:
            raise FizzFileMissingFromError(
                f"First instruction must be FROM, got {self._steps[0].instruction.value}"
            )

        return list(self._steps)

    def _preprocess(self, content: str) -> List[Tuple[int, str]]:
        """Preprocess FizzFile content: strip comments, join continuations.

        Args:
            content: Raw FizzFile content.

        Returns:
            List of (line_number, processed_line) tuples.
        """
        raw_lines = content.split("\n")
        result: List[Tuple[int, str]] = []
        current_line = ""
        start_line_number = 1

        for i, line in enumerate(raw_lines, 1):
            stripped = line.strip()

            # Skip empty lines and comments
            if not stripped or stripped.startswith(FIZZFILE_COMMENT):
                if current_line:
                    result.append((start_line_number, current_line.strip()))
                    current_line = ""
                continue

            # Handle line continuation
            if stripped.endswith(FIZZFILE_CONTINUATION):
                if not current_line:
                    start_line_number = i
                current_line += stripped[:-1] + " "
                continue

            if current_line:
                current_line += stripped
                result.append((start_line_number, current_line.strip()))
                current_line = ""
            else:
                result.append((i, stripped))

        # Handle trailing continuation
        if current_line:
            result.append((start_line_number, current_line.strip()))

        return result

    def _parse_line(self, line_number: int, line: str) -> None:
        """Parse a single preprocessed line.

        Args:
            line_number: Source line number.
            line: The preprocessed line text.
        """
        match = self._INSTRUCTION_PATTERN.match(line)
        if match is None:
            self._errors.append(f"Line {line_number}: unrecognized instruction: {line}")
            return

        instruction_name = match.group(1).upper()
        arguments = match.group(2).strip()

        try:
            instruction = FizzFileInstruction(instruction_name)
        except ValueError:
            self._errors.append(
                f"Line {line_number}: unknown instruction: {instruction_name}"
            )
            return

        # Validate instruction-specific arguments
        self._validate_instruction(line_number, instruction, arguments)

        self._steps.append(
            FizzFileStep(
                instruction=instruction,
                arguments=arguments,
                line_number=line_number,
                original_line=line,
            )
        )

    def _validate_instruction(
        self, line_number: int, instruction: FizzFileInstruction, arguments: str
    ) -> None:
        """Validate instruction-specific argument requirements.

        Args:
            line_number: Source line number.
            instruction: The instruction type.
            arguments: The instruction arguments.
        """
        if not arguments:
            self._errors.append(
                f"Line {line_number}: {instruction.value} requires arguments"
            )
            return

        if instruction == FizzFileInstruction.FIZZ:
            self._validate_fizz_buzz_args(line_number, "FIZZ", arguments)
        elif instruction == FizzFileInstruction.BUZZ:
            self._validate_fizz_buzz_args(line_number, "BUZZ", arguments)
        elif instruction == FizzFileInstruction.COPY:
            parts = arguments.split()
            if len(parts) < 2:
                self._errors.append(
                    f"Line {line_number}: COPY requires <src> <dest>"
                )
        elif instruction == FizzFileInstruction.ENV:
            if "=" not in arguments:
                self._errors.append(
                    f"Line {line_number}: ENV requires KEY=VALUE format"
                )

    def _validate_fizz_buzz_args(
        self, line_number: int, name: str, arguments: str
    ) -> None:
        """Validate FIZZ/BUZZ instruction arguments.

        Args:
            line_number: Source line number.
            name: Instruction name ('FIZZ' or 'BUZZ').
            arguments: The instruction arguments.
        """
        parts = arguments.split(None, 1)
        if len(parts) < 2:
            self._errors.append(
                f"Line {line_number}: {name} requires <divisor> <word>"
            )
            return
        try:
            int(parts[0])
        except ValueError:
            self._errors.append(
                f"Line {line_number}: {name} divisor must be an integer, got '{parts[0]}'"
            )


# ============================================================
# ImageBuilder — Build Images from FizzFiles
# ============================================================


class ImageBuilder:
    """Builds OCI images from FizzFile build scripts.

    Processes FizzFile instructions to produce complete OCI
    images: starts from the base image specified by FROM,
    executes each instruction, captures filesystem changes
    as layers, and pushes the resulting manifest and config
    to the registry.

    Layer caching avoids re-executing unchanged instructions.
    Each instruction is hashed (instruction text + parent
    layer digest), and if the hash matches a previously built
    layer, the cached layer is reused.
    """

    def __init__(
        self,
        blob_store: BlobStore,
        registry_api: RegistryAPI,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._blob_store = blob_store
        self._registry_api = registry_api
        self._event_bus = event_bus
        self._instruction_cache: Dict[str, str] = {}
        self._cache_hits = 0
        self._cache_misses = 0
        self._builds_completed = 0
        self._lock = threading.Lock()
        logger.info("ImageBuilder initialized")

    def build(
        self,
        fizzfile_content: str,
        repository: str,
        tag: str = DEFAULT_BUILD_TAG,
    ) -> str:
        """Build an OCI image from a FizzFile.

        Args:
            fizzfile_content: FizzFile content as a string.
            repository: Target repository name.
            tag: Target tag name.

        Returns:
            The manifest digest of the built image.

        Raises:
            FizzFileMissingFromError: If FROM is missing.
            FizzFileParseError: If syntax errors exist.
            ImageBuildError: If the build process fails.
        """
        context = BuildContext(
            started_at=time.time(),
            phase=BuildPhase.PARSING,
        )

        try:
            # Parse FizzFile
            parser = FizzFileParser()
            context.steps = parser.parse(fizzfile_content)
            context.phase = BuildPhase.RESOLVING_BASE

            # Process FROM instruction
            from_step = context.steps[0]
            context.base_image = from_step.arguments.strip()

            # Resolve base image layers
            base_layers = self._resolve_base_layers(context.base_image)
            context.layers = list(base_layers)

            context.phase = BuildPhase.EXECUTING

            # Execute remaining instructions
            for step in context.steps[1:]:
                self._execute_step(context, step)

            context.phase = BuildPhase.COMMITTING

            # Create image config
            image_config = self._create_image_config(context)
            config_data = image_config.serialize()
            config_digest = self._blob_store.put(config_data, OCI_CONFIG_MEDIA_TYPE)

            # Create manifest
            manifest = self._create_manifest(context, config_digest, len(config_data))

            context.phase = BuildPhase.PUSHING

            # Push manifest to registry
            digest = self._registry_api.put_manifest(repository, tag, manifest)

            context.phase = BuildPhase.COMPLETE
            context.completed_at = time.time()

            with self._lock:
                self._builds_completed += 1

            self._emit_event(
                EventType.REG_IMAGE_BUILT,
                {
                    "repository": repository,
                    "tag": tag,
                    "digest": digest,
                    "layers": len(context.layers),
                    "duration": context.completed_at - context.started_at,
                },
            )

            logger.info(
                "Image built: %s:%s -> %s (%d layers)",
                repository,
                tag,
                digest,
                len(context.layers),
            )
            return digest

        except (FizzFileMissingFromError, FizzFileParseError):
            context.phase = BuildPhase.FAILED
            raise
        except Exception as e:
            context.phase = BuildPhase.FAILED
            raise ImageBuildError("build", str(e))

    def _resolve_base_layers(self, base_image: str) -> List[str]:
        """Resolve the base image to its layer digests.

        Args:
            base_image: Base image reference (e.g., 'scratch', 'fizzbuzz:latest').

        Returns:
            List of layer digest strings from the base image.
        """
        if base_image == SCRATCH_IMAGE:
            return []

        # Parse image:tag format
        parts = base_image.split(":")
        repo_name = parts[0]
        ref = parts[1] if len(parts) > 1 else DEFAULT_BUILD_TAG

        try:
            manifest = self._registry_api.get_manifest(repo_name, ref)
            return [layer.digest for layer in manifest.layers]
        except (RepositoryNotFoundError, ManifestNotFoundError, TagNotFoundError):
            # Base image not found — start from empty
            return []

    def _execute_step(self, context: BuildContext, step: FizzFileStep) -> None:
        """Execute a single FizzFile instruction.

        Args:
            context: The build context.
            step: The instruction to execute.
        """
        # Compute cache key
        parent_digest = context.layers[-1] if context.layers else "scratch"
        cache_key = self._compute_cache_key(step, parent_digest)

        # Check layer cache
        with self._lock:
            cached_digest = self._instruction_cache.get(cache_key)

        if cached_digest is not None and self._blob_store.exists(cached_digest):
            # Cache hit — reuse layer
            context.layers.append(cached_digest)
            with self._lock:
                self._cache_hits += 1
            self._emit_event(
                EventType.REG_LAYER_CACHED,
                {"cache_key": cache_key, "digest": cached_digest, "hit": True},
            )
            logger.debug("Cache hit for %s: %s", step.instruction.value, cached_digest)
            return

        with self._lock:
            self._cache_misses += 1

        # Execute instruction and create layer
        layer_data = self._execute_instruction(context, step)

        if layer_data:
            digest = self._blob_store.put(layer_data, OCI_LAYER_GZIP_MEDIA_TYPE)
            context.layers.append(digest)

            # Update cache
            with self._lock:
                if len(self._instruction_cache) >= MAX_INSTRUCTION_CACHE_SIZE:
                    # Evict oldest entry
                    oldest_key = next(iter(self._instruction_cache))
                    del self._instruction_cache[oldest_key]
                self._instruction_cache[cache_key] = digest

    def _execute_instruction(
        self, context: BuildContext, step: FizzFileStep
    ) -> Optional[bytes]:
        """Execute a FizzFile instruction and return the layer content.

        Args:
            context: The build context.
            step: The instruction to execute.

        Returns:
            Layer content bytes, or None for metadata-only instructions.
        """
        instruction = step.instruction
        arguments = step.arguments

        if instruction == FizzFileInstruction.FIZZ:
            parts = arguments.split(None, 1)
            divisor = int(parts[0])
            word = parts[1].strip().strip('"').strip("'")
            context.fizz_rules.append((divisor, word))
            # Create a layer representing the Fizz rule
            layer_content = f"FIZZ {divisor} {word}".encode("utf-8")
            return layer_content

        elif instruction == FizzFileInstruction.BUZZ:
            parts = arguments.split(None, 1)
            divisor = int(parts[0])
            word = parts[1].strip().strip('"').strip("'")
            context.buzz_rules.append((divisor, word))
            layer_content = f"BUZZ {divisor} {word}".encode("utf-8")
            return layer_content

        elif instruction == FizzFileInstruction.RUN:
            # Simulate command execution by creating a layer with the command
            layer_content = f"RUN {arguments}".encode("utf-8")
            return layer_content

        elif instruction == FizzFileInstruction.COPY:
            parts = arguments.split()
            src = parts[0]
            dest = parts[1] if len(parts) > 1 else "/"
            layer_content = f"COPY {src} -> {dest}".encode("utf-8")
            return layer_content

        elif instruction == FizzFileInstruction.ENV:
            key_value = arguments.strip()
            if "=" in key_value:
                key, value = key_value.split("=", 1)
                context.env_vars[key.strip()] = value.strip()
            # ENV is metadata-only but produces a history entry layer
            layer_content = f"ENV {key_value}".encode("utf-8")
            return layer_content

        elif instruction == FizzFileInstruction.ENTRYPOINT:
            # Parse entrypoint arguments
            ep_args = arguments.strip()
            if ep_args.startswith("["):
                # JSON array format
                ep_args = ep_args.strip("[]")
                context.entrypoint = [
                    a.strip().strip('"').strip("'") for a in ep_args.split(",")
                ]
            else:
                context.entrypoint = [ep_args]
            return None  # Metadata-only

        elif instruction == FizzFileInstruction.LABEL:
            key_value = arguments.strip()
            if "=" in key_value:
                key, value = key_value.split("=", 1)
                context.labels[key.strip()] = value.strip().strip('"').strip("'")
            return None  # Metadata-only

        return None

    def _compute_cache_key(self, step: FizzFileStep, parent_digest: str) -> str:
        """Compute a cache key for a build instruction.

        The cache key is the SHA-256 hash of the instruction text
        combined with the parent layer digest, ensuring that cache
        hits only occur when both the instruction and its context
        are identical.

        Args:
            step: The build step.
            parent_digest: Digest of the parent layer.

        Returns:
            Cache key as a hex string.
        """
        key_data = f"{step.instruction.value}:{step.arguments}:{parent_digest}"
        return hashlib.sha256(key_data.encode("utf-8")).hexdigest()

    def _create_image_config(self, context: BuildContext) -> OCIImageConfig:
        """Create the OCI image config from the build context.

        Args:
            context: The build context.

        Returns:
            The OCIImageConfig for the built image.
        """
        config = OCIImageConfig(
            created=datetime.now(timezone.utc).isoformat(),
            author="FizzRegistry ImageBuilder",
            rootfs=RootFS(
                type="layers",
                diff_ids=list(context.layers),
            ),
            config=ContainerConfig(
                entrypoint=context.entrypoint or ["python", "-m", "enterprise_fizzbuzz"],
                env=[f"{k}={v}" for k, v in context.env_vars.items()],
                labels=dict(context.labels),
            ),
        )

        # Build history
        for step in context.steps:
            config.history.append(
                HistoryEntry(
                    created=datetime.now(timezone.utc).isoformat(),
                    created_by=step.original_line,
                    empty_layer=(step.instruction in (
                        FizzFileInstruction.ENTRYPOINT,
                        FizzFileInstruction.LABEL,
                    )),
                )
            )

        return config

    def _create_manifest(
        self, context: BuildContext, config_digest: str, config_size: int
    ) -> OCIManifest:
        """Create the OCI manifest from the build context.

        Args:
            context: The build context.
            config_digest: Digest of the config blob.
            config_size: Size of the config blob in bytes.

        Returns:
            The OCIManifest for the built image.
        """
        manifest = OCIManifest(
            config=OCIDescriptor(
                media_type=OCI_CONFIG_MEDIA_TYPE,
                digest=config_digest,
                size=config_size,
            ),
        )

        for layer_digest in context.layers:
            try:
                size, media_type = self._blob_store.stat(layer_digest)
            except BlobNotFoundError:
                size = 0
                media_type = OCI_LAYER_GZIP_MEDIA_TYPE

            manifest.layers.append(
                OCIDescriptor(
                    media_type=media_type,
                    digest=layer_digest,
                    size=size,
                )
            )

        return manifest

    @property
    def cache_hits(self) -> int:
        """Return the number of layer cache hits."""
        return self._cache_hits

    @property
    def cache_misses(self) -> int:
        """Return the number of layer cache misses."""
        return self._cache_misses

    @property
    def builds_completed(self) -> int:
        """Return the number of builds completed."""
        return self._builds_completed

    @property
    def cache_size(self) -> int:
        """Return the number of entries in the instruction cache."""
        with self._lock:
            return len(self._instruction_cache)

    def _emit_event(self, event_type: EventType, data: Dict[str, Any]) -> None:
        """Emit an event to the event bus if available."""
        if self._event_bus is not None:
            try:
                self._event_bus.publish(event_type, data)
            except Exception:
                pass


# ============================================================
# GarbageCollector — Mark-and-Sweep
# ============================================================


class GarbageCollector:
    """Mark-and-sweep garbage collector for unreferenced blobs.

    Identifies blobs that are not referenced by any manifest in
    any repository and removes them, reclaiming storage.  A
    configurable grace period prevents deletion of blobs that
    are part of an in-progress push operation.

    The algorithm:
    1. MARK: Walk all manifests in all repositories, marking
       every referenced blob (config + layers).
    2. SWEEP: Remove all blobs not marked in step 1 that have
       exceeded the grace period.
    """

    def __init__(
        self,
        blob_store: BlobStore,
        registry_api: RegistryAPI,
        grace_period: float = DEFAULT_GC_GRACE_PERIOD,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._blob_store = blob_store
        self._registry_api = registry_api
        self._grace_period = grace_period
        self._event_bus = event_bus
        self._gc_runs = 0
        self._total_bytes_reclaimed = 0
        self._lock = threading.Lock()
        logger.info("GarbageCollector initialized: grace_period=%.1fs", grace_period)

    def collect(self) -> GCReport:
        """Run a full garbage collection cycle.

        Returns:
            GCReport documenting the collection results.

        Raises:
            GarbageCollectionError: If the GC encounters a fatal error.
        """
        report = GCReport(
            started_at=time.time(),
            phase=GCPhase.MARK,
        )

        try:
            # Phase 1: MARK
            referenced = self._mark()
            report.blobs_marked = len(referenced)
            report.phase = GCPhase.SWEEP

            # Phase 2: SWEEP
            swept_count, bytes_reclaimed = self._sweep(referenced)
            report.blobs_swept = swept_count
            report.bytes_reclaimed = bytes_reclaimed

            report.phase = GCPhase.COMPLETE
            report.duration = time.time() - report.started_at

            with self._lock:
                self._gc_runs += 1
                self._total_bytes_reclaimed += bytes_reclaimed

            self._emit_event(
                EventType.REG_GC_COMPLETED,
                {
                    "gc_id": report.gc_id,
                    "blobs_marked": report.blobs_marked,
                    "blobs_swept": report.blobs_swept,
                    "bytes_reclaimed": report.bytes_reclaimed,
                    "duration": report.duration,
                },
            )

            logger.info(
                "GC completed: marked=%d, swept=%d, reclaimed=%d bytes",
                report.blobs_marked,
                report.blobs_swept,
                report.bytes_reclaimed,
            )
            return report

        except Exception as e:
            report.errors.append(str(e))
            report.phase = GCPhase.COMPLETE
            report.duration = time.time() - report.started_at
            raise GarbageCollectionError(str(e))

    def _mark(self) -> Set[str]:
        """Mark phase: walk all manifests and collect referenced digests.

        Returns:
            Set of referenced blob digests.
        """
        referenced: Set[str] = set()
        catalog = self._registry_api.catalog()

        for repo_name in catalog:
            try:
                repo = self._registry_api.get_repo(repo_name)
                for digest in repo.get_manifest_digests():
                    try:
                        manifest = repo.get_manifest(digest)
                        # Mark config blob
                        if manifest.config is not None:
                            referenced.add(manifest.config.digest)
                        # Mark layer blobs
                        for layer_desc in manifest.layers:
                            referenced.add(layer_desc.digest)
                        # Mark the manifest itself (stored as blob in some registries)
                        referenced.add(digest)
                    except (ManifestNotFoundError, TagNotFoundError):
                        continue
            except RepositoryNotFoundError:
                continue

        return referenced

    def _sweep(self, referenced: Set[str]) -> Tuple[int, int]:
        """Sweep phase: remove unreferenced blobs past the grace period.

        Args:
            referenced: Set of referenced blob digests to keep.

        Returns:
            Tuple of (blobs_swept, bytes_reclaimed).
        """
        swept = 0
        bytes_reclaimed = 0
        unreferenced = self._blob_store.get_unreferenced(self._grace_period)

        for digest in unreferenced:
            if digest not in referenced:
                try:
                    size, _ = self._blob_store.stat(digest)
                    self._blob_store.delete(digest)
                    swept += 1
                    bytes_reclaimed += size
                except BlobNotFoundError:
                    continue

        return swept, bytes_reclaimed

    @property
    def gc_runs(self) -> int:
        """Return the number of GC cycles completed."""
        return self._gc_runs

    @property
    def total_bytes_reclaimed(self) -> int:
        """Return the total bytes reclaimed across all GC runs."""
        return self._total_bytes_reclaimed

    def _emit_event(self, event_type: EventType, data: Dict[str, Any]) -> None:
        """Emit an event to the event bus if available."""
        if self._event_bus is not None:
            try:
                self._event_bus.publish(event_type, data)
            except Exception:
                pass


# ============================================================
# ImageSigner — ECDSA-P256 Cosign-Style Signing
# ============================================================


class ImageSigner:
    """Cosign-style image signing and verification.

    Signs manifest digests using HMAC-SHA256 keys, producing
    signatures that attest to the provenance and integrity of
    container images.  Signatures are stored as OCI artifacts
    linked to the signed image.

    The signing key is managed by Bob McFizzington as the
    platform's designated Secrets Vault Custodian.
    """

    def __init__(
        self,
        blob_store: BlobStore,
        signing_key: Optional[bytes] = None,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._blob_store = blob_store
        self._signing_key = signing_key or self._generate_key()
        self._signatures: Dict[str, ImageSignature] = {}
        self._event_bus = event_bus
        self._lock = threading.Lock()
        self._key_id = hashlib.sha256(self._signing_key).hexdigest()[:16]
        logger.info("ImageSigner initialized: key_id=%s", self._key_id)

    @staticmethod
    def _generate_key() -> bytes:
        """Generate a random HMAC signing key.

        Returns:
            32 bytes of random key material.
        """
        return os.urandom(32)

    def sign(self, manifest_digest: str, signer: str = "Bob McFizzington") -> ImageSignature:
        """Sign a manifest digest.

        Args:
            manifest_digest: The digest of the manifest to sign.
            signer: Identity of the signer.

        Returns:
            The ImageSignature object.

        Raises:
            ImageSignatureError: If signing fails.
        """
        try:
            # Compute HMAC-SHA256 signature
            signature_bytes = hmac.new(
                self._signing_key,
                manifest_digest.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()

            sig = ImageSignature(
                manifest_digest=manifest_digest,
                signature=signature_bytes,
                key_id=self._key_id,
                signer=signer,
                signed_at=time.time(),
                status=SignatureStatus.SIGNED,
            )

            with self._lock:
                self._signatures[manifest_digest] = sig

            # Store signature as blob
            sig_data = (
                f"manifest:{manifest_digest}\n"
                f"signature:{signature_bytes}\n"
                f"key_id:{self._key_id}\n"
                f"signer:{signer}\n"
            ).encode("utf-8")
            self._blob_store.put(sig_data, OCI_SIGNATURE_MEDIA_TYPE)

            self._emit_event(
                EventType.REG_IMAGE_SIGNED,
                {
                    "manifest_digest": manifest_digest,
                    "signer": signer,
                    "key_id": self._key_id,
                },
            )

            logger.info("Image signed: %s by %s", manifest_digest, signer)
            return sig

        except Exception as e:
            raise ImageSignatureError(manifest_digest, str(e))

    def verify(self, manifest_digest: str) -> ImageSignature:
        """Verify the signature of a manifest.

        Args:
            manifest_digest: The digest of the manifest to verify.

        Returns:
            The ImageSignature with updated status.

        Raises:
            ImageSignatureError: If no signature exists for the manifest.
        """
        with self._lock:
            sig = self._signatures.get(manifest_digest)

        if sig is None:
            raise ImageSignatureError(
                manifest_digest, "No signature found for this manifest"
            )

        try:
            # Recompute HMAC and compare
            expected = hmac.new(
                self._signing_key,
                manifest_digest.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()

            if hmac.compare_digest(sig.signature, expected):
                sig.status = SignatureStatus.VERIFIED
                self._emit_event(
                    EventType.REG_IMAGE_VERIFIED,
                    {"manifest_digest": manifest_digest, "status": "VERIFIED"},
                )
            else:
                sig.status = SignatureStatus.INVALID
                self._emit_event(
                    EventType.REG_IMAGE_VERIFIED,
                    {"manifest_digest": manifest_digest, "status": "INVALID"},
                )

            return copy.deepcopy(sig)

        except Exception as e:
            raise ImageSignatureError(manifest_digest, str(e))

    def get_signature(self, manifest_digest: str) -> Optional[ImageSignature]:
        """Retrieve the signature for a manifest.

        Args:
            manifest_digest: The digest of the manifest.

        Returns:
            The ImageSignature, or None if unsigned.
        """
        with self._lock:
            sig = self._signatures.get(manifest_digest)
            return copy.deepcopy(sig) if sig else None

    @property
    def signed_count(self) -> int:
        """Return the number of signed images."""
        with self._lock:
            return len(self._signatures)

    @property
    def key_id(self) -> str:
        """Return the signing key identifier."""
        return self._key_id

    def _emit_event(self, event_type: EventType, data: Dict[str, Any]) -> None:
        """Emit an event to the event bus if available."""
        if self._event_bus is not None:
            try:
                self._event_bus.publish(event_type, data)
            except Exception:
                pass


# ============================================================
# VulnerabilityScanner — CVE Scanning
# ============================================================


# Built-in vulnerability database for FizzBuzz-specific CVEs
_FIZZBUZZ_CVE_DATABASE: List[VulnerabilityFinding] = [
    VulnerabilityFinding(
        cve_id="CVE-2026-FIZZ-001",
        severity=VulnerabilitySeverity.CRITICAL,
        package="fizzbuzz-core",
        version="<1.0.0",
        fixed_version="1.0.0",
        description="Modulo operation returns incorrect result for divisor=0, "
        "causing infinite loop in the FizzBuzz evaluation pipeline",
    ),
    VulnerabilityFinding(
        cve_id="CVE-2026-FIZZ-002",
        severity=VulnerabilitySeverity.HIGH,
        package="fizzbuzz-rules",
        version="<1.2.0",
        fixed_version="1.2.0",
        description="Rule engine fails to apply composite rules when more "
        "than 15 divisors are configured simultaneously",
    ),
    VulnerabilityFinding(
        cve_id="CVE-2026-FIZZ-003",
        severity=VulnerabilitySeverity.MEDIUM,
        package="fizzbuzz-cache",
        version="<1.1.0",
        fixed_version="1.1.0",
        description="MESI cache coherence protocol allows stale reads under "
        "high contention between evaluation workers",
    ),
    VulnerabilityFinding(
        cve_id="CVE-2026-FIZZ-004",
        severity=VulnerabilitySeverity.LOW,
        package="fizzbuzz-formatter",
        version="<1.3.0",
        fixed_version="1.3.0",
        description="Unicode normalization not applied to Klingon locale "
        "output, causing display artifacts in tlhIngan Hol terminals",
    ),
    VulnerabilityFinding(
        cve_id="CVE-2026-FIZZ-005",
        severity=VulnerabilitySeverity.MEDIUM,
        package="fizzbuzz-blockchain",
        version="<2.0.0",
        fixed_version="2.0.0",
        description="Proof-of-work difficulty adjustment allows block times "
        "to drift below 100ms under reduced mining load",
    ),
    VulnerabilityFinding(
        cve_id="CVE-2026-FIZZ-006",
        severity=VulnerabilitySeverity.HIGH,
        package="fizzbuzz-auth",
        version="<1.4.0",
        fixed_version="1.4.0",
        description="HMAC token validation susceptible to timing side-channel "
        "when comparing token signatures of equal length",
    ),
    VulnerabilityFinding(
        cve_id="CVE-2026-FIZZ-007",
        severity=VulnerabilitySeverity.LOW,
        package="fizzbuzz-metrics",
        version="<1.0.5",
        fixed_version="1.0.5",
        description="Prometheus histogram buckets not aligned with SLO "
        "boundaries, causing misleading percentile calculations",
    ),
    VulnerabilityFinding(
        cve_id="CVE-2026-FIZZ-008",
        severity=VulnerabilitySeverity.CRITICAL,
        package="fizzbuzz-secrets",
        version="<2.1.0",
        fixed_version="2.1.0",
        description="Secrets vault unsealing process logs key shares to "
        "standard output when debug logging is enabled",
    ),
]


class VulnerabilityScanner:
    """Image vulnerability scanner with CVE database.

    Scans image layers for known vulnerabilities by analyzing
    layer metadata against the FizzBuzz vulnerability database.
    Scan results include severity classification, affected
    package information, and remediation guidance.
    """

    def __init__(
        self,
        blob_store: BlobStore,
        cve_database: Optional[List[VulnerabilityFinding]] = None,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._blob_store = blob_store
        self._cve_database = cve_database if cve_database is not None else list(_FIZZBUZZ_CVE_DATABASE)
        self._event_bus = event_bus
        self._scans: Dict[str, VulnerabilityReport] = {}
        self._lock = threading.Lock()
        logger.info(
            "VulnerabilityScanner initialized: %d CVEs in database",
            len(self._cve_database),
        )

    def scan(self, image_ref: str, manifest: OCIManifest) -> VulnerabilityReport:
        """Scan an image for known vulnerabilities.

        Analyzes each layer in the manifest against the CVE
        database, producing a vulnerability report with findings
        classified by severity.

        Args:
            image_ref: Human-readable image reference (e.g., 'fizzbuzz:latest').
            manifest: The OCI manifest describing the image.

        Returns:
            VulnerabilityReport with scan findings.

        Raises:
            VulnerabilityScanError: If scanning encounters a fatal error.
        """
        start_time = time.time()
        report = VulnerabilityReport(
            image_ref=image_ref,
            scanned_at=start_time,
            layers_scanned=len(manifest.layers),
        )

        try:
            for layer_desc in manifest.layers:
                findings = self._scan_layer(layer_desc)
                report.findings.extend(findings)

            report.scan_duration = time.time() - start_time

            with self._lock:
                self._scans[image_ref] = report

            self._emit_event(
                EventType.REG_VULN_SCANNED,
                {
                    "image_ref": image_ref,
                    "total_findings": report.total_count,
                    "critical": report.critical_count,
                    "high": report.high_count,
                    "medium": report.medium_count,
                    "low": report.low_count,
                },
            )

            logger.info(
                "Scan completed: %s — %d findings (%d critical, %d high)",
                image_ref,
                report.total_count,
                report.critical_count,
                report.high_count,
            )
            return report

        except Exception as e:
            raise VulnerabilityScanError(image_ref, str(e))

    def _scan_layer(self, layer_desc: OCIDescriptor) -> List[VulnerabilityFinding]:
        """Scan a single layer for vulnerabilities.

        Uses a deterministic matching algorithm based on the layer
        digest to simulate vulnerability detection.  The distribution
        of findings across severity levels is consistent for a given
        layer digest.

        Args:
            layer_desc: The layer descriptor.

        Returns:
            List of vulnerability findings for this layer.
        """
        findings = []
        digest_hash = int(layer_desc.digest.replace(DIGEST_PREFIX, "")[:8], 16)

        for cve in self._cve_database:
            # Deterministic match based on digest and CVE
            cve_hash = hash(cve.cve_id)
            if (digest_hash ^ cve_hash) % 7 == 0:
                finding = VulnerabilityFinding(
                    cve_id=cve.cve_id,
                    severity=cve.severity,
                    package=cve.package,
                    version=cve.version,
                    fixed_version=cve.fixed_version,
                    description=cve.description,
                    layer_digest=layer_desc.digest,
                )
                findings.append(finding)

        return findings

    def get_report(self, image_ref: str) -> Optional[VulnerabilityReport]:
        """Retrieve the most recent scan report for an image.

        Args:
            image_ref: The image reference.

        Returns:
            The VulnerabilityReport, or None if never scanned.
        """
        with self._lock:
            return copy.deepcopy(self._scans.get(image_ref))

    @property
    def scanned_count(self) -> int:
        """Return the number of images scanned."""
        with self._lock:
            return len(self._scans)

    @property
    def cve_count(self) -> int:
        """Return the number of CVEs in the database."""
        return len(self._cve_database)

    def _emit_event(self, event_type: EventType, data: Dict[str, Any]) -> None:
        """Emit an event to the event bus if available."""
        if self._event_bus is not None:
            try:
                self._event_bus.publish(event_type, data)
            except Exception:
                pass


# ============================================================
# FizzRegistryMiddleware
# ============================================================


class FizzRegistryMiddleware(IMiddleware):
    """Middleware integrating FizzRegistry into the evaluation pipeline.

    Ensures that the image registry is available for image pull
    operations during FizzBuzz evaluation startup.  This middleware
    runs at priority 110, after the overlay filesystem middleware
    (109) has set up the container's layered filesystem.
    """

    def __init__(
        self,
        registry_api: RegistryAPI,
        blob_store: BlobStore,
        image_builder: ImageBuilder,
        garbage_collector: GarbageCollector,
        image_signer: ImageSigner,
        vulnerability_scanner: VulnerabilityScanner,
        event_bus: Optional[Any] = None,
        enable_dashboard: bool = False,
        dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
    ) -> None:
        self._registry_api = registry_api
        self._blob_store = blob_store
        self._image_builder = image_builder
        self._gc = garbage_collector
        self._signer = image_signer
        self._scanner = vulnerability_scanner
        self._event_bus = event_bus
        self._enable_dashboard = enable_dashboard
        self._dashboard_width = dashboard_width
        self._evaluations = 0
        self._errors = 0
        self._dashboard = RegistryDashboard(
            registry_api=registry_api,
            blob_store=blob_store,
            image_builder=image_builder,
            garbage_collector=garbage_collector,
            image_signer=image_signer,
            vulnerability_scanner=vulnerability_scanner,
            width=dashboard_width,
        )

    @property
    def evaluations(self) -> int:
        """Return the number of evaluations processed."""
        return self._evaluations

    @property
    def error_count(self) -> int:
        """Return the number of evaluation errors."""
        return self._errors

    def get_name(self) -> str:
        """Return the middleware name."""
        return "FizzRegistryMiddleware"

    def get_priority(self) -> int:
        """Return the middleware priority."""
        return MIDDLEWARE_PRIORITY

    @property
    def priority(self) -> int:
        """Return the middleware priority (convenience property)."""
        return MIDDLEWARE_PRIORITY

    @property
    def name(self) -> str:
        """Return the middleware name (convenience property)."""
        return "FizzRegistryMiddleware"

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process a FizzBuzz evaluation through the registry layer.

        Increments the evaluation counter and attaches registry
        metadata to the processing context, then delegates to the
        next handler in the middleware pipeline.

        Args:
            context: The processing context.
            next_handler: The next middleware in the pipeline.

        Returns:
            The processed context with registry metadata.

        Raises:
            RegistryMiddlewareError: If middleware processing fails.
        """
        try:
            self._evaluations += 1

            # Attach registry metadata to context
            context.metadata["registry_enabled"] = True
            context.metadata["registry_repos"] = self._registry_api.repo_count
            context.metadata["registry_blobs"] = self._blob_store.blob_count
            context.metadata["registry_signed"] = self._signer.signed_count

            return next_handler(context)

        except Exception as e:
            self._errors += 1
            if isinstance(e, RegistryMiddlewareError):
                raise
            raise RegistryMiddlewareError(
                context.number if hasattr(context, "number") else 0,
                str(e),
            )

    def render_catalog(self) -> str:
        """Render the registry catalog dashboard."""
        return self._dashboard.render_catalog()

    def render_stats(self) -> str:
        """Render registry statistics dashboard."""
        return self._dashboard.render_stats()

    def render_gc_report(self) -> str:
        """Render the last GC report."""
        return self._dashboard.render_gc_report()

    def render_scan_summary(self) -> str:
        """Render vulnerability scan summary."""
        return self._dashboard.render_scan_summary()

    def render_build_stats(self) -> str:
        """Render image builder statistics."""
        return self._dashboard.render_build_stats()


# ============================================================
# RegistryDashboard
# ============================================================


class RegistryDashboard:
    """ASCII dashboard for FizzRegistry metrics and status.

    Renders registry statistics, repository catalog, blob store
    metrics, garbage collection reports, vulnerability scan
    summaries, and image builder cache statistics in formatted
    ASCII output.
    """

    def __init__(
        self,
        registry_api: RegistryAPI,
        blob_store: BlobStore,
        image_builder: ImageBuilder,
        garbage_collector: GarbageCollector,
        image_signer: ImageSigner,
        vulnerability_scanner: VulnerabilityScanner,
        width: int = DEFAULT_DASHBOARD_WIDTH,
    ) -> None:
        self._registry_api = registry_api
        self._blob_store = blob_store
        self._builder = image_builder
        self._gc = garbage_collector
        self._signer = image_signer
        self._scanner = vulnerability_scanner
        self._width = width

    def render_catalog(self) -> str:
        """Render the registry repository catalog.

        Returns:
            Formatted ASCII catalog listing.
        """
        try:
            repos = self._registry_api.catalog()
            lines = []
            lines.append(f"  FizzRegistry Catalog")
            lines.append(f"  {'─' * 40}")
            if not repos:
                lines.append("  (no repositories)")
            else:
                for repo_name in repos:
                    try:
                        repo = self._registry_api.get_repo(repo_name)
                        tags = repo.list_tags()
                        lines.append(
                            f"  {repo_name:<30} {len(tags)} tag(s)"
                        )
                    except RepositoryNotFoundError:
                        lines.append(f"  {repo_name:<30} (unavailable)")
            lines.append(f"  {'─' * 40}")
            lines.append(f"  Total: {len(repos)} repositories")
            return "\n".join(lines)
        except Exception as e:
            raise RegistryDashboardError(str(e))

    def render_stats(self) -> str:
        """Render registry statistics.

        Returns:
            Formatted ASCII statistics.
        """
        try:
            lines = []
            lines.append(f"  FizzRegistry Statistics")
            lines.append(f"  {'─' * 40}")
            lines.append(f"  Repositories: {self._registry_api.repo_count}")
            lines.append(f"  Blobs:        {self._blob_store.blob_count}")
            lines.append(f"  Total Bytes:  {self._blob_store.total_bytes}")
            lines.append(f"  Pushes:       {self._blob_store.total_pushes}")
            lines.append(f"  Pulls:        {self._blob_store.total_pulls}")
            lines.append(f"  GC Runs:      {self._gc.gc_runs}")
            lines.append(f"  Reclaimed:    {self._gc.total_bytes_reclaimed} bytes")
            lines.append(f"  Signed:       {self._signer.signed_count}")
            lines.append(f"  Scanned:      {self._scanner.scanned_count}")
            return "\n".join(lines)
        except Exception as e:
            raise RegistryDashboardError(str(e))

    def render_gc_report(self) -> str:
        """Render the most recent garbage collection report.

        Returns:
            Formatted ASCII GC report.
        """
        try:
            lines = []
            lines.append(f"  Garbage Collection Report")
            lines.append(f"  {'─' * 40}")
            lines.append(f"  GC Runs:      {self._gc.gc_runs}")
            lines.append(f"  Total Reclaimed: {self._gc.total_bytes_reclaimed} bytes")
            return "\n".join(lines)
        except Exception as e:
            raise RegistryDashboardError(str(e))

    def render_scan_summary(self) -> str:
        """Render vulnerability scan summary.

        Returns:
            Formatted ASCII scan summary.
        """
        try:
            lines = []
            lines.append(f"  Vulnerability Scan Summary")
            lines.append(f"  {'─' * 40}")
            lines.append(f"  Images Scanned: {self._scanner.scanned_count}")
            lines.append(f"  CVEs in DB:     {self._scanner.cve_count}")
            return "\n".join(lines)
        except Exception as e:
            raise RegistryDashboardError(str(e))

    def render_build_stats(self) -> str:
        """Render image builder statistics.

        Returns:
            Formatted ASCII build statistics.
        """
        try:
            total = self._builder.cache_hits + self._builder.cache_misses
            hit_rate = (
                (self._builder.cache_hits / total * 100.0) if total > 0 else 0.0
            )
            lines = []
            lines.append(f"  Image Builder Statistics")
            lines.append(f"  {'─' * 40}")
            lines.append(f"  Builds:       {self._builder.builds_completed}")
            lines.append(f"  Cache Hits:   {self._builder.cache_hits}")
            lines.append(f"  Cache Misses: {self._builder.cache_misses}")
            lines.append(f"  Hit Rate:     {hit_rate:.1f}%")
            lines.append(f"  Cache Size:   {self._builder.cache_size}")
            return "\n".join(lines)
        except Exception as e:
            raise RegistryDashboardError(str(e))


# ============================================================
# Factory Function
# ============================================================


def create_fizzregistry_subsystem(
    max_blobs: int = DEFAULT_MAX_BLOBS,
    max_repos: int = DEFAULT_MAX_REPOS,
    max_tags: int = DEFAULT_MAX_TAGS,
    gc_grace_period: float = DEFAULT_GC_GRACE_PERIOD,
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
    enable_dashboard: bool = False,
    event_bus: Optional[Any] = None,
) -> tuple:
    """Create and wire the complete FizzRegistry subsystem.

    Factory function that instantiates the BlobStore, RegistryAPI,
    ImageBuilder, GarbageCollector, ImageSigner, VulnerabilityScanner,
    and FizzRegistryMiddleware, ready for integration into the
    FizzBuzz evaluation pipeline.

    Args:
        max_blobs: Maximum blobs in the content store.
        max_repos: Maximum repositories in the registry.
        max_tags: Maximum tags per repository.
        gc_grace_period: GC grace period in seconds.
        dashboard_width: ASCII dashboard width.
        enable_dashboard: Whether to enable post-execution dashboard.
        event_bus: Optional event bus for lifecycle events.

    Returns:
        Tuple of (RegistryAPI, FizzRegistryMiddleware).
    """
    blob_store = BlobStore(
        max_blobs=max_blobs,
        event_bus=event_bus,
    )

    registry_api = RegistryAPI(
        blob_store=blob_store,
        max_repos=max_repos,
        max_tags=max_tags,
        event_bus=event_bus,
    )

    image_builder = ImageBuilder(
        blob_store=blob_store,
        registry_api=registry_api,
        event_bus=event_bus,
    )

    gc = GarbageCollector(
        blob_store=blob_store,
        registry_api=registry_api,
        grace_period=gc_grace_period,
        event_bus=event_bus,
    )

    signer = ImageSigner(
        blob_store=blob_store,
        event_bus=event_bus,
    )

    scanner = VulnerabilityScanner(
        blob_store=blob_store,
        event_bus=event_bus,
    )

    middleware = FizzRegistryMiddleware(
        registry_api=registry_api,
        blob_store=blob_store,
        image_builder=image_builder,
        garbage_collector=gc,
        image_signer=signer,
        vulnerability_scanner=scanner,
        event_bus=event_bus,
        enable_dashboard=enable_dashboard,
        dashboard_width=dashboard_width,
    )

    logger.info(
        "FizzRegistry subsystem created: max_blobs=%d, max_repos=%d, "
        "max_tags=%d, gc_grace=%.1fs",
        max_blobs,
        max_repos,
        max_tags,
        gc_grace_period,
    )

    return registry_api, middleware
