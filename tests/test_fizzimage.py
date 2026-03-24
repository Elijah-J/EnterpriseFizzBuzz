"""
Tests for enterprise_fizzbuzz.infrastructure.fizzimage

Comprehensive test suite for the FizzImage Official Container Image
Catalog: enums, data classes, exception hierarchy, core classes
(ImageCatalog, BaseImageBuilder, EvalImageBuilder, SubsystemImageGenerator,
InitContainerBuilder, SidecarImageBuilder, ImageMetadata, MultiArchBuilder,
CatalogScanner, ImageVersioner), middleware, dashboard, and factory.
"""

import hashlib
from dataclasses import fields
from datetime import datetime, timezone

import pytest

from enterprise_fizzbuzz.infrastructure.fizzimage import (
    # Constants
    FIZZIMAGE_VERSION,
    FIZZIMAGE_API_VERSION,
    DEFAULT_REGISTRY_URL,
    DEFAULT_BASE_IMAGE,
    DEFAULT_PYTHON_VERSION,
    DEFAULT_MODULE_BASE_PATH,
    DEFAULT_SCAN_SEVERITY_THRESHOLD,
    DEFAULT_VULN_DB_SIZE,
    DEFAULT_INITIAL_VERSION,
    DEFAULT_MAX_CATALOG_SIZE,
    DEFAULT_DASHBOARD_WIDTH,
    MIDDLEWARE_PRIORITY,
    SUPPORTED_PLATFORMS,
    IMAGE_AUTHOR,
    IMAGE_GROUPS,
    # Event type constants
    FIZZIMAGE_CATALOG_LOADED,
    FIZZIMAGE_CATALOG_STATS,
    FIZZIMAGE_IMAGE_REGISTERED,
    FIZZIMAGE_BASE_BUILT,
    FIZZIMAGE_EVAL_BUILT,
    FIZZIMAGE_SUBSYSTEM_GENERATED,
    FIZZIMAGE_INIT_BUILT,
    FIZZIMAGE_SIDECAR_BUILT,
    FIZZIMAGE_MULTI_ARCH_INDEXED,
    FIZZIMAGE_SCAN_STARTED,
    FIZZIMAGE_SCAN_COMPLETED,
    FIZZIMAGE_SCAN_BLOCKED,
    FIZZIMAGE_VERSION_BUMPED,
    FIZZIMAGE_IMAGE_REMOVED,
    FIZZIMAGE_BUILD_ALL_STARTED,
    FIZZIMAGE_BUILD_ALL_COMPLETED,
    # Enums
    ImageType,
    ImageProfile,
    ArchPlatform,
    ScanSeverity,
    VersionBump,
    BuildStatus,
    InitPolicy,
    # Data classes
    ImageSpec,
    ImageManifest,
    LayerDescriptor,
    ScanResult,
    VulnerabilityEntry,
    VersionTag,
    InitContainerSpec,
    ImageIndex,
    CatalogStats,
    # Classes
    ImageMetadata,
    ImageCatalog,
    BaseImageBuilder,
    EvalImageBuilder,
    SubsystemImageGenerator,
    InitContainerBuilder,
    SidecarImageBuilder,
    MultiArchBuilder,
    CatalogScanner,
    ImageVersioner,
    FizzImageDashboard,
    FizzImageMiddleware,
    # Factory
    create_fizzimage_subsystem,
    # Exceptions
    FizzImageError,
    CatalogInitializationError,
    ImageNotFoundError,
    ImageAlreadyExistsError,
    ImageBuildError,
    ImageBuildDependencyError,
    FizzFileGenerationError,
    DependencyRuleViolationError,
    LayerCreationError,
    DigestMismatchError,
    VulnerabilityScanError,
    ImageBlockedByScanError,
    VersionConflictError,
    MultiArchBuildError,
    PlatformResolutionError,
    InitContainerBuildError,
    SidecarBuildError,
    CatalogCapacityError,
    CircularDependencyError,
    MetadataValidationError,
    FizzImageMiddlewareError,
)
from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
from enterprise_fizzbuzz.domain.models import ProcessingContext


# ============================================================
# Constants
# ============================================================


class TestConstants:
    """Verify all module-level constants are defined and typed correctly."""

    def test_fizzimage_version(self):
        assert FIZZIMAGE_VERSION == "1.0.0"

    def test_fizzimage_api_version(self):
        assert FIZZIMAGE_API_VERSION == "v1"

    def test_default_registry_url(self):
        assert isinstance(DEFAULT_REGISTRY_URL, str)
        assert "registry" in DEFAULT_REGISTRY_URL

    def test_default_base_image(self):
        assert DEFAULT_BASE_IMAGE == "fizzbuzz-base"

    def test_default_python_version(self):
        assert DEFAULT_PYTHON_VERSION == "3.12"

    def test_default_module_base_path(self):
        assert DEFAULT_MODULE_BASE_PATH == "enterprise_fizzbuzz.infrastructure"

    def test_default_scan_severity_threshold(self):
        assert DEFAULT_SCAN_SEVERITY_THRESHOLD == "critical"

    def test_default_vuln_db_size(self):
        assert isinstance(DEFAULT_VULN_DB_SIZE, int)
        assert DEFAULT_VULN_DB_SIZE > 0

    def test_default_initial_version(self):
        assert DEFAULT_INITIAL_VERSION == "1.0.0"

    def test_default_max_catalog_size(self):
        assert isinstance(DEFAULT_MAX_CATALOG_SIZE, int)
        assert DEFAULT_MAX_CATALOG_SIZE > 0

    def test_default_dashboard_width(self):
        assert DEFAULT_DASHBOARD_WIDTH == 72

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 113

    def test_supported_platforms(self):
        assert isinstance(SUPPORTED_PLATFORMS, list)
        assert "linux/amd64" in SUPPORTED_PLATFORMS
        assert "linux/arm64" in SUPPORTED_PLATFORMS
        assert "fizzbuzz/vm" in SUPPORTED_PLATFORMS

    def test_image_groups(self):
        assert isinstance(IMAGE_GROUPS, dict)
        assert len(IMAGE_GROUPS) >= 4


# ============================================================
# Enums
# ============================================================


class TestImageType:
    """Verify ImageType enum members."""

    def test_base(self):
        assert ImageType.BASE.value == "base"

    def test_eval(self):
        assert ImageType.EVAL.value == "eval"

    def test_subsystem(self):
        assert ImageType.SUBSYSTEM.value == "subsystem"

    def test_init(self):
        assert ImageType.INIT.value == "init"

    def test_sidecar(self):
        assert ImageType.SIDECAR.value == "sidecar"

    def test_composite(self):
        assert ImageType.COMPOSITE.value == "composite"


