"""
Enterprise FizzBuzz Platform - FizzRegistry Test Suite

Comprehensive tests for the OCI Distribution-Compliant Image Registry.
Validates content-addressable blob storage, SHA-256 digest computation,
OCI manifest management, repository tag CRUD, FizzFile DSL parsing,
image builder with layer caching, mark-and-sweep garbage collection,
cosign-style HMAC image signing, vulnerability scanning with CVE
database, middleware integration, dashboard rendering, factory wiring,
and all 20 exception classes.

Container images must be stored somewhere.  These tests ensure that
somewhere works.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from fizzregistry import (
    DEFAULT_BUILD_TAG,
    DEFAULT_DASHBOARD_WIDTH,
    DEFAULT_GC_GRACE_PERIOD,
    DEFAULT_MAX_BLOBS,
    DEFAULT_MAX_REPOS,
    DEFAULT_MAX_TAGS,
    DIGEST_ALGORITHM,
    DIGEST_PREFIX,
    FIZZFILE_COMMENT,
    FIZZFILE_CONTINUATION,
    MAX_INSTRUCTION_CACHE_SIZE,
    MIDDLEWARE_PRIORITY,
    OCI_CONFIG_MEDIA_TYPE,
    OCI_INDEX_MEDIA_TYPE,
    OCI_LAYER_GZIP_MEDIA_TYPE,
    OCI_LAYER_MEDIA_TYPE,
    OCI_MANIFEST_MEDIA_TYPE,
    OCI_SIGNATURE_MEDIA_TYPE,
    SCHEMA_VERSION,
    SCRATCH_IMAGE,
    BlobStore,
    BuildContext,
    BuildPhase,
    ContainerConfig,
    FizzFileInstruction,
    FizzFileParser,
    FizzFileStep,
    FizzRegistryMiddleware,
    GCPhase,
    GCReport,
    GarbageCollector,
    HistoryEntry,
    ImageBuilder,
    ImagePlatformArch,
    ImagePlatformOS,
    ImageSignature,
    ImageSigner,
    ManifestSchemaVersion,
    OCIDescriptor,
    OCIImageConfig,
    OCIImageIndex,
    OCIManifest,
    OCIPlatform,
    RegistryAPI,
    RegistryDashboard,
    RegistryOperation,
    RegistryStats,
    Repository,
    RootFS,
    SignatureStatus,
    TagReference,
    TagState,
    VulnerabilityFinding,
    VulnerabilityReport,
    VulnerabilityScanner,
    VulnerabilitySeverity,
    create_fizzregistry_subsystem,
)
from enterprise_fizzbuzz.infrastructure.fizzregistry import _BlobStoreMeta
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
from enterprise_fizzbuzz.domain.exceptions.container_registry import (
    ManifestValidationError as RegistryManifestValidationError,
)
from config import _SingletonMeta
from models import EventType, FizzBuzzResult, ProcessingContext


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    _BlobStoreMeta.reset()
    yield
    _SingletonMeta.reset()
    _BlobStoreMeta.reset()


# ============================================================
# Constants Tests
# ============================================================


class TestConstants:
    """Validate registry constants."""

    def test_oci_manifest_media_type(self):
        assert OCI_MANIFEST_MEDIA_TYPE == "application/vnd.oci.image.manifest.v1+json"

    def test_oci_index_media_type(self):
        assert OCI_INDEX_MEDIA_TYPE == "application/vnd.oci.image.index.v1+json"

    def test_oci_config_media_type(self):
        assert OCI_CONFIG_MEDIA_TYPE == "application/vnd.oci.image.config.v1+json"

    def test_oci_layer_media_type(self):
        assert OCI_LAYER_MEDIA_TYPE == "application/vnd.oci.image.layer.v1.tar"

    def test_oci_layer_gzip_media_type(self):
        assert "gzip" in OCI_LAYER_GZIP_MEDIA_TYPE

    def test_oci_signature_media_type(self):
        assert "cosign" in OCI_SIGNATURE_MEDIA_TYPE

    def test_default_max_blobs(self):
        assert DEFAULT_MAX_BLOBS == 4096

    def test_default_max_repos(self):
        assert DEFAULT_MAX_REPOS == 256

    def test_default_max_tags(self):
        assert DEFAULT_MAX_TAGS == 1024

    def test_default_gc_grace_period(self):
        assert DEFAULT_GC_GRACE_PERIOD == 86400.0

    def test_default_dashboard_width(self):
        assert DEFAULT_DASHBOARD_WIDTH == 72

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 110

    def test_digest_algorithm(self):
        assert DIGEST_ALGORITHM == "sha256"

    def test_digest_prefix(self):
        assert DIGEST_PREFIX == "sha256:"

    def test_scratch_image(self):
        assert SCRATCH_IMAGE == "scratch"

    def test_fizzfile_comment(self):
        assert FIZZFILE_COMMENT == "#"

    def test_fizzfile_continuation(self):
        assert FIZZFILE_CONTINUATION == "\\"

    def test_default_build_tag(self):
        assert DEFAULT_BUILD_TAG == "latest"

    def test_schema_version(self):
        assert SCHEMA_VERSION == 2

    def test_max_instruction_cache_size(self):
        assert MAX_INSTRUCTION_CACHE_SIZE == 512


# ============================================================
# Enum Tests
# ============================================================


class TestEnums:
    """Validate registry enums."""

    def test_manifest_schema_version_v1(self):
        assert ManifestSchemaVersion.V1.value == 1

    def test_manifest_schema_version_v2(self):
        assert ManifestSchemaVersion.V2.value == 2

    def test_image_platform_os_values(self):
        assert ImagePlatformOS.LINUX.value == "linux"
        assert ImagePlatformOS.FIZZBUZZ_OS.value == "fizzbuzz-os"

    def test_image_platform_arch_values(self):
        assert ImagePlatformArch.AMD64.value == "amd64"
        assert ImagePlatformArch.FIZZ_ARCH.value == "fizz-arch"

    def test_tag_state_members(self):
        assert len(TagState) == 3
        assert TagState.ACTIVE.name == "ACTIVE"
        assert TagState.DEPRECATED.name == "DEPRECATED"
        assert TagState.DELETED.name == "DELETED"

    def test_gc_phase_members(self):
        assert len(GCPhase) == 4

    def test_signature_status_members(self):
        assert len(SignatureStatus) == 5

    def test_vulnerability_severity_members(self):
        assert len(VulnerabilitySeverity) == 6

    def test_fizzfile_instruction_members(self):
        assert len(FizzFileInstruction) == 8
        assert FizzFileInstruction.FROM.value == "FROM"
        assert FizzFileInstruction.FIZZ.value == "FIZZ"
        assert FizzFileInstruction.BUZZ.value == "BUZZ"
        assert FizzFileInstruction.RUN.value == "RUN"
        assert FizzFileInstruction.COPY.value == "COPY"
        assert FizzFileInstruction.ENV.value == "ENV"
        assert FizzFileInstruction.ENTRYPOINT.value == "ENTRYPOINT"
        assert FizzFileInstruction.LABEL.value == "LABEL"

    def test_build_phase_members(self):
        assert len(BuildPhase) == 8

    def test_registry_operation_members(self):
        assert len(RegistryOperation) == 10


# ============================================================
# Dataclass Tests
# ============================================================


class TestOCIDescriptor:
    """Validate OCI content descriptor."""

    def test_creation(self):
        desc = OCIDescriptor(
            media_type=OCI_LAYER_MEDIA_TYPE,
            digest="sha256:abc123",
            size=1024,
        )
        assert desc.media_type == OCI_LAYER_MEDIA_TYPE
        assert desc.digest == "sha256:abc123"
        assert desc.size == 1024

    def test_to_dict(self):
        desc = OCIDescriptor(
            media_type=OCI_LAYER_MEDIA_TYPE,
            digest="sha256:abc",
            size=100,
        )
        d = desc.to_dict()
        assert d["mediaType"] == OCI_LAYER_MEDIA_TYPE
        assert d["digest"] == "sha256:abc"
        assert d["size"] == 100

    def test_to_dict_with_annotations(self):
        desc = OCIDescriptor(
            media_type=OCI_LAYER_MEDIA_TYPE,
            digest="sha256:abc",
            size=100,
            annotations={"key": "value"},
        )
        d = desc.to_dict()
        assert d["annotations"] == {"key": "value"}

    def test_to_dict_with_platform(self):
        platform = OCIPlatform(os="linux", architecture="amd64")
        desc = OCIDescriptor(
            media_type=OCI_MANIFEST_MEDIA_TYPE,
            digest="sha256:abc",
            size=100,
            platform=platform,
        )
        d = desc.to_dict()
        assert "platform" in d
        assert d["platform"]["os"] == "linux"


class TestOCIPlatform:
    """Validate OCI platform specification."""

    def test_defaults(self):
        p = OCIPlatform()
        assert p.os == "fizzbuzz-os"
        assert p.architecture == "fizz-arch"

    def test_to_dict(self):
        p = OCIPlatform(os="linux", architecture="amd64", variant="v8")
        d = p.to_dict()
        assert d["os"] == "linux"
        assert d["architecture"] == "amd64"
        assert d["variant"] == "v8"


class TestOCIManifest:
    """Validate OCI image manifest."""

    def test_defaults(self):
        m = OCIManifest()
        assert m.schema_version == 2
        assert m.media_type == OCI_MANIFEST_MEDIA_TYPE

    def test_to_dict(self):
        m = OCIManifest(
            config=OCIDescriptor(
                media_type=OCI_CONFIG_MEDIA_TYPE,
                digest="sha256:cfg",
                size=50,
            ),
            layers=[
                OCIDescriptor(
                    media_type=OCI_LAYER_MEDIA_TYPE,
                    digest="sha256:layer1",
                    size=100,
                ),
            ],
        )
        d = m.to_dict()
        assert d["schemaVersion"] == 2
        assert d["config"]["digest"] == "sha256:cfg"
        assert len(d["layers"]) == 1

    def test_compute_digest(self):
        m = OCIManifest()
        digest = m.compute_digest()
        assert digest.startswith(DIGEST_PREFIX)

    def test_total_size(self):
        m = OCIManifest(
            config=OCIDescriptor(media_type=OCI_CONFIG_MEDIA_TYPE, digest="sha256:c", size=50),
            layers=[
                OCIDescriptor(media_type=OCI_LAYER_MEDIA_TYPE, digest="sha256:l1", size=100),
                OCIDescriptor(media_type=OCI_LAYER_MEDIA_TYPE, digest="sha256:l2", size=200),
            ],
        )
        assert m.total_size == 350


class TestOCIImageIndex:
    """Validate OCI image index."""

    def test_defaults(self):
        idx = OCIImageIndex()
        assert idx.schema_version == 2
        assert idx.media_type == OCI_INDEX_MEDIA_TYPE

    def test_to_dict(self):
        idx = OCIImageIndex(
            manifests=[
                OCIDescriptor(
                    media_type=OCI_MANIFEST_MEDIA_TYPE,
                    digest="sha256:m1",
                    size=100,
                    platform=OCIPlatform(os="linux", architecture="amd64"),
                ),
            ],
        )
        d = idx.to_dict()
        assert len(d["manifests"]) == 1


class TestRootFS:
    """Validate root filesystem specification."""

    def test_defaults(self):
        r = RootFS()
        assert r.type == "layers"
        assert r.diff_ids == []

    def test_to_dict(self):
        r = RootFS(diff_ids=["sha256:a", "sha256:b"])
        d = r.to_dict()
        assert d["type"] == "layers"
        assert len(d["diff_ids"]) == 2


class TestHistoryEntry:
    """Validate build history entry."""

    def test_defaults(self):
        h = HistoryEntry()
        assert h.created == ""
        assert h.empty_layer is False

    def test_to_dict(self):
        h = HistoryEntry(created_by="FROM scratch", empty_layer=True)
        d = h.to_dict()
        assert d["created_by"] == "FROM scratch"
        assert d["empty_layer"] is True


class TestContainerConfig:
    """Validate container configuration."""

    def test_defaults(self):
        c = ContainerConfig()
        assert c.working_dir == "/"
        assert c.entrypoint == []

    def test_to_dict(self):
        c = ContainerConfig(
            entrypoint=["python", "-m", "fizzbuzz"],
            env=["FOO=bar"],
            labels={"version": "1.0"},
        )
        d = c.to_dict()
        assert d["Entrypoint"] == ["python", "-m", "fizzbuzz"]
        assert d["Env"] == ["FOO=bar"]
        assert d["Labels"]["version"] == "1.0"


class TestOCIImageConfig:
    """Validate OCI image configuration."""

    def test_defaults(self):
        c = OCIImageConfig()
        assert c.architecture == "fizz-arch"
        assert c.os == "fizzbuzz-os"

    def test_compute_digest(self):
        c = OCIImageConfig()
        digest = c.compute_digest()
        assert digest.startswith(DIGEST_PREFIX)

    def test_serialize(self):
        c = OCIImageConfig()
        data = c.serialize()
        assert isinstance(data, bytes)
        parsed = json.loads(data)
        assert parsed["architecture"] == "fizz-arch"

    def test_to_dict(self):
        c = OCIImageConfig(
            history=[HistoryEntry(created_by="FROM scratch")],
            config=ContainerConfig(entrypoint=["python"]),
        )
        d = c.to_dict()
        assert "history" in d
        assert "config" in d


class TestTagReference:
    """Validate tag reference."""

    def test_defaults(self):
        t = TagReference()
        assert t.name == ""
        assert t.state == TagState.ACTIVE


class TestFizzFileStep:
    """Validate FizzFile step."""

    def test_defaults(self):
        s = FizzFileStep()
        assert s.instruction == FizzFileInstruction.FROM
        assert s.arguments == ""


class TestBuildContext:
    """Validate build context."""

    def test_defaults(self):
        ctx = BuildContext()
        assert ctx.base_image == SCRATCH_IMAGE
        assert ctx.phase == BuildPhase.INITIALIZING

    def test_build_id_unique(self):
        a = BuildContext()
        _BlobStoreMeta.reset()
        b = BuildContext()
        assert a.build_id != b.build_id


class TestImageSignature:
    """Validate image signature."""

    def test_defaults(self):
        sig = ImageSignature()
        assert sig.signer == "Bob McFizzington"
        assert sig.status == SignatureStatus.UNSIGNED


class TestVulnerabilityFinding:
    """Validate vulnerability finding."""

    def test_defaults(self):
        f = VulnerabilityFinding()
        assert f.severity == VulnerabilitySeverity.UNKNOWN


class TestVulnerabilityReport:
    """Validate vulnerability report."""

    def test_empty_report(self):
        r = VulnerabilityReport()
        assert r.total_count == 0
        assert r.critical_count == 0
        assert r.has_critical is False

    def test_report_counts(self):
        r = VulnerabilityReport(
            findings=[
                VulnerabilityFinding(severity=VulnerabilitySeverity.CRITICAL),
                VulnerabilityFinding(severity=VulnerabilitySeverity.HIGH),
                VulnerabilityFinding(severity=VulnerabilitySeverity.MEDIUM),
                VulnerabilityFinding(severity=VulnerabilitySeverity.LOW),
            ]
        )
        assert r.total_count == 4
        assert r.critical_count == 1
        assert r.high_count == 1
        assert r.medium_count == 1
        assert r.low_count == 1
        assert r.has_critical is True


class TestGCReport:
    """Validate GC report."""

    def test_defaults(self):
        r = GCReport()
        assert r.phase == GCPhase.IDLE
        assert r.blobs_swept == 0


class TestRegistryStats:
    """Validate registry statistics."""

    def test_defaults(self):
        s = RegistryStats()
        assert s.total_blobs == 0
        assert s.cache_hit_rate == 0.0

    def test_cache_hit_rate(self):
        s = RegistryStats(cache_hits=3, cache_misses=7)
        assert s.cache_hit_rate == 30.0

    def test_dedup_ratio_no_manifests(self):
        s = RegistryStats()
        assert s.dedup_ratio == 1.0


# ============================================================
# BlobStore Tests
# ============================================================


class TestBlobStore:
    """Validate content-addressable blob storage."""

    def test_put_returns_digest(self):
        store = BlobStore()
        data = b"hello fizzbuzz"
        digest = store.put(data)
        assert digest.startswith(DIGEST_PREFIX)

    def test_put_deduplication(self):
        store = BlobStore()
        data = b"dedup test"
        d1 = store.put(data)
        d2 = store.put(data)
        assert d1 == d2
        assert store.blob_count == 1

    def test_get_returns_data(self):
        store = BlobStore()
        data = b"test content"
        digest = store.put(data)
        assert store.get(digest) == data

    def test_get_not_found(self):
        store = BlobStore()
        with pytest.raises(BlobNotFoundError):
            store.get("sha256:nonexistent")

    def test_exists(self):
        store = BlobStore()
        data = b"exist check"
        digest = store.put(data)
        assert store.exists(digest) is True
        assert store.exists("sha256:nope") is False

    def test_delete(self):
        store = BlobStore()
        data = b"to delete"
        digest = store.put(data)
        store.delete(digest)
        assert store.exists(digest) is False

    def test_delete_not_found(self):
        store = BlobStore()
        with pytest.raises(BlobNotFoundError):
            store.delete("sha256:nope")

    def test_stat(self):
        store = BlobStore()
        data = b"stat test"
        digest = store.put(data, OCI_LAYER_GZIP_MEDIA_TYPE)
        size, media = store.stat(digest)
        assert size == len(data)
        assert media == OCI_LAYER_GZIP_MEDIA_TYPE

    def test_stat_not_found(self):
        store = BlobStore()
        with pytest.raises(BlobNotFoundError):
            store.stat("sha256:nope")

    def test_blob_count(self):
        store = BlobStore()
        assert store.blob_count == 0
        store.put(b"a")
        store.put(b"b")
        assert store.blob_count == 2

    def test_total_bytes(self):
        store = BlobStore()
        store.put(b"abc")
        store.put(b"defgh")
        assert store.total_bytes == 8

    def test_digests(self):
        store = BlobStore()
        d1 = store.put(b"x")
        d2 = store.put(b"y")
        digests = store.digests
        assert d1 in digests
        assert d2 in digests

    def test_ref_counting(self):
        store = BlobStore()
        digest = store.put(b"ref test")
        assert store.get_ref_count(digest) == 0
        store.increment_ref(digest)
        assert store.get_ref_count(digest) == 1
        store.decrement_ref(digest)
        assert store.get_ref_count(digest) == 0

    def test_capacity_limit(self):
        store = BlobStore(max_blobs=2)
        store.put(b"a")
        store.put(b"b")
        with pytest.raises(BlobStoreFullError):
            store.put(b"c")

    def test_compute_digest_static(self):
        digest = BlobStore.compute_digest(b"test")
        expected = DIGEST_PREFIX + hashlib.sha256(b"test").hexdigest()
        assert digest == expected

    def test_get_unreferenced(self):
        store = BlobStore()
        d1 = store.put(b"unref")
        # With 0 grace period, it should be eligible
        unreferenced = store.get_unreferenced(grace_period=0.0)
        assert d1 in unreferenced

    def test_get_unreferenced_with_refs(self):
        store = BlobStore()
        d1 = store.put(b"ref")
        store.increment_ref(d1)
        unreferenced = store.get_unreferenced(grace_period=0.0)
        assert d1 not in unreferenced

    def test_total_pushes(self):
        store = BlobStore()
        store.put(b"a")
        store.put(b"b")
        assert store.total_pushes == 2

    def test_total_pulls(self):
        store = BlobStore()
        d = store.put(b"data")
        store.get(d)
        assert store.total_pulls == 1

    def test_singleton_behavior(self):
        s1 = BlobStore()
        s2 = BlobStore()
        assert s1 is s2


# ============================================================
# Repository Tests
# ============================================================


class TestRepository:
    """Validate repository tag management."""

    def test_creation(self):
        repo = Repository("test-repo")
        assert repo.name == "test-repo"
        assert repo.tag_count == 0

    def test_put_manifest(self):
        repo = Repository("test-repo")
        manifest = OCIManifest()
        digest = repo.put_manifest("latest", manifest)
        assert digest.startswith(DIGEST_PREFIX)
        assert repo.tag_count == 1

    def test_get_manifest_by_tag(self):
        repo = Repository("test-repo")
        manifest = OCIManifest(annotations={"test": "value"})
        repo.put_manifest("v1.0", manifest)
        retrieved = repo.get_manifest("v1.0")
        assert retrieved.annotations.get("test") == "value"

    def test_get_manifest_by_digest(self):
        repo = Repository("test-repo")
        manifest = OCIManifest()
        digest = repo.put_manifest("latest", manifest)
        retrieved = repo.get_manifest(digest)
        assert retrieved is not None

    def test_get_manifest_tag_not_found(self):
        repo = Repository("test-repo")
        with pytest.raises(TagNotFoundError):
            repo.get_manifest("nonexistent")

    def test_delete_manifest(self):
        repo = Repository("test-repo")
        manifest = OCIManifest()
        repo.put_manifest("latest", manifest)
        repo.delete_manifest("latest")
        with pytest.raises(TagNotFoundError):
            repo.get_manifest("latest")

    def test_list_tags(self):
        repo = Repository("test-repo")
        repo.put_manifest("v1.0", OCIManifest())
        repo.put_manifest("v2.0", OCIManifest(annotations={"v": "2"}))
        tags = repo.list_tags()
        assert "v1.0" in tags
        assert "v2.0" in tags

    def test_has_tag(self):
        repo = Repository("test-repo")
        repo.put_manifest("latest", OCIManifest())
        assert repo.has_tag("latest") is True
        assert repo.has_tag("nonexistent") is False

    def test_tag_limit(self):
        repo = Repository("test-repo", max_tags=2)
        repo.put_manifest("v1", OCIManifest())
        repo.put_manifest("v2", OCIManifest(annotations={"v": "2"}))
        with pytest.raises(TagLimitError):
            repo.put_manifest("v3", OCIManifest(annotations={"v": "3"}))

    def test_get_tag(self):
        repo = Repository("test-repo")
        repo.put_manifest("latest", OCIManifest())
        tag = repo.get_tag("latest")
        assert tag.name == "latest"
        assert tag.state == TagState.ACTIVE

    def test_get_tag_not_found(self):
        repo = Repository("test-repo")
        with pytest.raises(TagNotFoundError):
            repo.get_tag("nope")

    def test_tag_history(self):
        repo = Repository("test-repo")
        m1 = OCIManifest()
        m2 = OCIManifest(annotations={"version": "2"})
        repo.put_manifest("latest", m1)
        repo.put_manifest("latest", m2)
        history = repo.tag_history("latest")
        assert len(history) == 2

    def test_tag_history_not_found(self):
        repo = Repository("test-repo")
        with pytest.raises(TagNotFoundError):
            repo.tag_history("nope")

    def test_manifest_count(self):
        repo = Repository("test-repo")
        repo.put_manifest("v1", OCIManifest())
        assert repo.manifest_count >= 1

    def test_get_manifest_digests(self):
        repo = Repository("test-repo")
        repo.put_manifest("v1", OCIManifest())
        digests = repo.get_manifest_digests()
        assert len(digests) >= 1

    def test_tag_update_preserves_active(self):
        repo = Repository("test-repo")
        repo.put_manifest("latest", OCIManifest())
        repo.put_manifest("latest", OCIManifest(annotations={"v": "2"}))
        tag = repo.get_tag("latest")
        assert tag.state == TagState.ACTIVE


# ============================================================
# RegistryAPI Tests
# ============================================================


class TestRegistryAPI:
    """Validate OCI Distribution Specification API."""

    def _make_api(self, **kwargs):
        store = BlobStore(**kwargs.pop("blob_kwargs", {}))
        return RegistryAPI(blob_store=store, **kwargs), store

    def test_put_blob(self):
        api, store = self._make_api()
        digest = api.put_blob("test-repo", b"layer data")
        assert digest.startswith(DIGEST_PREFIX)

    def test_get_blob(self):
        api, store = self._make_api()
        digest = api.put_blob("test-repo", b"content")
        data = api.get_blob("test-repo", digest)
        assert data == b"content"

    def test_head_blob(self):
        api, store = self._make_api()
        digest = api.put_blob("test-repo", b"head test")
        size, media = api.head_blob("test-repo", digest)
        assert size == len(b"head test")

    def test_delete_blob(self):
        api, store = self._make_api()
        digest = api.put_blob("test-repo", b"to delete")
        api.delete_blob("test-repo", digest)
        with pytest.raises(BlobNotFoundError):
            api.get_blob("test-repo", digest)

    def test_put_manifest(self):
        api, store = self._make_api()
        # First push config and layer blobs
        config_data = b'{"architecture":"fizz-arch"}'
        config_digest = api.put_blob("test-repo", config_data, OCI_CONFIG_MEDIA_TYPE)
        layer_data = b"layer content"
        layer_digest = api.put_blob("test-repo", layer_data)

        manifest = OCIManifest(
            config=OCIDescriptor(media_type=OCI_CONFIG_MEDIA_TYPE, digest=config_digest, size=len(config_data)),
            layers=[OCIDescriptor(media_type=OCI_LAYER_MEDIA_TYPE, digest=layer_digest, size=len(layer_data))],
        )
        digest = api.put_manifest("test-repo", "latest", manifest)
        assert digest.startswith(DIGEST_PREFIX)

    def test_put_manifest_missing_blob(self):
        api, store = self._make_api()
        manifest = OCIManifest(
            config=OCIDescriptor(media_type=OCI_CONFIG_MEDIA_TYPE, digest="sha256:missing", size=10),
        )
        with pytest.raises(RegistryManifestValidationError):
            api.put_manifest("test-repo", "latest", manifest)

    def test_get_manifest(self):
        api, store = self._make_api()
        config_digest = api.put_blob("test-repo", b"cfg", OCI_CONFIG_MEDIA_TYPE)
        manifest = OCIManifest(
            config=OCIDescriptor(media_type=OCI_CONFIG_MEDIA_TYPE, digest=config_digest, size=3),
        )
        api.put_manifest("test-repo", "v1", manifest)
        retrieved = api.get_manifest("test-repo", "v1")
        assert retrieved.config.digest == config_digest

    def test_get_manifest_repo_not_found(self):
        api, store = self._make_api()
        with pytest.raises(RepositoryNotFoundError):
            api.get_manifest("nonexistent", "latest")

    def test_head_manifest(self):
        api, store = self._make_api()
        config_digest = api.put_blob("test-repo", b"cfg", OCI_CONFIG_MEDIA_TYPE)
        manifest = OCIManifest(
            config=OCIDescriptor(media_type=OCI_CONFIG_MEDIA_TYPE, digest=config_digest, size=3),
        )
        api.put_manifest("test-repo", "v1", manifest)
        digest = api.head_manifest("test-repo", "v1")
        assert digest.startswith(DIGEST_PREFIX)

    def test_delete_manifest(self):
        api, store = self._make_api()
        config_digest = api.put_blob("test-repo", b"cfg", OCI_CONFIG_MEDIA_TYPE)
        manifest = OCIManifest(
            config=OCIDescriptor(media_type=OCI_CONFIG_MEDIA_TYPE, digest=config_digest, size=3),
        )
        api.put_manifest("test-repo", "v1", manifest)
        api.delete_manifest("test-repo", "v1")
        with pytest.raises((TagNotFoundError, ManifestNotFoundError)):
            api.get_manifest("test-repo", "v1")

    def test_delete_manifest_not_found(self):
        api, store = self._make_api()
        api.put_blob("test-repo", b"init")  # auto-create repo
        with pytest.raises(ManifestNotFoundError):
            api.delete_manifest("test-repo", "nonexistent")

    def test_catalog(self):
        api, store = self._make_api()
        api.put_blob("repo-a", b"a")
        api.put_blob("repo-b", b"b")
        catalog = api.catalog()
        assert "repo-a" in catalog
        assert "repo-b" in catalog

    def test_list_tags(self):
        api, store = self._make_api()
        config_digest = api.put_blob("test-repo", b"cfg", OCI_CONFIG_MEDIA_TYPE)
        manifest = OCIManifest(
            config=OCIDescriptor(media_type=OCI_CONFIG_MEDIA_TYPE, digest=config_digest, size=3),
        )
        api.put_manifest("test-repo", "v1", manifest)
        api.put_manifest("test-repo", "v2", manifest)
        tags = api.list_tags("test-repo")
        assert "v1" in tags
        assert "v2" in tags

    def test_list_tags_repo_not_found(self):
        api, store = self._make_api()
        with pytest.raises(RepositoryNotFoundError):
            api.list_tags("nonexistent")

    def test_repo_count(self):
        api, store = self._make_api()
        api.put_blob("r1", b"1")
        api.put_blob("r2", b"2")
        assert api.repo_count == 2

    def test_repo_limit(self):
        api, store = self._make_api(max_repos=1)
        api.put_blob("r1", b"1")
        with pytest.raises(RepositoryLimitError):
            api.put_blob("r2", b"2")

    def test_op_counts(self):
        api, store = self._make_api()
        api.put_blob("r", b"data")
        counts = api.op_counts
        assert counts[RegistryOperation.BLOB_PUT] == 1

    def test_auto_create_repo(self):
        api, store = self._make_api()
        api.put_blob("new-repo", b"auto")
        assert api.repo_count == 1

    def test_get_repo(self):
        api, store = self._make_api()
        api.put_blob("my-repo", b"x")
        repo = api.get_repo("my-repo")
        assert repo.name == "my-repo"


# ============================================================
# FizzFile Parser Tests
# ============================================================


class TestFizzFileParser:
    """Validate FizzFile build DSL parser."""

    def test_parse_simple(self):
        content = "FROM scratch\nFIZZ 3 Fizz\nBUZZ 5 Buzz"
        parser = FizzFileParser()
        steps = parser.parse(content)
        assert len(steps) == 3
        assert steps[0].instruction == FizzFileInstruction.FROM
        assert steps[1].instruction == FizzFileInstruction.FIZZ
        assert steps[2].instruction == FizzFileInstruction.BUZZ

    def test_parse_from_required(self):
        content = "FIZZ 3 Fizz"
        parser = FizzFileParser()
        with pytest.raises(FizzFileMissingFromError):
            parser.parse(content)

    def test_parse_empty(self):
        parser = FizzFileParser()
        with pytest.raises(FizzFileMissingFromError):
            parser.parse("")

    def test_parse_comments(self):
        content = "# This is a comment\nFROM scratch\n# Another comment\nFIZZ 3 Fizz"
        parser = FizzFileParser()
        steps = parser.parse(content)
        assert len(steps) == 2

    def test_parse_run(self):
        content = "FROM scratch\nRUN echo hello"
        parser = FizzFileParser()
        steps = parser.parse(content)
        assert steps[1].instruction == FizzFileInstruction.RUN
        assert "echo hello" in steps[1].arguments

    def test_parse_copy(self):
        content = "FROM scratch\nCOPY src dest"
        parser = FizzFileParser()
        steps = parser.parse(content)
        assert steps[1].instruction == FizzFileInstruction.COPY

    def test_parse_env(self):
        content = "FROM scratch\nENV FOO=bar"
        parser = FizzFileParser()
        steps = parser.parse(content)
        assert steps[1].instruction == FizzFileInstruction.ENV

    def test_parse_entrypoint(self):
        content = 'FROM scratch\nENTRYPOINT ["python", "-m", "fizzbuzz"]'
        parser = FizzFileParser()
        steps = parser.parse(content)
        assert steps[1].instruction == FizzFileInstruction.ENTRYPOINT

    def test_parse_label(self):
        content = 'FROM scratch\nLABEL version="1.0"'
        parser = FizzFileParser()
        steps = parser.parse(content)
        assert steps[1].instruction == FizzFileInstruction.LABEL

    def test_parse_invalid_instruction(self):
        content = "FROM scratch\nINVALID command"
        parser = FizzFileParser()
        with pytest.raises(FizzFileParseError):
            parser.parse(content)

    def test_parse_fizz_invalid_divisor(self):
        content = "FROM scratch\nFIZZ abc Fizz"
        parser = FizzFileParser()
        with pytest.raises(FizzFileParseError):
            parser.parse(content)

    def test_parse_fizz_missing_word(self):
        content = "FROM scratch\nFIZZ 3"
        parser = FizzFileParser()
        with pytest.raises(FizzFileParseError):
            parser.parse(content)

    def test_parse_copy_missing_dest(self):
        content = "FROM scratch\nCOPY src"
        parser = FizzFileParser()
        with pytest.raises(FizzFileParseError):
            parser.parse(content)

    def test_parse_env_missing_equals(self):
        content = "FROM scratch\nENV NOEQUALS"
        parser = FizzFileParser()
        with pytest.raises(FizzFileParseError):
            parser.parse(content)

    def test_parse_line_continuation(self):
        content = "FROM \\\nscratch\nFIZZ 3 Fizz"
        parser = FizzFileParser()
        steps = parser.parse(content)
        assert steps[0].instruction == FizzFileInstruction.FROM
        assert "scratch" in steps[0].arguments

    def test_parse_case_insensitive(self):
        content = "from scratch\nfizz 3 Fizz"
        parser = FizzFileParser()
        steps = parser.parse(content)
        assert len(steps) == 2

    def test_parse_with_image_tag(self):
        content = "FROM fizzbuzz:v1.0\nFIZZ 3 Fizz"
        parser = FizzFileParser()
        steps = parser.parse(content)
        assert steps[0].arguments == "fizzbuzz:v1.0"

    def test_parse_line_numbers(self):
        content = "# comment\nFROM scratch\nFIZZ 3 Fizz"
        parser = FizzFileParser()
        steps = parser.parse(content)
        assert steps[0].line_number == 2
        assert steps[1].line_number == 3

    def test_parse_original_line(self):
        content = "FROM scratch\nFIZZ 3 Fizz"
        parser = FizzFileParser()
        steps = parser.parse(content)
        assert steps[0].original_line == "FROM scratch"

    def test_parse_multiple_fizz_buzz(self):
        content = "FROM scratch\nFIZZ 3 Fizz\nBUZZ 5 Buzz\nFIZZ 7 Bazz"
        parser = FizzFileParser()
        steps = parser.parse(content)
        assert len(steps) == 4

    def test_parse_all_instructions(self):
        content = (
            "FROM scratch\n"
            "FIZZ 3 Fizz\n"
            "BUZZ 5 Buzz\n"
            "RUN make build\n"
            "COPY app.py /app/\n"
            "ENV MODE=production\n"
            'ENTRYPOINT ["python"]\n'
            'LABEL version="2.0"'
        )
        parser = FizzFileParser()
        steps = parser.parse(content)
        assert len(steps) == 8


# ============================================================
# ImageBuilder Tests
# ============================================================


class TestImageBuilder:
    """Validate image builder with layer caching."""

    def _make_builder(self):
        store = BlobStore()
        api = RegistryAPI(blob_store=store)
        builder = ImageBuilder(blob_store=store, registry_api=api)
        return builder, api, store

    def test_build_from_scratch(self):
        builder, api, store = self._make_builder()
        fizzfile = "FROM scratch\nFIZZ 3 Fizz\nBUZZ 5 Buzz"
        digest = builder.build(fizzfile, "test-image")
        assert digest.startswith(DIGEST_PREFIX)

    def test_build_creates_manifest(self):
        builder, api, store = self._make_builder()
        fizzfile = "FROM scratch\nFIZZ 3 Fizz"
        builder.build(fizzfile, "test-image", "v1")
        manifest = api.get_manifest("test-image", "v1")
        assert manifest is not None
        assert len(manifest.layers) > 0

    def test_build_with_env(self):
        builder, api, store = self._make_builder()
        fizzfile = "FROM scratch\nENV MODE=production"
        builder.build(fizzfile, "env-test")
        manifest = api.get_manifest("env-test", "latest")
        assert manifest is not None

    def test_build_with_run(self):
        builder, api, store = self._make_builder()
        fizzfile = "FROM scratch\nRUN echo hello"
        builder.build(fizzfile, "run-test")
        manifest = api.get_manifest("run-test", "latest")
        assert len(manifest.layers) > 0

    def test_build_with_copy(self):
        builder, api, store = self._make_builder()
        fizzfile = "FROM scratch\nCOPY src dest"
        builder.build(fizzfile, "copy-test")
        manifest = api.get_manifest("copy-test", "latest")
        assert len(manifest.layers) > 0

    def test_build_with_entrypoint(self):
        builder, api, store = self._make_builder()
        fizzfile = 'FROM scratch\nENTRYPOINT ["python"]'
        builder.build(fizzfile, "ep-test")
        # Entrypoint doesn't create a layer
        manifest = api.get_manifest("ep-test", "latest")
        assert manifest is not None

    def test_build_with_label(self):
        builder, api, store = self._make_builder()
        fizzfile = 'FROM scratch\nLABEL version="1.0"'
        builder.build(fizzfile, "label-test")
        manifest = api.get_manifest("label-test", "latest")
        assert manifest is not None

    def test_build_layer_caching(self):
        builder, api, store = self._make_builder()
        fizzfile = "FROM scratch\nFIZZ 3 Fizz"
        builder.build(fizzfile, "cache-test", "v1")
        hits_before = builder.cache_hits
        _BlobStoreMeta.reset()
        store2 = BlobStore()
        # Copy blobs to new store
        for d in store.digests:
            try:
                data = store.get(d)
                mt = store._blob_media_types.get(d, OCI_LAYER_MEDIA_TYPE)
                store2.put(data, mt)
            except Exception:
                pass

    def test_build_invalid_fizzfile(self):
        builder, api, store = self._make_builder()
        with pytest.raises(FizzFileMissingFromError):
            builder.build("", "test")

    def test_build_from_nonexistent_base(self):
        builder, api, store = self._make_builder()
        fizzfile = "FROM nonexistent:latest\nFIZZ 3 Fizz"
        # Should not raise — nonexistent base treated as empty
        digest = builder.build(fizzfile, "nobase")
        assert digest.startswith(DIGEST_PREFIX)

    def test_builds_completed(self):
        builder, api, store = self._make_builder()
        builder.build("FROM scratch\nFIZZ 3 Fizz", "repo1")
        builder.build("FROM scratch\nBUZZ 5 Buzz", "repo2")
        assert builder.builds_completed == 2

    def test_cache_size(self):
        builder, api, store = self._make_builder()
        builder.build("FROM scratch\nFIZZ 3 Fizz\nBUZZ 5 Buzz", "repo")
        assert builder.cache_size > 0


# ============================================================
# GarbageCollector Tests
# ============================================================


class TestGarbageCollector:
    """Validate mark-and-sweep garbage collection."""

    def _make_gc(self):
        store = BlobStore()
        api = RegistryAPI(blob_store=store)
        gc = GarbageCollector(blob_store=store, registry_api=api, grace_period=0.0)
        return gc, api, store

    def test_collect_empty(self):
        gc, api, store = self._make_gc()
        report = gc.collect()
        assert report.phase == GCPhase.COMPLETE
        assert report.blobs_swept == 0

    def test_collect_unreferenced_blobs(self):
        gc, api, store = self._make_gc()
        store.put(b"orphan blob")
        report = gc.collect()
        assert report.blobs_swept == 1
        assert report.bytes_reclaimed > 0

    def test_collect_preserves_referenced(self):
        gc, api, store = self._make_gc()
        config_data = b"config data"
        config_digest = api.put_blob("repo", config_data, OCI_CONFIG_MEDIA_TYPE)
        manifest = OCIManifest(
            config=OCIDescriptor(media_type=OCI_CONFIG_MEDIA_TYPE, digest=config_digest, size=len(config_data)),
        )
        api.put_manifest("repo", "latest", manifest)
        report = gc.collect()
        assert store.exists(config_digest)

    def test_gc_runs_counter(self):
        gc, api, store = self._make_gc()
        gc.collect()
        gc.collect()
        assert gc.gc_runs == 2

    def test_total_bytes_reclaimed(self):
        gc, api, store = self._make_gc()
        store.put(b"orphan1")
        store.put(b"orphan2")
        gc.collect()
        assert gc.total_bytes_reclaimed > 0

    def test_gc_report_duration(self):
        gc, api, store = self._make_gc()
        report = gc.collect()
        assert report.duration >= 0


# ============================================================
# ImageSigner Tests
# ============================================================


class TestImageSigner:
    """Validate cosign-style image signing."""

    def _make_signer(self):
        store = BlobStore()
        signer = ImageSigner(blob_store=store)
        return signer, store

    def test_sign(self):
        signer, store = self._make_signer()
        sig = signer.sign("sha256:test_digest")
        assert sig.status == SignatureStatus.SIGNED
        assert sig.manifest_digest == "sha256:test_digest"
        assert sig.signer == "Bob McFizzington"

    def test_verify_valid(self):
        signer, store = self._make_signer()
        signer.sign("sha256:verify_test")
        result = signer.verify("sha256:verify_test")
        assert result.status == SignatureStatus.VERIFIED

    def test_verify_not_signed(self):
        signer, store = self._make_signer()
        with pytest.raises(ImageSignatureError):
            signer.verify("sha256:unsigned")

    def test_signed_count(self):
        signer, store = self._make_signer()
        signer.sign("sha256:a")
        signer.sign("sha256:b")
        assert signer.signed_count == 2

    def test_get_signature(self):
        signer, store = self._make_signer()
        signer.sign("sha256:get_test")
        sig = signer.get_signature("sha256:get_test")
        assert sig is not None
        assert sig.manifest_digest == "sha256:get_test"

    def test_get_signature_not_found(self):
        signer, store = self._make_signer()
        sig = signer.get_signature("sha256:none")
        assert sig is None

    def test_key_id(self):
        signer, store = self._make_signer()
        assert len(signer.key_id) == 16

    def test_signature_stored_as_blob(self):
        signer, store = self._make_signer()
        initial_count = store.blob_count
        signer.sign("sha256:blob_test")
        assert store.blob_count > initial_count


# ============================================================
# VulnerabilityScanner Tests
# ============================================================


class TestVulnerabilityScanner:
    """Validate image vulnerability scanning."""

    def _make_scanner(self):
        store = BlobStore()
        scanner = VulnerabilityScanner(blob_store=store)
        return scanner, store

    def test_scan_empty_manifest(self):
        scanner, store = self._make_scanner()
        manifest = OCIManifest()
        report = scanner.scan("test:latest", manifest)
        assert report.image_ref == "test:latest"
        assert report.layers_scanned == 0

    def test_scan_with_layers(self):
        scanner, store = self._make_scanner()
        layer_data = b"layer content for scanning"
        layer_digest = store.put(layer_data)
        manifest = OCIManifest(
            layers=[OCIDescriptor(media_type=OCI_LAYER_MEDIA_TYPE, digest=layer_digest, size=len(layer_data))],
        )
        report = scanner.scan("test:v1", manifest)
        assert report.layers_scanned == 1

    def test_scan_duration(self):
        scanner, store = self._make_scanner()
        manifest = OCIManifest()
        report = scanner.scan("test:latest", manifest)
        assert report.scan_duration >= 0

    def test_scanned_count(self):
        scanner, store = self._make_scanner()
        scanner.scan("a:latest", OCIManifest())
        scanner.scan("b:latest", OCIManifest())
        assert scanner.scanned_count == 2

    def test_get_report(self):
        scanner, store = self._make_scanner()
        scanner.scan("test:v1", OCIManifest())
        report = scanner.get_report("test:v1")
        assert report is not None

    def test_get_report_not_found(self):
        scanner, store = self._make_scanner()
        assert scanner.get_report("nonexistent") is None

    def test_cve_count(self):
        scanner, store = self._make_scanner()
        assert scanner.cve_count > 0

    def test_custom_cve_database(self):
        store = BlobStore()
        custom_db = [
            VulnerabilityFinding(
                cve_id="CVE-CUSTOM-001",
                severity=VulnerabilitySeverity.HIGH,
                package="custom-pkg",
            ),
        ]
        scanner = VulnerabilityScanner(blob_store=store, cve_database=custom_db)
        assert scanner.cve_count == 1


# ============================================================
# FizzRegistryMiddleware Tests
# ============================================================


class TestFizzRegistryMiddleware:
    """Validate registry middleware integration."""

    def _make_middleware(self):
        store = BlobStore()
        api = RegistryAPI(blob_store=store)
        builder = ImageBuilder(blob_store=store, registry_api=api)
        gc = GarbageCollector(blob_store=store, registry_api=api)
        signer = ImageSigner(blob_store=store)
        scanner = VulnerabilityScanner(blob_store=store)
        mw = FizzRegistryMiddleware(
            registry_api=api,
            blob_store=store,
            image_builder=builder,
            garbage_collector=gc,
            image_signer=signer,
            vulnerability_scanner=scanner,
        )
        return mw

    def test_get_name(self):
        mw = self._make_middleware()
        assert mw.get_name() == "FizzRegistryMiddleware"

    def test_name_property(self):
        mw = self._make_middleware()
        assert mw.name == "FizzRegistryMiddleware"

    def test_get_priority(self):
        mw = self._make_middleware()
        assert mw.get_priority() == MIDDLEWARE_PRIORITY

    def test_priority_property(self):
        mw = self._make_middleware()
        assert mw.priority == MIDDLEWARE_PRIORITY

    def test_process(self):
        mw = self._make_middleware()
        ctx = ProcessingContext(number=42, session_id="test-session")

        def next_handler(c):
            return c

        result = mw.process(ctx, next_handler)
        assert result.metadata.get("registry_enabled") is True
        assert mw.evaluations == 1

    def test_process_increments_counter(self):
        mw = self._make_middleware()

        def next_handler(c):
            return c

        for i in range(5):
            ctx = ProcessingContext(number=i, session_id="test-session")
            mw.process(ctx, next_handler)
        assert mw.evaluations == 5

    def test_process_error_handling(self):
        mw = self._make_middleware()

        def failing_handler(c):
            raise RuntimeError("test error")

        ctx = ProcessingContext(number=1, session_id="test-session")
        with pytest.raises(RegistryMiddlewareError):
            mw.process(ctx, failing_handler)
        assert mw.error_count == 1

    def test_render_catalog(self):
        mw = self._make_middleware()
        output = mw.render_catalog()
        assert "Catalog" in output

    def test_render_stats(self):
        mw = self._make_middleware()
        output = mw.render_stats()
        assert "Statistics" in output

    def test_render_gc_report(self):
        mw = self._make_middleware()
        output = mw.render_gc_report()
        assert "Garbage Collection" in output

    def test_render_scan_summary(self):
        mw = self._make_middleware()
        output = mw.render_scan_summary()
        assert "Vulnerability" in output

    def test_render_build_stats(self):
        mw = self._make_middleware()
        output = mw.render_build_stats()
        assert "Builder" in output


# ============================================================
# RegistryDashboard Tests
# ============================================================


class TestRegistryDashboard:
    """Validate ASCII dashboard rendering."""

    def _make_dashboard(self):
        store = BlobStore()
        api = RegistryAPI(blob_store=store)
        builder = ImageBuilder(blob_store=store, registry_api=api)
        gc = GarbageCollector(blob_store=store, registry_api=api)
        signer = ImageSigner(blob_store=store)
        scanner = VulnerabilityScanner(blob_store=store)
        dashboard = RegistryDashboard(
            registry_api=api,
            blob_store=store,
            image_builder=builder,
            garbage_collector=gc,
            image_signer=signer,
            vulnerability_scanner=scanner,
        )
        return dashboard, api, store

    def test_render_catalog_empty(self):
        dash, api, store = self._make_dashboard()
        output = dash.render_catalog()
        assert "no repositories" in output

    def test_render_catalog_with_repos(self):
        dash, api, store = self._make_dashboard()
        api.put_blob("my-repo", b"data")
        output = dash.render_catalog()
        assert "my-repo" in output

    def test_render_stats(self):
        dash, api, store = self._make_dashboard()
        output = dash.render_stats()
        assert "Repositories" in output
        assert "Blobs" in output

    def test_render_gc_report(self):
        dash, api, store = self._make_dashboard()
        output = dash.render_gc_report()
        assert "GC Runs" in output

    def test_render_scan_summary(self):
        dash, api, store = self._make_dashboard()
        output = dash.render_scan_summary()
        assert "CVEs in DB" in output

    def test_render_build_stats(self):
        dash, api, store = self._make_dashboard()
        output = dash.render_build_stats()
        assert "Builds" in output
        assert "Cache" in output


# ============================================================
# Factory Function Tests
# ============================================================


class TestFactory:
    """Validate factory function."""

    def test_create_returns_tuple(self):
        api, mw = create_fizzregistry_subsystem()
        assert isinstance(api, RegistryAPI)
        assert isinstance(mw, FizzRegistryMiddleware)

    def test_create_with_custom_params(self):
        api, mw = create_fizzregistry_subsystem(
            max_blobs=100,
            max_repos=10,
            max_tags=50,
            gc_grace_period=3600.0,
            dashboard_width=80,
        )
        assert isinstance(api, RegistryAPI)

    def test_create_with_event_bus(self):
        bus = MagicMock()
        api, mw = create_fizzregistry_subsystem(event_bus=bus)
        assert isinstance(mw, FizzRegistryMiddleware)

    def test_factory_middleware_priority(self):
        _, mw = create_fizzregistry_subsystem()
        assert mw.priority == 110

    def test_factory_middleware_name(self):
        _, mw = create_fizzregistry_subsystem()
        assert mw.name == "FizzRegistryMiddleware"


# ============================================================
# Exception Tests
# ============================================================


class TestExceptions:
    """Validate all 20 registry exception classes."""

    def test_registry_error(self):
        e = RegistryError("test")
        assert e.error_code == "EFP-REG00"
        assert e.context["reason"] == "test"

    def test_blob_not_found_error(self):
        e = BlobNotFoundError("sha256:abc")
        assert e.error_code == "EFP-REG01"
        assert e.context["digest"] == "sha256:abc"

    def test_blob_corruption_error(self):
        e = BlobCorruptionError("sha256:abc", "bad data")
        assert e.error_code == "EFP-REG02"
        assert e.context["digest"] == "sha256:abc"

    def test_blob_store_full_error(self):
        e = BlobStoreFullError(100, "at capacity")
        assert e.error_code == "EFP-REG03"
        assert e.context["max_blobs"] == 100

    def test_manifest_not_found_error(self):
        e = ManifestNotFoundError("repo:tag")
        assert e.error_code == "EFP-REG04"
        assert e.context["reference"] == "repo:tag"

    def test_manifest_validation_error(self):
        e = ManifestValidationError("missing blob")
        assert e.error_code == "EFP-DPL11"

    def test_manifest_exists_error(self):
        e = ManifestExistsError("repo:tag")
        assert e.error_code == "EFP-REG06"

    def test_repository_not_found_error(self):
        e = RepositoryNotFoundError("my-repo")
        assert e.error_code == "EFP-REG07"

    def test_repository_limit_error(self):
        e = RepositoryLimitError(256, "too many")
        assert e.error_code == "EFP-REG08"

    def test_tag_not_found_error(self):
        e = TagNotFoundError("repo", "v1")
        assert e.error_code == "EFP-REG09"
        assert e.context["tag"] == "v1"

    def test_tag_limit_error(self):
        e = TagLimitError("repo", 100, "too many")
        assert e.error_code == "EFP-REG10"

    def test_fizzfile_parse_error(self):
        e = FizzFileParseError(5, "syntax error")
        assert e.error_code == "EFP-REG11"
        assert e.context["line_number"] == 5

    def test_fizzfile_missing_from_error(self):
        e = FizzFileMissingFromError("no FROM")
        assert e.error_code == "EFP-REG12"

    def test_image_build_error(self):
        e = ImageBuildError("failed")
        assert e.error_code == "EFP-IMG04"

    def test_layer_cache_miss_error(self):
        e = LayerCacheMissError("key123", "not found")
        assert e.error_code == "EFP-REG14"

    def test_garbage_collection_error(self):
        e = GarbageCollectionError("sweep failed")
        assert e.error_code == "EFP-ADM25"

    def test_image_signature_error(self):
        e = ImageSignatureError("sha256:abc", "key error")
        assert e.error_code == "EFP-REG16"

    def test_vulnerability_scan_error(self):
        e = VulnerabilityScanError("img:v1", "timeout")
        assert e.error_code == "EFP-REG17"

    def test_registry_dashboard_error(self):
        e = RegistryDashboardError("render failed")
        assert e.error_code == "EFP-REG18"

    def test_registry_middleware_error(self):
        e = RegistryMiddlewareError(42, "init failed")
        assert e.error_code == "EFP-REG19"
        assert e.evaluation_number == 42


# ============================================================
# EventType Tests
# ============================================================


class TestEventTypes:
    """Validate registry EventType members."""

    def test_reg_blob_pushed(self):
        assert EventType.REG_BLOB_PUSHED.name == "REG_BLOB_PUSHED"

    def test_reg_blob_pulled(self):
        assert EventType.REG_BLOB_PULLED.name == "REG_BLOB_PULLED"

    def test_reg_blob_deleted(self):
        assert EventType.REG_BLOB_DELETED.name == "REG_BLOB_DELETED"

    def test_reg_manifest_pushed(self):
        assert EventType.REG_MANIFEST_PUSHED.name == "REG_MANIFEST_PUSHED"

    def test_reg_manifest_pulled(self):
        assert EventType.REG_MANIFEST_PULLED.name == "REG_MANIFEST_PULLED"

    def test_reg_manifest_deleted(self):
        assert EventType.REG_MANIFEST_DELETED.name == "REG_MANIFEST_DELETED"

    def test_reg_tag_created(self):
        assert EventType.REG_TAG_CREATED.name == "REG_TAG_CREATED"

    def test_reg_tag_deleted(self):
        assert EventType.REG_TAG_DELETED.name == "REG_TAG_DELETED"

    def test_reg_image_built(self):
        assert EventType.REG_IMAGE_BUILT.name == "REG_IMAGE_BUILT"

    def test_reg_layer_cached(self):
        assert EventType.REG_LAYER_CACHED.name == "REG_LAYER_CACHED"

    def test_reg_gc_completed(self):
        assert EventType.REG_GC_COMPLETED.name == "REG_GC_COMPLETED"

    def test_reg_image_signed(self):
        assert EventType.REG_IMAGE_SIGNED.name == "REG_IMAGE_SIGNED"

    def test_reg_image_verified(self):
        assert EventType.REG_IMAGE_VERIFIED.name == "REG_IMAGE_VERIFIED"

    def test_reg_vuln_scanned(self):
        assert EventType.REG_VULN_SCANNED.name == "REG_VULN_SCANNED"

    def test_reg_repo_created(self):
        assert EventType.REG_REPO_CREATED.name == "REG_REPO_CREATED"

    def test_reg_dashboard_rendered(self):
        assert EventType.REG_DASHBOARD_RENDERED.name == "REG_DASHBOARD_RENDERED"


# ============================================================
# Integration Tests
# ============================================================


class TestIntegration:
    """End-to-end integration tests."""

    def test_full_push_pull_cycle(self):
        """Push blobs and manifest, then pull and verify."""
        store = BlobStore()
        api = RegistryAPI(blob_store=store)

        # Push blobs
        config_data = b'{"architecture":"fizz-arch","os":"fizzbuzz-os"}'
        config_digest = api.put_blob("fizzbuzz", config_data, OCI_CONFIG_MEDIA_TYPE)

        layer1_data = b"FIZZ 3 Fizz"
        layer1_digest = api.put_blob("fizzbuzz", layer1_data)

        layer2_data = b"BUZZ 5 Buzz"
        layer2_digest = api.put_blob("fizzbuzz", layer2_data)

        # Push manifest
        manifest = OCIManifest(
            config=OCIDescriptor(
                media_type=OCI_CONFIG_MEDIA_TYPE,
                digest=config_digest,
                size=len(config_data),
            ),
            layers=[
                OCIDescriptor(media_type=OCI_LAYER_MEDIA_TYPE, digest=layer1_digest, size=len(layer1_data)),
                OCIDescriptor(media_type=OCI_LAYER_MEDIA_TYPE, digest=layer2_digest, size=len(layer2_data)),
            ],
        )
        api.put_manifest("fizzbuzz", "latest", manifest)

        # Pull manifest
        pulled = api.get_manifest("fizzbuzz", "latest")
        assert len(pulled.layers) == 2

        # Pull blobs
        assert api.get_blob("fizzbuzz", layer1_digest) == layer1_data
        assert api.get_blob("fizzbuzz", layer2_digest) == layer2_data

    def test_build_sign_scan_cycle(self):
        """Build image, sign it, scan it."""
        store = BlobStore()
        api = RegistryAPI(blob_store=store)
        builder = ImageBuilder(blob_store=store, registry_api=api)
        signer = ImageSigner(blob_store=store)
        scanner = VulnerabilityScanner(blob_store=store)

        # Build
        fizzfile = "FROM scratch\nFIZZ 3 Fizz\nBUZZ 5 Buzz"
        digest = builder.build(fizzfile, "enterprise-fizzbuzz", "v1.0")

        # Sign
        sig = signer.sign(digest)
        assert sig.status == SignatureStatus.SIGNED

        # Verify
        verified = signer.verify(digest)
        assert verified.status == SignatureStatus.VERIFIED

        # Scan
        manifest = api.get_manifest("enterprise-fizzbuzz", "v1.0")
        report = scanner.scan("enterprise-fizzbuzz:v1.0", manifest)
        assert report.layers_scanned > 0

    def test_gc_after_delete(self):
        """Push, delete, then GC should reclaim unreferenced blobs."""
        store = BlobStore()
        api = RegistryAPI(blob_store=store)
        gc = GarbageCollector(blob_store=store, registry_api=api, grace_period=0.0)

        config_data = b"config"
        config_digest = api.put_blob("repo", config_data, OCI_CONFIG_MEDIA_TYPE)
        manifest = OCIManifest(
            config=OCIDescriptor(media_type=OCI_CONFIG_MEDIA_TYPE, digest=config_digest, size=len(config_data)),
        )
        api.put_manifest("repo", "v1", manifest)

        # Add orphan blob
        orphan_digest = store.put(b"orphan data")

        # GC should sweep the orphan but keep the config
        report = gc.collect()
        assert report.blobs_swept >= 1

    def test_middleware_pipeline_integration(self):
        """Test middleware processes evaluations correctly."""
        api, mw = create_fizzregistry_subsystem()

        results = []
        for i in range(1, 6):
            ctx = ProcessingContext(number=i, session_id="test-session")
            result = mw.process(ctx, lambda c: c)
            results.append(result)

        assert len(results) == 5
        assert mw.evaluations == 5
        assert all(r.metadata.get("registry_enabled") for r in results)

    def test_multi_repo_catalog(self):
        """Create multiple repositories and verify catalog."""
        store = BlobStore()
        api = RegistryAPI(blob_store=store)

        for name in ["alpha", "beta", "gamma", "delta"]:
            api.put_blob(name, f"data-{name}".encode())

        catalog = api.catalog()
        assert len(catalog) == 4
        assert catalog == ["alpha", "beta", "delta", "gamma"]  # sorted

    def test_tag_update_history(self):
        """Update a tag and verify history is maintained."""
        store = BlobStore()
        api = RegistryAPI(blob_store=store)

        config1 = api.put_blob("repo", b"cfg1", OCI_CONFIG_MEDIA_TYPE)
        config2 = api.put_blob("repo", b"cfg2", OCI_CONFIG_MEDIA_TYPE)

        m1 = OCIManifest(config=OCIDescriptor(media_type=OCI_CONFIG_MEDIA_TYPE, digest=config1, size=4))
        m2 = OCIManifest(config=OCIDescriptor(media_type=OCI_CONFIG_MEDIA_TYPE, digest=config2, size=4))

        api.put_manifest("repo", "latest", m1)
        api.put_manifest("repo", "latest", m2)

        repo = api.get_repo("repo")
        history = repo.tag_history("latest")
        assert len(history) == 2

    def test_build_base_image_chain(self):
        """Build a base image then build on top of it."""
        store = BlobStore()
        api = RegistryAPI(blob_store=store)
        builder = ImageBuilder(blob_store=store, registry_api=api)

        # Build base image
        base_fizzfile = "FROM scratch\nFIZZ 3 Fizz"
        builder.build(base_fizzfile, "base", "latest")

        # Build derived image
        derived_fizzfile = "FROM base:latest\nBUZZ 5 Buzz"
        digest = builder.build(derived_fizzfile, "derived", "latest")
        assert digest.startswith(DIGEST_PREFIX)

        # Derived should have more layers than base
        base_manifest = api.get_manifest("base", "latest")
        derived_manifest = api.get_manifest("derived", "latest")
        assert len(derived_manifest.layers) > len(base_manifest.layers)
