# Plan: FizzImage -- Official Container Image Catalog

**Module**: `enterprise_fizzbuzz/infrastructure/fizzimage.py` (~2,800 lines)
**Tests**: `tests/test_fizzimage.py` (~400 lines)
**Re-export stub**: `fizzimage.py` (root)

---

## 1. Class Inventory

### 1.1 ImageCatalog

The central registry of all official container image definitions for the Enterprise FizzBuzz Platform. Manages the complete lifecycle from image definition through build, scan, version, and publish.

```python
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
    ) -> None: ...

    def register_image(self, spec: ImageSpec) -> ImageManifest: ...
    def build_image(self, image_name: str) -> ImageManifest: ...
    def build_all(self) -> List[ImageManifest]: ...
    def get_image(self, image_name: str) -> ImageManifest: ...
    def list_images(self) -> List[ImageManifest]: ...
    def inspect_image(self, image_name: str) -> Dict[str, Any]: ...
    def get_dependencies(self, image_name: str) -> List[str]: ...
    def scan_all(self) -> List[ScanResult]: ...
    def remove_image(self, image_name: str) -> None: ...
    def get_stats(self) -> CatalogStats: ...
    def _resolve_build_order(self) -> List[str]: ...
    def _emit_event(self, event_type: EventType, data: Dict[str, Any]) -> None: ...
```

### 1.2 BaseImageBuilder

Constructs the `fizzbuzz-base` foundation image containing the Python runtime, domain layer, and core utilities. Enforces the Clean Architecture dependency rule at the image level by verifying no infrastructure imports leak into the base image.

```python
class BaseImageBuilder:
    """Builds the fizzbuzz-base foundation image.

    Constructs the minimal base image from its FizzFile definition,
    executing each instruction as an overlay layer via FizzOverlay
    and pushing the result to FizzRegistry.  Validates that the base
    image contains no infrastructure module dependencies.
    """

    def __init__(
        self,
        catalog: ImageCatalog,
        base_image_name: str = DEFAULT_BASE_IMAGE,
        python_version: str = DEFAULT_PYTHON_VERSION,
    ) -> None: ...

    def build(self) -> ImageManifest: ...
    def generate_fizzfile(self) -> str: ...
    def validate_dependency_rule(self, manifest: ImageManifest) -> bool: ...
    def _create_base_layers(self) -> List[LayerDescriptor]: ...
    def _compute_layer_digest(self, content: bytes) -> str: ...
```

### 1.3 EvalImageBuilder

Constructs evaluation-profile images that extend `fizzbuzz-base` with the application layer and minimal infrastructure for FizzBuzz evaluation. Supports four variant profiles: standard, configurable, cached, and ML.

```python
class EvalImageBuilder:
    """Builds fizzbuzz-eval profile images.

    Extends fizzbuzz-base with the application layer (service builder,
    rule factories, strategy ports) and the minimal infrastructure
    required for each evaluation profile.  Each profile is independently
    versioned and tagged.
    """

    def __init__(
        self,
        catalog: ImageCatalog,
        base_builder: BaseImageBuilder,
    ) -> None: ...

    def build_profile(self, profile: ImageProfile) -> ImageManifest: ...
    def build_all_profiles(self) -> List[ImageManifest]: ...
    def generate_fizzfile(self, profile: ImageProfile) -> str: ...
    def _get_profile_dependencies(self, profile: ImageProfile) -> List[str]: ...
    def _get_profile_entrypoint(self, profile: ImageProfile) -> List[str]: ...
```

### 1.4 SubsystemImageGenerator

Generates FizzFile definitions and builds container images for each of the 116 infrastructure modules. Uses AST-based import analysis to determine the minimal dependency set for each module, resolves transitive dependencies, detects circular dependency groups, and groups related subsystems into composite images.