class TestImageProfile:
    """Verify ImageProfile enum members."""

    def test_standard(self):
        assert ImageProfile.STANDARD.value == "standard"

    def test_configurable(self):
        assert ImageProfile.CONFIGURABLE.value == "configurable"

    def test_cached(self):
        assert ImageProfile.CACHED.value == "cached"

    def test_ml(self):
        assert ImageProfile.ML.value == "ml"


class TestArchPlatform:
    """Verify ArchPlatform enum members."""

    def test_linux_amd64(self):
        assert ArchPlatform.LINUX_AMD64.value == "linux/amd64"

    def test_linux_arm64(self):
        assert ArchPlatform.LINUX_ARM64.value == "linux/arm64"

    def test_fizzbuzz_vm(self):
        assert ArchPlatform.FIZZBUZZ_VM.value == "fizzbuzz/vm"


class TestScanSeverity:
    """Verify ScanSeverity enum members."""

    def test_critical(self):
        assert ScanSeverity.CRITICAL.value == "critical"

    def test_high(self):
        assert ScanSeverity.HIGH.value == "high"

    def test_medium(self):
        assert ScanSeverity.MEDIUM.value == "medium"

    def test_low(self):
        assert ScanSeverity.LOW.value == "low"

    def test_negligible(self):
        assert ScanSeverity.NEGLIGIBLE.value == "negligible"


class TestVersionBump:
    """Verify VersionBump enum members."""

    def test_major(self):
        assert VersionBump.MAJOR.value == "major"

    def test_minor(self):
        assert VersionBump.MINOR.value == "minor"

    def test_patch(self):
        assert VersionBump.PATCH.value == "patch"


class TestBuildStatus:
    """Verify BuildStatus enum members."""

    def test_pending(self):
        assert BuildStatus.PENDING.value == "pending"

    def test_building(self):
        assert BuildStatus.BUILDING.value == "building"

    def test_scanning(self):
        assert BuildStatus.SCANNING.value == "scanning"

    def test_publishing(self):
        assert BuildStatus.PUBLISHING.value == "publishing"

    def test_complete(self):
        assert BuildStatus.COMPLETE.value == "complete"

    def test_failed(self):
        assert BuildStatus.FAILED.value == "failed"

    def test_blocked(self):
        assert BuildStatus.BLOCKED.value == "blocked"


class TestInitPolicy:
    """Verify InitPolicy enum members."""

    def test_restart(self):
        assert InitPolicy.RESTART_ON_FAILURE.value == "restart"

    def test_abort(self):
        assert InitPolicy.ABORT_ON_FAILURE.value == "abort"

    def test_ignore(self):
        assert InitPolicy.IGNORE_FAILURE.value == "ignore"


# ============================================================
# Data Classes
# ============================================================


class TestImageSpec:
    """Verify ImageSpec data class."""

    def test_creation(self):
        spec = ImageSpec(name="test-image")
        assert spec.name == "test-image"
        assert spec.image_type == ImageType.SUBSYSTEM

    def test_defaults(self):
        spec = ImageSpec(name="test")
        assert spec.base_image == ""
        assert spec.dependencies == []
        assert spec.fizzfile_instructions == []

    def test_with_metadata(self):
        meta = ImageMetadata(title="T", description="D", version="1.0.0")
        spec = ImageSpec(name="test", metadata=meta)
        assert spec.metadata is not None
        assert spec.metadata.title == "T"

    def test_with_profile(self):
        spec = ImageSpec(name="eval", profile=ImageProfile.STANDARD)
        assert spec.profile == ImageProfile.STANDARD

    def test_with_labels(self):
        spec = ImageSpec(name="test", labels={"key": "value"})
        assert spec.labels["key"] == "value"


class TestImageManifest:
    """Verify ImageManifest data class."""

    def test_creation(self):
        manifest = ImageManifest(name="test-image")
        assert manifest.name == "test-image"
        assert manifest.build_status == BuildStatus.PENDING

    def test_defaults(self):
        manifest = ImageManifest(name="test")
        assert manifest.digest == ""
        assert manifest.layers == []
        assert manifest.total_size == 0

    def test_with_layers(self):
        layer = LayerDescriptor(digest="sha256:abc")
        manifest = ImageManifest(name="test", layers=[layer])
        assert len(manifest.layers) == 1

    def test_platform_default(self):
        manifest = ImageManifest(name="test")
        assert manifest.platform == ArchPlatform.LINUX_AMD64

    def test_created_at(self):
        manifest = ImageManifest(name="test")
        assert isinstance(manifest.created_at, datetime)


class TestLayerDescriptor:
    """Verify LayerDescriptor data class."""

    def test_creation(self):
        layer = LayerDescriptor(digest="sha256:abc123")
        assert layer.digest == "sha256:abc123"

    def test_defaults(self):
        layer = LayerDescriptor(digest="sha256:test")
        assert layer.size == 0
        assert "tar+gzip" in layer.media_type

    def test_with_instruction(self):
        layer = LayerDescriptor(digest="sha256:x", instruction="RUN echo hello")
        assert layer.instruction == "RUN echo hello"

    def test_annotations(self):
        layer = LayerDescriptor(digest="sha256:x", annotations={"key": "val"})
        assert layer.annotations["key"] == "val"


class TestScanResult:
    """Verify ScanResult data class."""

    def test_creation(self):
        result = ScanResult(image_name="test")
        assert result.image_name == "test"

    def test_defaults(self):
        result = ScanResult(image_name="test")
        assert result.total_vulnerabilities == 0
        assert result.admitted is True

    def test_vulnerability_counts(self):
        result = ScanResult(
            image_name="test",
            critical_count=1,
            high_count=2,
            medium_count=3,
        )
        assert result.critical_count == 1
        assert result.high_count == 2
        assert result.medium_count == 3

    def test_with_vulnerabilities(self):
        vuln = VulnerabilityEntry(cve_id="CVE-2024-1234")
        result = ScanResult(image_name="test", vulnerabilities=[vuln])
        assert len(result.vulnerabilities) == 1

    def test_scan_duration(self):
        result = ScanResult(image_name="test", scan_duration_ms=42.5)
        assert result.scan_duration_ms == 42.5


class TestVulnerabilityEntry:
    """Verify VulnerabilityEntry data class."""

    def test_creation(self):
        vuln = VulnerabilityEntry(cve_id="CVE-2024-0001")
        assert vuln.cve_id == "CVE-2024-0001"

    def test_defaults(self):
        vuln = VulnerabilityEntry(cve_id="CVE-2024-0001")
        assert vuln.severity == ScanSeverity.LOW
        assert vuln.package == ""

    def test_with_severity(self):
        vuln = VulnerabilityEntry(
            cve_id="CVE-2024-0001",
            severity=ScanSeverity.CRITICAL,
        )
        assert vuln.severity == ScanSeverity.CRITICAL

    def test_with_fix(self):
        vuln = VulnerabilityEntry(
            cve_id="CVE-2024-0001",
            fixed_version="1.2.3",
        )
        assert vuln.fixed_version == "1.2.3"


class TestVersionTag:
    """Verify VersionTag data class."""

    def test_creation(self):
        tag = VersionTag(major=1, minor=2, patch=3)
        assert tag.major == 1
        assert tag.minor == 2
        assert tag.patch == 3

    def test_semver(self):
        tag = VersionTag(major=2, minor=1, patch=0)
        assert tag.semver == "2.1.0"

    def test_defaults(self):
        tag = VersionTag()
        assert tag.major == 1
        assert tag.minor == 0
        assert tag.patch == 0

    def test_tags_list(self):
        tag = VersionTag(tags=["1.0.0", "latest"])
        assert "latest" in tag.tags

    def test_commit_sha(self):
        tag = VersionTag(commit_sha="abc123")
        assert tag.commit_sha == "abc123"


class TestInitContainerSpec:
    """Verify InitContainerSpec data class."""

    def test_creation(self):
        spec = InitContainerSpec(name="config-init")
        assert spec.name == "config-init"

    def test_defaults(self):
        spec = InitContainerSpec(name="test")
        assert spec.order == 0
        assert spec.failure_policy == InitPolicy.ABORT_ON_FAILURE
        assert spec.timeout_seconds == 300

    def test_shared_volumes(self):
        spec = InitContainerSpec(name="test", shared_volumes=["/config"])
        assert "/config" in spec.shared_volumes

    def test_with_env(self):
        spec = InitContainerSpec(name="test", env=["FOO=bar"])
        assert "FOO=bar" in spec.env


class TestImageIndex:
    """Verify ImageIndex data class."""

    def test_creation(self):
        index = ImageIndex(image_name="test")
        assert index.image_name == "test"

    def test_media_type(self):
        index = ImageIndex(image_name="test")
        assert "index" in index.media_type

    def test_manifests(self):
        m = ImageManifest(name="test")
        index = ImageIndex(image_name="test", manifests={"linux/amd64": m})
        assert "linux/amd64" in index.manifests

    def test_annotations(self):
        index = ImageIndex(image_name="test", annotations={"key": "val"})
        assert index.annotations["key"] == "val"


class TestCatalogStats:
    """Verify CatalogStats data class."""

    def test_creation(self):
        stats = CatalogStats()
        assert stats.total_images == 0

    def test_all_defaults_zero(self):
        stats = CatalogStats()
        for f in fields(stats):
            assert getattr(stats, f.name) == 0

    def test_with_counts(self):
        stats = CatalogStats(total_images=10, base_images=1, eval_images=4)
        assert stats.total_images == 10
        assert stats.base_images == 1
        assert stats.eval_images == 4

    def test_builds(self):
        stats = CatalogStats(builds_completed=5, builds_failed=1)
        assert stats.builds_completed == 5
        assert stats.builds_failed == 1

    def test_scanning(self):
        stats = CatalogStats(total_scans=10, images_admitted=8, images_blocked=2)
        assert stats.total_scans == 10


# ============================================================
# ImageMetadata
# ============================================================


class TestImageMetadata:
    """Verify ImageMetadata class."""

    def test_creation(self):
        meta = ImageMetadata(
            title="Test Image",
            description="A test image",
            version="1.0.0",
        )
        assert meta.title == "Test Image"
        assert meta.description == "A test image"
        assert meta.version == "1.0.0"

    def test_module_and_layer(self):
        meta = ImageMetadata(
            title="T", description="D", version="1.0.0",
            module="cache", layer="infrastructure",
        )
        assert meta.module == "cache"
        assert meta.layer == "infrastructure"

    def test_dependencies(self):
        meta = ImageMetadata(
            title="T", description="D", version="1.0.0",
            dependencies=["dep1", "dep2"],
        )
        assert len(meta.dependencies) == 2

    def test_to_oci_annotations(self):
        meta = ImageMetadata(title="T", description="D", version="1.0.0")
        annotations = meta.to_oci_annotations()
        assert "org.opencontainers.image.title" in annotations
        assert annotations["org.opencontainers.image.title"] == "T"
        assert "org.opencontainers.image.version" in annotations

    def test_to_platform_labels(self):
        meta = ImageMetadata(
            title="T", description="D", version="1.0.0",
            module="cache",
        )
        labels = meta.to_platform_labels()
        assert labels["com.fizzbuzz.platform.module"] == "cache"

    def test_to_dict(self):
        meta = ImageMetadata(title="T", description="D", version="1.0.0")
        d = meta.to_dict()
        assert d["title"] == "T"
        assert "authors" in d

    def test_from_dict(self):
        meta = ImageMetadata.from_dict({
            "title": "T",
            "description": "D",
            "version": "2.0.0",
            "module": "auth",
        })
        assert meta.title == "T"
        assert meta.version == "2.0.0"
        assert meta.module == "auth"

    def test_dependencies_in_labels(self):
        meta = ImageMetadata(
            title="T", description="D", version="1.0.0",
            dependencies=["a", "b"],
        )
        labels = meta.to_platform_labels()
        assert "a,b" in labels["com.fizzbuzz.platform.dependencies"]


# ============================================================
# ImageCatalog
# ============================================================