```python
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
    ) -> None: ...

    def analyze_module(self, module_name: str) -> List[str]: ...
    def generate_fizzfile(self, module_name: str) -> str: ...
    def build_subsystem_image(self, module_name: str) -> ImageManifest: ...
    def build_all_subsystem_images(self) -> List[ImageManifest]: ...
    def detect_circular_groups(self) -> List[List[str]]: ...
    def get_image_groups(self) -> Dict[str, List[str]]: ...
    def _resolve_transitive_deps(self, module_name: str) -> Set[str]: ...
    def _ast_extract_imports(self, module_name: str) -> List[str]: ...
```

### 1.5 InitContainerBuilder

Builds init container images for pre-flight setup operations: configuration injection, schema migration, and secret population. Init containers run to completion before the main container starts.

```python
class InitContainerBuilder:
    """Builds init container images for pre-flight setup.

    Creates specialized images for configuration loading, schema
    migration, and secret injection.  Init containers execute
    before the main container and share data via volumes.
    """

    def __init__(
        self,
        catalog: ImageCatalog,
        base_image_name: str = DEFAULT_BASE_IMAGE,
    ) -> None: ...

    def build_config_init(self) -> ImageManifest: ...
    def build_schema_init(self) -> ImageManifest: ...
    def build_secrets_init(self) -> ImageManifest: ...
    def build_all_inits(self) -> List[ImageManifest]: ...
    def generate_fizzfile(self, init_type: str) -> str: ...
    def get_init_spec(self, init_type: str) -> InitContainerSpec: ...
```

### 1.6 SidecarImageBuilder

Builds sidecar container images for cross-cutting concerns that run alongside the main container: structured logging forwarding, Prometheus-compatible metrics export, OpenTelemetry span collection, and service mesh data plane proxy.

```python
class SidecarImageBuilder:
    """Builds sidecar container images for cross-cutting concerns.

    Creates specialized images for logging, metrics, tracing, and
    proxy sidecars.  Sidecar containers run alongside the main
    container and communicate via shared volumes or Unix sockets.
    """

    def __init__(
        self,
        catalog: ImageCatalog,
        base_image_name: str = DEFAULT_BASE_IMAGE,
    ) -> None: ...

    def build_log_sidecar(self) -> ImageManifest: ...
    def build_metrics_sidecar(self) -> ImageManifest: ...
    def build_trace_sidecar(self) -> ImageManifest: ...
    def build_proxy_sidecar(self) -> ImageManifest: ...
    def build_all_sidecars(self) -> List[ImageManifest]: ...
    def generate_fizzfile(self, sidecar_type: str) -> str: ...
```

### 1.7 ImageMetadata

Manages standardized OCI annotation labels and platform-specific metadata for every image in the catalog. Ensures consistent labeling across all images.

```python
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
    ) -> None: ...

    def to_oci_annotations(self) -> Dict[str, str]: ...
    def to_platform_labels(self) -> Dict[str, str]: ...
    def to_dict(self) -> Dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ImageMetadata: ...
```

### 1.8 MultiArchBuilder

Produces OCI image indexes (manifest lists) for each image, supporting multiple target architectures. A single image reference resolves to the correct platform-specific manifest at pull time.

```python
class MultiArchBuilder:
    """Produces OCI image indexes for multi-architecture support.

    Generates manifest lists that map a single image reference
    (e.g., fizzbuzz-eval:1.0.0) to platform-specific manifests
    for linux/amd64, linux/arm64, and fizzbuzz/vm architectures.
    """

    def __init__(
        self,
        supported_platforms: Optional[List[str]] = None,
    ) -> None: ...

    def build_index(self, image_name: str, manifests: Dict[str, ImageManifest]) -> ImageIndex: ...
    def resolve_platform(self, index: ImageIndex, platform: str) -> ImageManifest: ...
    def list_platforms(self, index: ImageIndex) -> List[str]: ...
    def _create_platform_descriptor(self, platform: str, manifest: ImageManifest) -> Dict[str, Any]: ...
```

### 1.9 CatalogScanner

Runs vulnerability scanning against every image in the catalog at build time. Images with CRITICAL severity vulnerabilities are blocked from the catalog. Scan results are stored as OCI artifacts attached to image manifests.

```python
class CatalogScanner:
    """Vulnerability scanner for the official image catalog.

    Scans each image's layers and dependencies for known
    vulnerabilities.  Assigns severity levels (CRITICAL, HIGH,
    MEDIUM, LOW, NEGLIGIBLE) and blocks images that exceed the
    configured severity threshold from entering the catalog.
    """

    def __init__(
        self,
        severity_threshold: str = DEFAULT_SCAN_SEVERITY_THRESHOLD,
        vulnerability_db_size: int = DEFAULT_VULN_DB_SIZE,
    ) -> None: ...

    def scan_image(self, manifest: ImageManifest) -> ScanResult: ...
    def scan_catalog(self, catalog: ImageCatalog) -> List[ScanResult]: ...
    def is_admissible(self, result: ScanResult) -> bool: ...
    def generate_report(self, result: ScanResult) -> str: ...
    def _check_layer(self, layer: LayerDescriptor) -> List[VulnerabilityEntry]: ...
    def _check_dependencies(self, dependencies: List[str]) -> List[VulnerabilityEntry]: ...
    def _severity_rank(self, severity: ScanSeverity) -> int: ...
```

### 1.10 ImageVersioner

Assigns semantic versions to images based on the platform's release history. Manages tag assignment including `latest`, semantic version, and Git commit SHA tags.

```python
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
    ) -> None: ...

    def get_version(self, image_name: str) -> VersionTag: ...
    def bump_version(self, image_name: str, bump: VersionBump) -> VersionTag: ...
    def tag_image(self, image_name: str, commit_sha: str = "") -> List[str]: ...
    def list_tags(self, image_name: str) -> List[str]: ...
    def _parse_version(self, version_str: str) -> Tuple[int, int, int]: ...
    def _format_version(self, major: int, minor: int, patch: int) -> str: ...
```

### 1.11 FizzImageMiddleware

Middleware that intercepts each FizzBuzz evaluation to record which image would serve the evaluation and enriches the processing context with image catalog metadata. Priority 113.

```python
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
    ) -> None: ...

    def get_name(self) -> str: ...
    def get_priority(self) -> int: ...
    @property
    def priority(self) -> int: ...
    @property
    def name(self) -> str: ...
    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext: ...
    def render_dashboard(self) -> str: ...
    def render_catalog(self) -> str: ...
    def render_image_detail(self, image_name: str) -> str: ...
    def render_dependencies(self, image_name: str) -> str: ...
    def render_scan_results(self) -> str: ...
    def render_stats(self) -> str: ...
```

### 1.12 FizzImageDashboard

ASCII dashboard rendering for the image catalog, providing views of the full catalog inventory, individual image details, dependency graphs, vulnerability scan results, and build statistics.

```python
class FizzImageDashboard:
    """ASCII dashboard for the FizzImage catalog.

    Renders catalog inventory, image details, dependency graphs,
    scan results, and build statistics in formatted ASCII tables.
    """

    def __init__(self, width: int = DEFAULT_DASHBOARD_WIDTH) -> None: ...

    def render(self, catalog: ImageCatalog) -> str: ...
    def render_catalog(self, catalog: ImageCatalog) -> str: ...
    def render_image_detail(self, catalog: ImageCatalog, image_name: str) -> str: ...
    def render_dependencies(self, catalog: ImageCatalog, image_name: str) -> str: ...
    def render_scan_results(self, catalog: ImageCatalog) -> str: ...
    def render_build_history(self, catalog: ImageCatalog) -> str: ...
    def _center(self, text: str) -> str: ...
    def _format_bytes(self, size: int) -> str: ...
    def _format_severity(self, severity: ScanSeverity) -> str: ...
```

---

## 2. Enums