class TestImageCatalog:
    """Verify ImageCatalog class."""

    def test_creation(self):
        catalog = ImageCatalog()
        assert catalog.registry_url == DEFAULT_REGISTRY_URL

    def test_register_image(self):
        catalog = ImageCatalog()
        spec = ImageSpec(name="test-image")
        manifest = catalog.register_image(spec)
        assert manifest.name == "test-image"
        assert manifest.build_status == BuildStatus.PENDING

    def test_register_duplicate_raises(self):
        catalog = ImageCatalog()
        spec = ImageSpec(name="test-image")
        catalog.register_image(spec)
        with pytest.raises(ImageAlreadyExistsError):
            catalog.register_image(spec)

    def test_capacity_limit(self):
        catalog = ImageCatalog(max_catalog_size=2)
        catalog.register_image(ImageSpec(name="img1"))
        catalog.register_image(ImageSpec(name="img2"))
        with pytest.raises(CatalogCapacityError):
            catalog.register_image(ImageSpec(name="img3"))

    def test_build_image(self):
        catalog = ImageCatalog()
        spec = ImageSpec(
            name="test",
            fizzfile_instructions=["FROM scratch", "RUN echo hello"],
        )
        catalog.register_image(spec)
        manifest = catalog.build_image("test")
        assert manifest.build_status == BuildStatus.COMPLETE
        assert len(manifest.layers) == 2
        assert manifest.digest.startswith("sha256:")

    def test_build_not_found_raises(self):
        catalog = ImageCatalog()
        with pytest.raises(ImageNotFoundError):
            catalog.build_image("nonexistent")

    def test_get_image(self):
        catalog = ImageCatalog()
        catalog.register_image(ImageSpec(name="test"))
        manifest = catalog.get_image("test")
        assert manifest.name == "test"

    def test_get_image_not_found_raises(self):
        catalog = ImageCatalog()
        with pytest.raises(ImageNotFoundError):
            catalog.get_image("nonexistent")

    def test_list_images(self):
        catalog = ImageCatalog()
        catalog.register_image(ImageSpec(name="img1"))
        catalog.register_image(ImageSpec(name="img2"))
        images = catalog.list_images()
        assert len(images) == 2

    def test_inspect_image(self):
        catalog = ImageCatalog()
        spec = ImageSpec(
            name="test",
            fizzfile_instructions=["FROM scratch"],
        )
        catalog.register_image(spec)
        catalog.build_image("test")
        details = catalog.inspect_image("test")
        assert details["name"] == "test"
        assert details["status"] == "complete"

    def test_get_dependencies(self):
        catalog = ImageCatalog()
        spec = ImageSpec(name="test", dependencies=["base"])
        catalog.register_image(spec)
        deps = catalog.get_dependencies("test")
        assert "base" in deps

    def test_remove_image(self):
        catalog = ImageCatalog()
        catalog.register_image(ImageSpec(name="test"))
        catalog.remove_image("test")
        with pytest.raises(ImageNotFoundError):
            catalog.get_image("test")

    def test_remove_not_found_raises(self):
        catalog = ImageCatalog()
        with pytest.raises(ImageNotFoundError):
            catalog.remove_image("nonexistent")

    def test_get_stats(self):
        catalog = ImageCatalog()
        catalog.register_image(ImageSpec(name="base", image_type=ImageType.BASE))
        catalog.register_image(ImageSpec(name="eval", image_type=ImageType.EVAL))
        stats = catalog.get_stats()
        assert stats.total_images == 2
        assert stats.base_images == 1
        assert stats.eval_images == 1

    def test_build_all(self):
        catalog = ImageCatalog()
        catalog.register_image(ImageSpec(
            name="img1", fizzfile_instructions=["FROM scratch"],
        ))
        catalog.register_image(ImageSpec(
            name="img2", fizzfile_instructions=["FROM img1"],
        ))
        results = catalog.build_all()
        assert len(results) == 2

    def test_scan_all(self):
        catalog = ImageCatalog()
        spec = ImageSpec(name="test", fizzfile_instructions=["FROM scratch"])
        catalog.register_image(spec)
        catalog.build_image("test")
        results = catalog.scan_all()
        assert len(results) == 1
        assert results[0].image_name == "test"

    def test_idempotent_build(self):
        catalog = ImageCatalog()
        spec = ImageSpec(name="test", fizzfile_instructions=["FROM scratch"])
        catalog.register_image(spec)
        m1 = catalog.build_image("test")
        m2 = catalog.build_image("test")
        assert m1.digest == m2.digest

    def test_base_image_name(self):
        catalog = ImageCatalog(base_image_name="custom-base")
        assert catalog.base_image_name == "custom-base"


# ============================================================
# BaseImageBuilder
# ============================================================


class TestBaseImageBuilder:
    """Verify BaseImageBuilder class."""

    def test_creation(self):
        catalog = ImageCatalog()
        builder = BaseImageBuilder(catalog)
        assert builder.base_image_name == DEFAULT_BASE_IMAGE

    def test_build(self):
        catalog = ImageCatalog()
        builder = BaseImageBuilder(catalog)
        manifest = builder.build()
        assert manifest.name == DEFAULT_BASE_IMAGE
        assert manifest.build_status == BuildStatus.COMPLETE

    def test_generate_fizzfile(self):
        catalog = ImageCatalog()
        builder = BaseImageBuilder(catalog)
        fizzfile = builder.generate_fizzfile()
        assert "FROM scratch" in fizzfile
        assert "domain" in fizzfile

    def test_validate_dependency_rule_pass(self):
        manifest = ImageManifest(
            name="base",
            layers=[LayerDescriptor(digest="sha256:x", instruction="RUN echo")],
        )
        catalog = ImageCatalog()
        builder = BaseImageBuilder(catalog)
        assert builder.validate_dependency_rule(manifest) is True

    def test_validate_dependency_rule_fail(self):
        manifest = ImageManifest(
            name="base",
            layers=[
                LayerDescriptor(
                    digest="sha256:x",
                    instruction="COPY infrastructure/cache.py /app/",
                ),
            ],
        )
        catalog = ImageCatalog()
        builder = BaseImageBuilder(catalog)
        with pytest.raises(DependencyRuleViolationError):
            builder.validate_dependency_rule(manifest)

    def test_custom_python_version(self):
        catalog = ImageCatalog()
        builder = BaseImageBuilder(catalog, python_version="3.11")
        fizzfile = builder.generate_fizzfile()
        assert "3.11" in fizzfile

    def test_compute_layer_digest(self):
        catalog = ImageCatalog()
        builder = BaseImageBuilder(catalog)
        digest = builder._compute_layer_digest(b"test content")
        assert digest.startswith("sha256:")

    def test_create_base_layers(self):
        catalog = ImageCatalog()
        builder = BaseImageBuilder(catalog)
        layers = builder._create_base_layers()
        assert len(layers) > 0
        assert all(l.digest.startswith("sha256:") for l in layers)


# ============================================================
# EvalImageBuilder
# ============================================================