```python
class ImageType(Enum):
    """Classification of images in the official catalog."""
    BASE = "base"                   # Foundation images (fizzbuzz-base)
    EVAL = "eval"                   # Evaluation runtime images (fizzbuzz-eval)
    SUBSYSTEM = "subsystem"         # Per-module infrastructure images
    INIT = "init"                   # Init container images (pre-flight setup)
    SIDECAR = "sidecar"             # Sidecar container images (cross-cutting)
    COMPOSITE = "composite"         # Grouped subsystem images (fizzbuzz-data, etc.)


class ImageProfile(Enum):
    """Evaluation image profiles."""
    STANDARD = "standard"           # Classic 3/5 rules
    CONFIGURABLE = "configurable"   # YAML-driven rules
    CACHED = "cached"               # With MESI cache coherence
    ML = "ml"                       # With neural network classification


class ArchPlatform(Enum):
    """Supported target architectures for multi-arch builds."""
    LINUX_AMD64 = "linux/amd64"
    LINUX_ARM64 = "linux/arm64"
    FIZZBUZZ_VM = "fizzbuzz/vm"     # Platform bytecode VM architecture


class ScanSeverity(Enum):
    """Vulnerability severity levels for catalog scanning."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NEGLIGIBLE = "negligible"


class VersionBump(Enum):
    """Semantic version bump classification."""
    MAJOR = "major"                 # Domain layer changes
    MINOR = "minor"                 # Functionality changes
    PATCH = "patch"                 # Configuration-only changes


class BuildStatus(Enum):
    """Status of an image build operation."""
    PENDING = "pending"
    BUILDING = "building"
    SCANNING = "scanning"
    PUBLISHING = "publishing"
    COMPLETE = "complete"
    FAILED = "failed"
    BLOCKED = "blocked"             # Blocked by scan policy


class InitPolicy(Enum):
    """Failure policy for init containers."""
    RESTART_ON_FAILURE = "restart"
    ABORT_ON_FAILURE = "abort"
    IGNORE_FAILURE = "ignore"
```

---

## 3. Data Classes

```python
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
    target_platforms: List[ArchPlatform] = field(default_factory=lambda: list(ArchPlatform))
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
```

---

## 4. Constants

```python
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

# Subsystem image groups — related modules packaged together
IMAGE_GROUPS = {
    "fizzbuzz-data": ["sqlite_backend", "filesystem_backend", "memory_backend"],
    "fizzbuzz-network": ["fizztcp", "fizzdns", "fizzproxy", "service_mesh"],
    "fizzbuzz-security": ["auth", "capability_security", "secrets_vault", "compliance"],
    "fizzbuzz-observability": ["fizzotel", "fizzflame", "sla_monitor", "metrics", "fizzcorr"],
}
"""Subsystem groupings for composite images."""
```

---

## 5. Exception Classes

All exceptions inherit from `FizzImageError(FizzBuzzError)` with error codes `EFP-IMG01` through `EFP-IMG20`. Each follows the pattern:
```python
def __init__(self, reason: str) -> None:
    super().__init__(reason)
    self.error_code = "EFP-IMG##"
    self.context = {"reason": reason}
```

Add to `enterprise_fizzbuzz/domain/exceptions.py`:

```python
# ── FizzImage: Official Container Image Catalog ──────────────

class FizzImageError(FizzBuzzError):
    """Base exception for FizzImage container image catalog errors."""
    # EFP-IMG00

class CatalogInitializationError(FizzImageError):
    """Raised when the image catalog fails to initialize."""
    # EFP-IMG01

class ImageNotFoundError(FizzImageError):
    """Raised when a referenced image does not exist in the catalog."""
    # EFP-IMG02

class ImageAlreadyExistsError(FizzImageError):
    """Raised when attempting to register a duplicate image name."""
    # EFP-IMG03

class ImageBuildError(FizzImageError):
    """Raised when image construction fails during FizzFile execution."""
    # EFP-IMG04

class ImageBuildDependencyError(FizzImageError):
    """Raised when an image's base or dependency image is missing."""
    # EFP-IMG05

class FizzFileGenerationError(FizzImageError):
    """Raised when FizzFile DSL generation fails for a module."""
    # EFP-IMG06

class DependencyRuleViolationError(FizzImageError):
    """Raised when an image violates the Clean Architecture dependency rule."""
    # EFP-IMG07

class LayerCreationError(FizzImageError):
    """Raised when a filesystem layer cannot be constructed."""
    # EFP-IMG08

class DigestMismatchError(FizzImageError):
    """Raised when a layer's computed digest does not match its expected digest."""
    # EFP-IMG09

class VulnerabilityScanError(FizzImageError):
    """Raised when the vulnerability scanner encounters an operational failure."""
    # EFP-IMG10

class ImageBlockedByScanError(FizzImageError):
    """Raised when an image is blocked from the catalog due to scan policy violations."""
    # EFP-IMG11

class VersionConflictError(FizzImageError):
    """Raised when a version tag assignment conflicts with an existing version."""
    # EFP-IMG12

class MultiArchBuildError(FizzImageError):
    """Raised when multi-architecture manifest index generation fails."""
    # EFP-IMG13

class PlatformResolutionError(FizzImageError):
    """Raised when a platform cannot be resolved from a manifest index."""
    # EFP-IMG14

class InitContainerBuildError(FizzImageError):
    """Raised when an init container image build fails."""
    # EFP-IMG15

class SidecarBuildError(FizzImageError):
    """Raised when a sidecar container image build fails."""
    # EFP-IMG16

class CatalogCapacityError(FizzImageError):
    """Raised when the catalog exceeds its maximum image capacity."""
    # EFP-IMG17

class CircularDependencyError(FizzImageError):
    """Raised when circular dependencies are detected in subsystem imports."""
    # EFP-IMG18

class MetadataValidationError(FizzImageError):
    """Raised when image metadata fails OCI annotation validation."""
    # EFP-IMG19

class FizzImageMiddlewareError(FizzImageError):
    """Raised when the FizzImage middleware fails to process an evaluation."""
    # EFP-IMG20 — takes (evaluation_number: int, reason: str)
    def __init__(self, evaluation_number: int, reason: str) -> None:
        super().__init__(
            f"FizzImage middleware error at evaluation {evaluation_number}: {reason}"
        )
        self.error_code = "EFP-IMG20"
        self.context = {"evaluation_number": evaluation_number, "reason": reason}
        self.evaluation_number = evaluation_number
```

---

## 6. EventType Entries

Add to `enterprise_fizzbuzz/domain/models.py` in the `EventType` enum:

```python
    # FizzImage — Official Container Image Catalog events
    FIZZIMAGE_CATALOG_LOADED = auto()
    FIZZIMAGE_CATALOG_STATS = auto()
    FIZZIMAGE_IMAGE_REGISTERED = auto()
    FIZZIMAGE_BASE_BUILT = auto()
    FIZZIMAGE_EVAL_BUILT = auto()
    FIZZIMAGE_SUBSYSTEM_GENERATED = auto()
    FIZZIMAGE_INIT_BUILT = auto()
    FIZZIMAGE_SIDECAR_BUILT = auto()
    FIZZIMAGE_MULTI_ARCH_INDEXED = auto()
    FIZZIMAGE_SCAN_STARTED = auto()
    FIZZIMAGE_SCAN_COMPLETED = auto()
    FIZZIMAGE_SCAN_BLOCKED = auto()
    FIZZIMAGE_VERSION_BUMPED = auto()
    FIZZIMAGE_IMAGE_REMOVED = auto()
    FIZZIMAGE_BUILD_ALL_STARTED = auto()
    FIZZIMAGE_BUILD_ALL_COMPLETED = auto()
```

16 event types covering the full image catalog lifecycle.

---

## 7. Config Properties

Add to `enterprise_fizzbuzz/infrastructure/config.py` (ConfigurationManager class):

```python
    @property
    def fizzimage_enabled(self) -> bool:
        """Whether the FizzImage container image catalog is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzimage", {}).get("enabled", False)

    @property
    def fizzimage_base_image_name(self) -> str:
        """Name of the base image in the catalog."""
        self._ensure_loaded()
        return self._raw_config.get("fizzimage", {}).get("base_image_name", "fizzbuzz-base")

    @property
    def fizzimage_registry_url(self) -> str:
        """Registry URL for image push/pull operations."""
        self._ensure_loaded()
        return self._raw_config.get("fizzimage", {}).get("registry_url", "registry.fizzbuzz.internal:5000")

    @property
    def fizzimage_scan_severity_threshold(self) -> str:
        """Maximum vulnerability severity that blocks image admission."""
        self._ensure_loaded()
        return self._raw_config.get("fizzimage", {}).get("scan_severity_threshold", "critical")

    @property
    def fizzimage_max_catalog_size(self) -> int:
        """Maximum number of images in the catalog."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzimage", {}).get("max_catalog_size", 1024))

    @property
    def fizzimage_python_version(self) -> str:
        """Python version installed in the base image."""
        self._ensure_loaded()
        return self._raw_config.get("fizzimage", {}).get("python_version", "3.12")

    @property
    def fizzimage_initial_version(self) -> str:
        """Initial semantic version for new images."""
        self._ensure_loaded()
        return self._raw_config.get("fizzimage", {}).get("initial_version", "1.0.0")

    @property
    def fizzimage_vuln_db_size(self) -> int:
        """Number of entries in the simulated vulnerability database."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzimage", {}).get("vuln_db_size", 512))

    @property
    def fizzimage_module_base_path(self) -> str:
        """Base Python package path for infrastructure modules."""
        self._ensure_loaded()
        return self._raw_config.get("fizzimage", {}).get("module_base_path", "enterprise_fizzbuzz.infrastructure")

    @property
    def fizzimage_dashboard_width(self) -> int:
        """Width of the FizzImage ASCII dashboard."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzimage", {}).get("dashboard", {}).get("width", 72))
```

---

## 8. YAML Config Section

Add to `config.yaml`:

```yaml
fizzimage:
  enabled: false                          # Master switch — opt-in via --fizzimage
  base_image_name: fizzbuzz-base          # Name of the foundation base image
  registry_url: "registry.fizzbuzz.internal:5000"  # Registry for push/pull
  scan_severity_threshold: critical       # Block images with this severity or above
  max_catalog_size: 1024                  # Maximum images in the catalog
  python_version: "3.12"                  # Python version in base image
  initial_version: "1.0.0"               # Default initial semantic version
  vuln_db_size: 512                       # Simulated vulnerability database entries
  module_base_path: "enterprise_fizzbuzz.infrastructure"
  dashboard:
    width: 72                             # ASCII dashboard width
```

---

## 9. CLI Flags

Add to `__main__.py` argparse section:

```python
    # FizzImage — Official Container Image Catalog
    parser.add_argument(
        "--fizzimage",
        action="store_true",
        default=False,
        help="Enable FizzImage: official container image catalog with base, eval, subsystem, init, and sidecar images",
    )
    parser.add_argument(
        "--fizzimage-catalog",
        action="store_true",
        default=False,
        help="Display the full image catalog with versions, sizes, and scan status",
    )
    parser.add_argument(
        "--fizzimage-build",
        type=str,
        default="",
        help="Build a specific catalog image by name",
    )
    parser.add_argument(
        "--fizzimage-build-all",
        action="store_true",
        default=False,
        help="Build the entire image catalog (base, eval, subsystem, init, sidecar)",
    )
    parser.add_argument(
        "--fizzimage-inspect",
        type=str,
        default="",
        help="Inspect an image: show layers, metadata, and vulnerability report",
    )
    parser.add_argument(
        "--fizzimage-deps",
        type=str,
        default="",
        help="Display the dependency graph for a catalog image",
    )
    parser.add_argument(
        "--fizzimage-scan",
        action="store_true",
        default=False,
        help="Run vulnerability scanning against all catalog images",
    )
```