class TestEvalImageBuilder:
    """Verify EvalImageBuilder class."""

    def test_creation(self):
        catalog = ImageCatalog()
        base = BaseImageBuilder(catalog)
        builder = EvalImageBuilder(catalog, base)
        assert builder is not None

    def test_build_standard_profile(self):
        catalog = ImageCatalog()
        base = BaseImageBuilder(catalog)
        base.build()
        builder = EvalImageBuilder(catalog, base)
        manifest = builder.build_profile(ImageProfile.STANDARD)
        assert manifest.build_status == BuildStatus.COMPLETE
        assert "standard" in manifest.name

    def test_build_all_profiles(self):
        catalog = ImageCatalog()
        base = BaseImageBuilder(catalog)
        base.build()
        builder = EvalImageBuilder(catalog, base)
        manifests = builder.build_all_profiles()
        assert len(manifests) == len(ImageProfile)

    def test_generate_fizzfile_standard(self):
        catalog = ImageCatalog()
        base = BaseImageBuilder(catalog)
        builder = EvalImageBuilder(catalog, base)
        fizzfile = builder.generate_fizzfile(ImageProfile.STANDARD)
        assert "FROM" in fizzfile
        assert "application" in fizzfile

    def test_generate_fizzfile_ml(self):
        catalog = ImageCatalog()
        base = BaseImageBuilder(catalog)
        builder = EvalImageBuilder(catalog, base)
        fizzfile = builder.generate_fizzfile(ImageProfile.ML)
        assert "ml_engine" in fizzfile

    def test_profile_dependencies_standard(self):
        catalog = ImageCatalog()
        base = BaseImageBuilder(catalog)
        builder = EvalImageBuilder(catalog, base)
        deps = builder._get_profile_dependencies(ImageProfile.STANDARD)
        assert "rule_engine" in deps

    def test_profile_dependencies_cached(self):
        catalog = ImageCatalog()
        base = BaseImageBuilder(catalog)
        builder = EvalImageBuilder(catalog, base)
        deps = builder._get_profile_dependencies(ImageProfile.CACHED)
        assert "cache" in deps

    def test_profile_entrypoint(self):
        catalog = ImageCatalog()
        base = BaseImageBuilder(catalog)
        builder = EvalImageBuilder(catalog, base)
        ep = builder._get_profile_entrypoint(ImageProfile.STANDARD)
        assert "python" in ep

    def test_each_profile_has_deps(self):
        for profile in ImageProfile:
            assert profile in EvalImageBuilder.PROFILE_DEPS

    def test_each_profile_has_entrypoint(self):
        for profile in ImageProfile:
            assert profile in EvalImageBuilder.PROFILE_ENTRYPOINTS


# ============================================================
# SubsystemImageGenerator
# ============================================================


class TestSubsystemImageGenerator:
    """Verify SubsystemImageGenerator class."""

    def test_creation(self):
        catalog = ImageCatalog()
        gen = SubsystemImageGenerator(catalog)
        assert gen is not None

    def test_analyze_module(self):
        catalog = ImageCatalog()
        gen = SubsystemImageGenerator(catalog)
        # Uses simulated AST analysis based on IMAGE_GROUPS
        deps = gen.analyze_module("sqlite_backend")
        assert isinstance(deps, list)

    def test_generate_fizzfile(self):
        catalog = ImageCatalog()
        gen = SubsystemImageGenerator(catalog)
        fizzfile = gen.generate_fizzfile("auth")
        assert "FROM" in fizzfile
        assert "auth" in fizzfile

    def test_build_subsystem_image(self):
        catalog = ImageCatalog()
        base = BaseImageBuilder(catalog)
        base.build()
        gen = SubsystemImageGenerator(catalog)
        manifest = gen.build_subsystem_image("auth")
        assert manifest.build_status == BuildStatus.COMPLETE
        assert "auth" in manifest.name

    def test_detect_circular_groups(self):
        catalog = ImageCatalog()
        gen = SubsystemImageGenerator(catalog)
        groups = gen.detect_circular_groups()
        assert isinstance(groups, list)

    def test_get_image_groups(self):
        catalog = ImageCatalog()
        gen = SubsystemImageGenerator(catalog)
        groups = gen.get_image_groups()
        assert isinstance(groups, dict)
        assert len(groups) == len(IMAGE_GROUPS)

    def test_resolve_transitive_deps(self):
        catalog = ImageCatalog()
        gen = SubsystemImageGenerator(catalog)
        deps = gen._resolve_transitive_deps("auth")
        assert "auth" in deps

    def test_ast_extract_imports(self):
        catalog = ImageCatalog()
        gen = SubsystemImageGenerator(catalog)
        imports = gen._ast_extract_imports("sqlite_backend")
        assert isinstance(imports, list)

    def test_dependency_caching(self):
        catalog = ImageCatalog()
        gen = SubsystemImageGenerator(catalog)
        deps1 = gen.analyze_module("auth")
        deps2 = gen.analyze_module("auth")
        assert deps1 == deps2

    def test_unknown_module_empty_deps(self):
        catalog = ImageCatalog()
        gen = SubsystemImageGenerator(catalog)
        deps = gen.analyze_module("nonexistent_module_xyz")
        assert deps == []

    def test_build_all_subsystem_images(self):
        catalog = ImageCatalog(max_catalog_size=200)
        base = BaseImageBuilder(catalog)
        base.build()
        gen = SubsystemImageGenerator(catalog)
        manifests = gen.build_all_subsystem_images()
        assert len(manifests) > 0

    def test_fizzfile_contains_copy(self):
        catalog = ImageCatalog()
        gen = SubsystemImageGenerator(catalog)
        fizzfile = gen.generate_fizzfile("sqlite_backend")
        assert "COPY" in fizzfile


# ============================================================
# InitContainerBuilder
# ============================================================


class TestInitContainerBuilder:
    """Verify InitContainerBuilder class."""

    def test_creation(self):
        catalog = ImageCatalog()
        builder = InitContainerBuilder(catalog)
        assert builder is not None

    def test_build_config_init(self):
        catalog = ImageCatalog()
        base = BaseImageBuilder(catalog)
        base.build()
        builder = InitContainerBuilder(catalog)
        manifest = builder.build_config_init()
        assert manifest.build_status == BuildStatus.COMPLETE
        assert "config" in manifest.name

    def test_build_schema_init(self):
        catalog = ImageCatalog()
        base = BaseImageBuilder(catalog)
        base.build()
        builder = InitContainerBuilder(catalog)
        manifest = builder.build_schema_init()
        assert "schema" in manifest.name

    def test_build_secrets_init(self):
        catalog = ImageCatalog()
        base = BaseImageBuilder(catalog)
        base.build()
        builder = InitContainerBuilder(catalog)
        manifest = builder.build_secrets_init()
        assert "secrets" in manifest.name

    def test_build_all_inits(self):
        catalog = ImageCatalog()
        base = BaseImageBuilder(catalog)
        base.build()
        builder = InitContainerBuilder(catalog)
        manifests = builder.build_all_inits()
        assert len(manifests) == 3

    def test_generate_fizzfile(self):
        catalog = ImageCatalog()
        builder = InitContainerBuilder(catalog)
        fizzfile = builder.generate_fizzfile("config")
        assert "FROM" in fizzfile
        assert "config" in fizzfile

    def test_get_init_spec(self):
        catalog = ImageCatalog()
        builder = InitContainerBuilder(catalog)
        spec = builder.get_init_spec("config")
        assert spec.name == "fizzbuzz-init-config"
        assert spec.order == 0
        assert len(spec.shared_volumes) > 0

    def test_init_spec_secrets(self):
        catalog = ImageCatalog()
        builder = InitContainerBuilder(catalog)
        spec = builder.get_init_spec("secrets")
        assert spec.order == 2
        assert "/run/secrets" in spec.shared_volumes