---

## 10. `__main__.py` Wiring

### Import block (top of file, with other infrastructure imports):

```python
from enterprise_fizzbuzz.infrastructure.fizzimage import (
    ImageCatalog,
    FizzImageDashboard,
    FizzImageMiddleware,
    create_fizzimage_subsystem,
)
```

### Argparse block:
See Section 9 above.

### Initialization block (in the subsystem wiring section):

```python
    # FizzImage — Official Container Image Catalog
    fizzimage_catalog_instance = None
    fizzimage_middleware_instance = None

    if args.fizzimage or args.fizzimage_catalog or args.fizzimage_build or args.fizzimage_build_all or args.fizzimage_inspect or args.fizzimage_deps or args.fizzimage_scan:
        fizzimage_catalog_instance, fizzimage_middleware_instance = create_fizzimage_subsystem(
            registry_url=config.fizzimage_registry_url,
            base_image_name=config.fizzimage_base_image_name,
            scan_severity_threshold=config.fizzimage_scan_severity_threshold,
            max_catalog_size=config.fizzimage_max_catalog_size,
            python_version=config.fizzimage_python_version,
            initial_version=config.fizzimage_initial_version,
            vuln_db_size=config.fizzimage_vuln_db_size,
            module_base_path=config.fizzimage_module_base_path,
            dashboard_width=config.fizzimage_dashboard_width,
            enable_dashboard=args.fizzimage_catalog,
            event_bus=event_bus if 'event_bus' in dir() else None,
        )

        builder.with_middleware(fizzimage_middleware_instance)

        if not args.quiet:
            print(
                "\n"
                "  +----------------------------------------------------------+\n"
                "  | FIZZIMAGE: OFFICIAL CONTAINER IMAGE CATALOG              |\n"
                f"  | Registry: {config.fizzimage_registry_url:<47}|\n"
                f"  | Base: {config.fizzimage_base_image_name:<14} Scan Threshold: {config.fizzimage_scan_severity_threshold:<14}|\n"
                "  +----------------------------------------------------------+\n"
                "  | Official image catalog for the Enterprise FizzBuzz       |\n"
                "  | Platform — base, eval, subsystem, init, and sidecar     |\n"
                "  +----------------------------------------------------------+\n"
            )

        # Handle build commands
        if args.fizzimage_build:
            fizzimage_catalog_instance.build_image(args.fizzimage_build)
        if args.fizzimage_build_all:
            fizzimage_catalog_instance.build_all()
```

### Post-execution rendering block:

```python
    # FizzImage Catalog (post-execution)
    if args.fizzimage_catalog and fizzimage_middleware_instance is not None:
        print()
        print(fizzimage_middleware_instance.render_catalog())
    elif args.fizzimage_catalog and fizzimage_middleware_instance is None:
        print("\n  FizzImage not enabled. Use --fizzimage to enable.\n")

    # FizzImage Inspect (post-execution)
    if args.fizzimage_inspect and fizzimage_middleware_instance is not None:
        print()
        print(fizzimage_middleware_instance.render_image_detail(args.fizzimage_inspect))
    elif args.fizzimage_inspect and fizzimage_middleware_instance is None:
        print("\n  FizzImage not enabled. Use --fizzimage to enable.\n")

    # FizzImage Dependencies (post-execution)
    if args.fizzimage_deps and fizzimage_middleware_instance is not None:
        print()
        print(fizzimage_middleware_instance.render_dependencies(args.fizzimage_deps))
    elif args.fizzimage_deps and fizzimage_middleware_instance is None:
        print("\n  FizzImage not enabled. Use --fizzimage to enable.\n")

    # FizzImage Scan Results (post-execution)
    if args.fizzimage_scan and fizzimage_middleware_instance is not None:
        print()
        print(fizzimage_middleware_instance.render_scan_results())
    elif args.fizzimage_scan and fizzimage_middleware_instance is None:
        print("\n  FizzImage not enabled. Use --fizzimage to enable.\n")
```