# ============================================================
# SidecarImageBuilder
# ============================================================


class TestSidecarImageBuilder:
    """Verify SidecarImageBuilder class."""

    def test_creation(self):
        catalog = ImageCatalog()
        builder = SidecarImageBuilder(catalog)
        assert builder is not None

    def test_build_log_sidecar(self):
        catalog = ImageCatalog()
        base = BaseImageBuilder(catalog)
        base.build()
        builder = SidecarImageBuilder(catalog)
        manifest = builder.build_log_sidecar()
        assert manifest.build_status == BuildStatus.COMPLETE
        assert "logging" in manifest.name

    def test_build_metrics_sidecar(self):
        catalog = ImageCatalog()
        base = BaseImageBuilder(catalog)
        base.build()
        builder = SidecarImageBuilder(catalog)
        manifest = builder.build_metrics_sidecar()
        assert "metrics" in manifest.name

    def test_build_trace_sidecar(self):
        catalog = ImageCatalog()
        base = BaseImageBuilder(catalog)
        base.build()
        builder = SidecarImageBuilder(catalog)
        manifest = builder.build_trace_sidecar()
        assert "tracing" in manifest.name

    def test_build_proxy_sidecar(self):
        catalog = ImageCatalog()
        base = BaseImageBuilder(catalog)
        base.build()
        builder = SidecarImageBuilder(catalog)
        manifest = builder.build_proxy_sidecar()
        assert "proxy" in manifest.name

    def test_build_all_sidecars(self):
        catalog = ImageCatalog()
        base = BaseImageBuilder(catalog)
        base.build()
        builder = SidecarImageBuilder(catalog)
        manifests = builder.build_all_sidecars()
        assert len(manifests) == 4

    def test_generate_fizzfile(self):
        catalog = ImageCatalog()
        builder = SidecarImageBuilder(catalog)
        fizzfile = builder.generate_fizzfile("logging")
        assert "FROM" in fizzfile
        assert "logging" in fizzfile

    def test_sidecar_ports(self):
        assert SidecarImageBuilder.SIDECAR_PORTS["logging"] == 5170
        assert SidecarImageBuilder.SIDECAR_PORTS["metrics"] == 9090
        assert SidecarImageBuilder.SIDECAR_PORTS["tracing"] == 4317
        assert SidecarImageBuilder.SIDECAR_PORTS["proxy"] == 15001


# ============================================================
# MultiArchBuilder
# ============================================================


class TestMultiArchBuilder:
    """Verify MultiArchBuilder class."""

    def test_creation(self):
        builder = MultiArchBuilder()
        assert len(builder.supported_platforms) == 3

    def test_build_index(self):
        builder = MultiArchBuilder()
        m1 = ImageManifest(name="test", digest="sha256:aaa")
        m2 = ImageManifest(name="test", digest="sha256:bbb")
        index = builder.build_index("test", {"linux/amd64": m1, "linux/arm64": m2})
        assert index.image_name == "test"
        assert len(index.manifests) == 2
        assert index.digest.startswith("sha256:")

    def test_build_index_empty_raises(self):
        builder = MultiArchBuilder()
        with pytest.raises(MultiArchBuildError):
            builder.build_index("test", {})

    def test_resolve_platform(self):
        builder = MultiArchBuilder()
        m = ImageManifest(name="test", digest="sha256:aaa")
        index = builder.build_index("test", {"linux/amd64": m})
        resolved = builder.resolve_platform(index, "linux/amd64")
        assert resolved.name == "test"

    def test_resolve_platform_not_found(self):
        builder = MultiArchBuilder()
        m = ImageManifest(name="test", digest="sha256:aaa")
        index = builder.build_index("test", {"linux/amd64": m})
        with pytest.raises(PlatformResolutionError):
            builder.resolve_platform(index, "linux/arm64")

    def test_list_platforms(self):
        builder = MultiArchBuilder()
        m = ImageManifest(name="test", digest="sha256:aaa")
        index = builder.build_index("test", {"linux/amd64": m})
        platforms = builder.list_platforms(index)
        assert "linux/amd64" in platforms


# ============================================================
# CatalogScanner
# ============================================================


class TestCatalogScanner:
    """Verify CatalogScanner class."""

    def test_creation(self):
        scanner = CatalogScanner()
        assert scanner.severity_threshold == ScanSeverity.CRITICAL

    def test_scan_image(self):
        scanner = CatalogScanner()
        manifest = ImageManifest(
            name="test",
            digest="sha256:abc",
            layers=[LayerDescriptor(digest="sha256:layer1")],
        )
        result = scanner.scan_image(manifest)
        assert result.image_name == "test"
        assert isinstance(result.total_vulnerabilities, int)

    def test_scan_catalog(self):
        catalog = ImageCatalog()
        spec = ImageSpec(name="test", fizzfile_instructions=["FROM scratch"])
        catalog.register_image(spec)
        catalog.build_image("test")
        scanner = CatalogScanner()
        results = scanner.scan_catalog(catalog)
        assert len(results) == 1

    def test_is_admissible_no_vulns(self):
        scanner = CatalogScanner()
        assert scanner.is_admissible(None, []) is True

    def test_is_admissible_low_severity(self):
        scanner = CatalogScanner(severity_threshold="critical")
        vulns = [VulnerabilityEntry(cve_id="CVE-1", severity=ScanSeverity.LOW)]
        assert scanner.is_admissible(None, vulns) is True

    def test_is_admissible_critical_blocked(self):
        scanner = CatalogScanner(severity_threshold="critical")
        vulns = [VulnerabilityEntry(cve_id="CVE-1", severity=ScanSeverity.CRITICAL)]
        assert scanner.is_admissible(None, vulns) is False

    def test_generate_report(self):
        scanner = CatalogScanner()
        result = ScanResult(
            image_name="test",
            total_vulnerabilities=2,
            critical_count=1,
            high_count=1,
        )
        report = scanner.generate_report(result)
        assert "test" in report
        assert "Critical" in report

    def test_severity_rank(self):
        scanner = CatalogScanner()
        assert scanner._severity_rank(ScanSeverity.CRITICAL) > scanner._severity_rank(ScanSeverity.LOW)

    def test_total_scans(self):
        scanner = CatalogScanner()
        manifest = ImageManifest(name="test", digest="sha256:abc", layers=[])
        scanner.scan_image(manifest)
        assert scanner.total_scans == 1

    def test_deterministic_vuln_db(self):
        s1 = CatalogScanner(vulnerability_db_size=10)
        s2 = CatalogScanner(vulnerability_db_size=10)
        assert len(s1._vulnerability_db) == len(s2._vulnerability_db)
        assert s1._vulnerability_db[0].cve_id == s2._vulnerability_db[0].cve_id