---

## 11. Middleware

**Class**: `FizzImageMiddleware(IMiddleware)`
**Priority**: 113 (one above FizzContainerd at 112)
**Constant**: `MIDDLEWARE_PRIORITY = 113`

The middleware resolves which catalog image would serve each evaluation based on the active configuration (standard, configurable, cached, or ML profile), enriches the processing context with image reference, version, layer count, and total size metadata, then delegates to the next handler. On failure, raises `FizzImageMiddlewareError` with the evaluation number and reason.

---

## 12. Factory Function

```python
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

    Returns:
        Tuple of (ImageCatalog, FizzImageMiddleware).
    """
```

---

## 13. Test Classes

File: `tests/test_fizzimage.py` (~400 lines)

| Test Class | Target | Approx Tests |
|---|---|---|
| `TestConstants` | All module constants | 14 |
| `TestImageType` | ImageType enum | 6 |
| `TestImageProfile` | ImageProfile enum | 4 |
| `TestArchPlatform` | ArchPlatform enum | 3 |
| `TestScanSeverity` | ScanSeverity enum | 5 |
| `TestVersionBump` | VersionBump enum | 3 |
| `TestBuildStatus` | BuildStatus enum | 7 |
| `TestInitPolicy` | InitPolicy enum | 3 |
| `TestImageSpec` | ImageSpec dataclass | 5 |
| `TestImageManifest` | ImageManifest dataclass | 5 |
| `TestLayerDescriptor` | LayerDescriptor dataclass | 4 |
| `TestScanResult` | ScanResult dataclass | 5 |
| `TestVulnerabilityEntry` | VulnerabilityEntry dataclass | 4 |
| `TestVersionTag` | VersionTag dataclass | 5 |
| `TestInitContainerSpec` | InitContainerSpec dataclass | 4 |
| `TestImageIndex` | ImageIndex dataclass | 4 |
| `TestCatalogStats` | CatalogStats dataclass | 5 |
| `TestImageMetadata` | ImageMetadata class | 8 |
| `TestImageCatalog` | ImageCatalog class | 18 |
| `TestBaseImageBuilder` | BaseImageBuilder class | 8 |
| `TestEvalImageBuilder` | EvalImageBuilder class | 10 |
| `TestSubsystemImageGenerator` | SubsystemImageGenerator class | 12 |
| `TestInitContainerBuilder` | InitContainerBuilder class | 8 |
| `TestSidecarImageBuilder` | SidecarImageBuilder class | 8 |
| `TestMultiArchBuilder` | MultiArchBuilder class | 6 |
| `TestCatalogScanner` | CatalogScanner class | 10 |
| `TestImageVersioner` | ImageVersioner class | 8 |
| `TestFizzImageDashboard` | FizzImageDashboard class | 10 |
| `TestFizzImageMiddleware` | FizzImageMiddleware class | 12 |
| `TestFactory` | create_fizzimage_subsystem | 5 |
| `TestExceptions` | All 21 exception classes | 21 |
| `TestEventTypes` | EventType entries | 16 |
| **Total** | | **~244** |

---

## 14. Re-export Stub

File: `fizzimage.py` (project root)

```python
"""Backward-compatible re-export stub for fizzimage."""
from enterprise_fizzbuzz.infrastructure.fizzimage import *  # noqa: F401,F403
```

---

## Implementation Order

1. Add exception classes to `domain/exceptions.py`
2. Add EventType entries to `domain/models.py`
3. Create `enterprise_fizzbuzz/infrastructure/fizzimage.py` with all classes
4. Add config properties to `enterprise_fizzbuzz/infrastructure/config.py`
5. Add YAML config section to `config.yaml`
6. Add CLI flags and wiring to `__main__.py`
7. Create re-export stub `fizzimage.py`
8. Create `tests/test_fizzimage.py`