# ============================================================
# ImageVersioner
# ============================================================


class TestImageVersioner:
    """Verify ImageVersioner class."""

    def test_creation(self):
        versioner = ImageVersioner()
        assert versioner is not None

    def test_get_version_default(self):
        versioner = ImageVersioner()
        tag = versioner.get_version("test")
        assert tag.semver == "1.0.0"

    def test_bump_major(self):
        versioner = ImageVersioner()
        versioner.get_version("test")
        tag = versioner.bump_version("test", VersionBump.MAJOR)
        assert tag.semver == "2.0.0"

    def test_bump_minor(self):
        versioner = ImageVersioner()
        versioner.get_version("test")
        tag = versioner.bump_version("test", VersionBump.MINOR)
        assert tag.semver == "1.1.0"

    def test_bump_patch(self):
        versioner = ImageVersioner()
        versioner.get_version("test")
        tag = versioner.bump_version("test", VersionBump.PATCH)
        assert tag.semver == "1.0.1"

    def test_tag_image(self):
        versioner = ImageVersioner()
        tags = versioner.tag_image("test")
        assert "1.0.0" in tags
        assert "latest" in tags

    def test_tag_with_commit_sha(self):
        versioner = ImageVersioner()
        tags = versioner.tag_image("test", commit_sha="abcdef123456")
        assert any("sha-" in t for t in tags)

    def test_list_tags(self):
        versioner = ImageVersioner()
        versioner.get_version("test")
        tags = versioner.list_tags("test")
        assert len(tags) >= 2


# ============================================================
# FizzImageDashboard
# ============================================================


class TestFizzImageDashboard:
    """Verify FizzImageDashboard class."""

    def test_creation(self):
        dashboard = FizzImageDashboard()
        assert dashboard._width == DEFAULT_DASHBOARD_WIDTH

    def test_render(self):
        catalog = ImageCatalog()
        dashboard = FizzImageDashboard()
        output = dashboard.render(catalog)
        assert "FIZZIMAGE" in output
        assert "Total Images" in output

    def test_render_catalog_empty(self):
        catalog = ImageCatalog()
        dashboard = FizzImageDashboard()
        output = dashboard.render_catalog(catalog)
        assert "no images" in output

    def test_render_catalog_with_images(self):
        catalog = ImageCatalog()
        spec = ImageSpec(name="test", fizzfile_instructions=["FROM scratch"])
        catalog.register_image(spec)
        catalog.build_image("test")
        dashboard = FizzImageDashboard()
        output = dashboard.render_catalog(catalog)
        assert "test" in output

    def test_render_image_detail(self):
        catalog = ImageCatalog()
        spec = ImageSpec(name="test", fizzfile_instructions=["FROM scratch"])
        catalog.register_image(spec)
        catalog.build_image("test")
        dashboard = FizzImageDashboard()
        output = dashboard.render_image_detail(catalog, "test")
        assert "test" in output
        assert "complete" in output

    def test_render_image_not_found(self):
        catalog = ImageCatalog()
        dashboard = FizzImageDashboard()
        output = dashboard.render_image_detail(catalog, "nonexistent")
        assert "not found" in output

    def test_render_dependencies(self):
        catalog = ImageCatalog()
        spec = ImageSpec(name="test", dependencies=["base"])
        catalog.register_image(spec)
        dashboard = FizzImageDashboard()
        output = dashboard.render_dependencies(catalog, "test")
        assert "base" in output

    def test_render_scan_results_empty(self):
        catalog = ImageCatalog()
        dashboard = FizzImageDashboard()
        output = dashboard.render_scan_results(catalog)
        assert "no scan" in output

    def test_render_build_history(self):
        catalog = ImageCatalog()
        spec = ImageSpec(name="test", fizzfile_instructions=["FROM scratch"])
        catalog.register_image(spec)
        catalog.build_image("test")
        dashboard = FizzImageDashboard()
        output = dashboard.render_build_history(catalog)
        assert "test" in output

    def test_format_bytes(self):
        assert "B" in FizzImageDashboard._format_bytes(100)
        assert "KB" in FizzImageDashboard._format_bytes(2048)
        assert "MB" in FizzImageDashboard._format_bytes(2 * 1024 * 1024)
        assert "GB" in FizzImageDashboard._format_bytes(2 * 1024 * 1024 * 1024)


# ============================================================
# FizzImageMiddleware
# ============================================================


class TestFizzImageMiddleware:
    """Verify FizzImageMiddleware class."""

    def _make_context(self, number: int = 42) -> ProcessingContext:
        return ProcessingContext(number=number, session_id="test-session")

    def test_creation(self):
        catalog = ImageCatalog()
        mw = FizzImageMiddleware(catalog)
        assert mw.name == "FizzImageMiddleware"

    def test_get_name(self):
        catalog = ImageCatalog()
        mw = FizzImageMiddleware(catalog)
        assert mw.get_name() == "FizzImageMiddleware"

    def test_get_priority(self):
        catalog = ImageCatalog()
        mw = FizzImageMiddleware(catalog)
        assert mw.get_priority() == 113

    def test_priority_property(self):
        catalog = ImageCatalog()
        mw = FizzImageMiddleware(catalog)
        assert mw.priority == 113

    def test_name_property(self):
        catalog = ImageCatalog()
        mw = FizzImageMiddleware(catalog)
        assert mw.name == "FizzImageMiddleware"

    def test_process(self):
        catalog = ImageCatalog()
        mw = FizzImageMiddleware(catalog)
        ctx = self._make_context()
        result = mw.process(ctx, lambda c: c)
        assert result is ctx
        assert "fizzimage_version" in result.metadata

    def test_process_increments_count(self):
        catalog = ImageCatalog()
        mw = FizzImageMiddleware(catalog)
        mw.process(self._make_context(), lambda c: c)
        mw.process(self._make_context(), lambda c: c)
        assert mw._evaluation_count == 2

    def test_process_error_raises_middleware_error(self):
        catalog = ImageCatalog()
        mw = FizzImageMiddleware(catalog)
        ctx = self._make_context()

        def bad_handler(c):
            raise RuntimeError("boom")

        with pytest.raises(FizzImageMiddlewareError):
            mw.process(ctx, bad_handler)

    def test_render_dashboard(self):
        catalog = ImageCatalog()
        mw = FizzImageMiddleware(catalog)
        output = mw.render_dashboard()
        assert "FIZZIMAGE" in output

    def test_render_catalog(self):
        catalog = ImageCatalog()
        mw = FizzImageMiddleware(catalog)
        output = mw.render_catalog()
        assert "CATALOG" in output

    def test_render_stats(self):
        catalog = ImageCatalog()
        mw = FizzImageMiddleware(catalog)
        output = mw.render_stats()
        assert "Evaluations" in output

    def test_render_scan_results(self):
        catalog = ImageCatalog()
        mw = FizzImageMiddleware(catalog)
        output = mw.render_scan_results()
        assert "SCAN" in output


# ============================================================
# Factory
# ============================================================


class TestFactory:
    """Verify create_fizzimage_subsystem factory function."""

    def test_returns_tuple(self):
        result = create_fizzimage_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_catalog_type(self):
        catalog, _ = create_fizzimage_subsystem()
        assert isinstance(catalog, ImageCatalog)

    def test_middleware_type(self):
        _, middleware = create_fizzimage_subsystem()
        assert isinstance(middleware, FizzImageMiddleware)

    def test_catalog_has_images(self):
        catalog, _ = create_fizzimage_subsystem()
        images = catalog.list_images()
        assert len(images) > 0

    def test_base_image_built(self):
        catalog, _ = create_fizzimage_subsystem()
        base = catalog.get_image(DEFAULT_BASE_IMAGE)
        assert base.build_status == BuildStatus.COMPLETE


# ============================================================
# Exceptions
# ============================================================


class TestExceptions:
    """Verify all FizzImage exception classes."""

    def test_fizzimage_error(self):
        exc = FizzImageError("test")
        assert isinstance(exc, FizzBuzzError)
        assert exc.error_code == "EFP-IMG00"
        assert exc.context["reason"] == "test"

    def test_catalog_initialization_error(self):
        exc = CatalogInitializationError("init fail")
        assert isinstance(exc, FizzImageError)
        assert exc.error_code == "EFP-IMG01"

    def test_image_not_found_error(self):
        exc = ImageNotFoundError("not found")
        assert exc.error_code == "EFP-IMG02"

    def test_image_already_exists_error(self):
        exc = ImageAlreadyExistsError("exists")
        assert exc.error_code == "EFP-IMG03"

    def test_image_build_error(self):
        exc = ImageBuildError("build fail")
        assert exc.error_code == "EFP-IMG04"

    def test_image_build_dependency_error(self):
        exc = ImageBuildDependencyError("dep missing")
        assert exc.error_code == "EFP-IMG05"

    def test_fizzfile_generation_error(self):
        exc = FizzFileGenerationError("gen fail")
        assert exc.error_code == "EFP-IMG06"

    def test_dependency_rule_violation_error(self):
        exc = DependencyRuleViolationError("violation")
        assert exc.error_code == "EFP-IMG07"

    def test_layer_creation_error(self):
        exc = LayerCreationError("layer fail")
        assert exc.error_code == "EFP-IMG08"

    def test_digest_mismatch_error(self):
        exc = DigestMismatchError("mismatch")
        assert exc.error_code == "EFP-IMG09"

    def test_vulnerability_scan_error(self):
        exc = VulnerabilityScanError("scan fail")
        assert exc.error_code == "EFP-IMG10"

    def test_image_blocked_by_scan_error(self):
        exc = ImageBlockedByScanError("blocked")
        assert exc.error_code == "EFP-IMG11"

    def test_version_conflict_error(self):
        exc = VersionConflictError("conflict")
        assert exc.error_code == "EFP-IMG12"

    def test_multi_arch_build_error(self):
        exc = MultiArchBuildError("arch fail")
        assert exc.error_code == "EFP-IMG13"

    def test_platform_resolution_error(self):
        exc = PlatformResolutionError("no platform")
        assert exc.error_code == "EFP-IMG14"

    def test_init_container_build_error(self):
        exc = InitContainerBuildError("init fail")
        assert exc.error_code == "EFP-IMG15"

    def test_sidecar_build_error(self):
        exc = SidecarBuildError("sidecar fail")
        assert exc.error_code == "EFP-IMG16"

    def test_catalog_capacity_error(self):
        exc = CatalogCapacityError("full")
        assert exc.error_code == "EFP-IMG17"

    def test_circular_dependency_error(self):
        exc = CircularDependencyError("circular")
        assert exc.error_code == "EFP-IMG18"

    def test_metadata_validation_error(self):
        exc = MetadataValidationError("invalid")
        assert exc.error_code == "EFP-IMG19"

    def test_fizzimage_middleware_error(self):
        exc = FizzImageMiddlewareError(42, "reason")
        assert exc.error_code == "EFP-IMG20"
        assert exc.evaluation_number == 42
        assert exc.context["evaluation_number"] == 42
        assert "42" in str(exc)


# ============================================================
# Event Type Constants
# ============================================================


class TestEventTypes:
    """Verify all event type constants are defined."""

    def test_catalog_loaded(self):
        assert FIZZIMAGE_CATALOG_LOADED == "fizzimage.catalog.loaded"

    def test_catalog_stats(self):
        assert FIZZIMAGE_CATALOG_STATS == "fizzimage.catalog.stats"

    def test_image_registered(self):
        assert FIZZIMAGE_IMAGE_REGISTERED == "fizzimage.image.registered"

    def test_base_built(self):
        assert FIZZIMAGE_BASE_BUILT == "fizzimage.base.built"

    def test_eval_built(self):
        assert FIZZIMAGE_EVAL_BUILT == "fizzimage.eval.built"

    def test_subsystem_generated(self):
        assert FIZZIMAGE_SUBSYSTEM_GENERATED == "fizzimage.subsystem.generated"

    def test_init_built(self):
        assert FIZZIMAGE_INIT_BUILT == "fizzimage.init.built"

    def test_sidecar_built(self):
        assert FIZZIMAGE_SIDECAR_BUILT == "fizzimage.sidecar.built"

    def test_multi_arch_indexed(self):
        assert FIZZIMAGE_MULTI_ARCH_INDEXED == "fizzimage.multiarch.indexed"

    def test_scan_started(self):
        assert FIZZIMAGE_SCAN_STARTED == "fizzimage.scan.started"

    def test_scan_completed(self):
        assert FIZZIMAGE_SCAN_COMPLETED == "fizzimage.scan.completed"

    def test_scan_blocked(self):
        assert FIZZIMAGE_SCAN_BLOCKED == "fizzimage.scan.blocked"

    def test_version_bumped(self):
        assert FIZZIMAGE_VERSION_BUMPED == "fizzimage.version.bumped"

    def test_image_removed(self):
        assert FIZZIMAGE_IMAGE_REMOVED == "fizzimage.image.removed"

    def test_build_all_started(self):
        assert FIZZIMAGE_BUILD_ALL_STARTED == "fizzimage.build_all.started"

    def test_build_all_completed(self):
        assert FIZZIMAGE_BUILD_ALL_COMPLETED == "fizzimage.build_all.completed"
