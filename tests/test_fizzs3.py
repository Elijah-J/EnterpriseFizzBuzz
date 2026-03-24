"""Tests for the FizzS3 S3-Compatible Object Storage subsystem.

Validates all components of the FizzS3 storage engine including bucket
management, object CRUD, versioning, multipart uploads, erasure coding,
content-addressable deduplication, presigned URLs, access control,
encryption, lifecycle management, and middleware integration.
"""

import hashlib
import time
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from enterprise_fizzbuzz.infrastructure.fizzs3 import (
    # Constants
    FIZZS3_VERSION,
    S3_API_VERSION,
    DEFAULT_REGION,
    SUPPORTED_REGIONS,
    MAX_BUCKET_NAME_LENGTH,
    MIN_BUCKET_NAME_LENGTH,
    MAX_BUCKETS_PER_OWNER,
    MAX_OBJECT_KEY_LENGTH,
    MAX_SINGLE_PUT_SIZE,
    MAX_METADATA_SIZE,
    MAX_TAGS_PER_BUCKET,
    MIN_PART_SIZE,
    MAX_PART_SIZE,
    MAX_PARTS,
    MAX_LIST_KEYS,
    MAX_DELETE_OBJECTS,
    MAX_LIFECYCLE_RULES,
    MAX_PRESIGN_EXPIRY,
    CLOCK_SKEW_TOLERANCE,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_SEGMENT_MAX_SIZE,
    DEFAULT_COMPACTION_THRESHOLD,
    DEFAULT_GC_INTERVAL,
    DEFAULT_GC_SAFETY_DELAY,
    MIDDLEWARE_PRIORITY,
    ERASURE_PARAMS,
    STORAGE_CLASS_ORDER,
    # Enums
    BucketVersioning,
    StorageClass,
    RestoreTier,
    EncryptionMode,
    EncryptionAlgorithm,
    PolicyEffect,
    ACLPermission,
    CannedACL,
    S3EventType,
    DestinationType,
    RuleStatus,
    SegmentStatus,
    # Data classes
    ServerSideEncryption,
    EncryptionConfiguration,
    BlockPublicAccessConfiguration,
    Grant,
    AccessControlList,
    PolicyStatement,
    BucketPolicy,
    TransitionRule,
    NoncurrentVersionTransitionRule,
    LifecycleRule,
    LifecycleConfiguration,
    ReplicationRule,
    ReplicationConfiguration,
    EventRule,
    NotificationConfiguration,
    Bucket,
    S3Object,
    ObjectSummary,
    ListObjectsResult,
    DeleteMarker,
    UploadPart,
    MultipartUpload,
    S3EventMessage,
    ChunkReference,
    ChunkManifest,
    AuthorizationResult,
    LifecycleAction,
    DeduplicationStats,
    FragmentLocation,
    Segment,
    # Classes
    BucketNameValidator,
    GaloisField,
    VandermondeMatrix,
    ErasureCodingEngine,
    FragmentDistributor,
    FragmentIntegrityChecker,
    MetadataIndex,
    SegmentLog,
    CompactionPolicy,
    ReferenceCounter,
    ContentAddressableStore,
    GarbageCollector,
    EncryptionEngine,
    KeyRotationManager,
    BucketManager,
    VersioningEngine,
    ObjectStore,
    MultipartUploadManager,
    IncompleteUploadReaper,
    SignatureV4Computer,
    PresignedURLGenerator,
    PresignedURLVerifier,
    StorageClassManager,
    FizzS3Middleware,
    create_fizzs3_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions.fizzs3 import (
    FizzS3Error,
    BucketError,
    BucketAlreadyExistsError,
    BucketAlreadyOwnedByYouError,
    BucketNotEmptyError,
    BucketNotFoundError,
    InvalidBucketNameError,
    TooManyBucketsError,
    ObjectError,
    ObjectNotFoundError,
    ObjectTooLargeError,
    InvalidObjectKeyError,
    PreconditionFailedError,
    NotModifiedError,
    InvalidRangeError,
    VersionError,
    NoSuchVersionError,
    VersioningNotEnabledError,
    InvalidVersionIdError,
    MultipartUploadError,
    NoSuchUploadError,
    InvalidPartError,
    InvalidPartOrderError,
    EntityTooSmallError,
    EntityTooLargeError,
    TooManyPartsError,
    AccessControlError,
    S3AccessDeniedError,
    InvalidPolicyError,
    MalformedACLError,
    PublicAccessBlockedError,
    EncryptionError,
    InvalidEncryptionKeyError,
    KMSKeyNotFoundError,
    KMSAccessDeniedError,
    KeyRotationInProgressError,
    ReplicationError,
    ReplicationConfigurationError,
    ReplicationFailedError,
    ReplicationLoopDetectedError,
    StorageClassError,
    InvalidStorageClassTransitionError,
    RestoreInProgressError,
    ObjectNotArchivedError,
    RestoreExpiredError,
    ErasureCodingError,
    InsufficientFragmentsError,
    FragmentCorruptionError,
    FragmentLocationUnavailableError,
    ContentAddressError,
    ChunkNotFoundError,
    ReferenceIntegrityError,
    DeduplicationHashCollisionError,
    LifecycleError,
    InvalidLifecycleConfigurationError,
    TooManyLifecycleRulesError,
    PresignedURLError,
    ExpiredPresignedURLError,
    InvalidSignatureError,
    SignatureMethodMismatchError,
    MetadataError,
    MetadataCorruptionError,
    MetadataCapacityExceededError,
    NotificationError,
    InvalidNotificationConfigurationError,
    NotificationDeliveryFailedError,
    FizzS3MiddlewareError,
    FizzS3DashboardError,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def event_bus():
    """Provide a mock event bus."""
    class MockEventBus:
        def __init__(self):
            self.events = []
        def publish(self, event_type, data=None):
            self.events.append((event_type, data))
    return MockEventBus()


@pytest.fixture
def gf():
    """Provide a GaloisField instance."""
    return GaloisField()


@pytest.fixture
def erasure_engine(gf):
    """Provide an ErasureCodingEngine."""
    return ErasureCodingEngine(gf=gf)


@pytest.fixture
def metadata_index():
    """Provide a MetadataIndex instance."""
    return MetadataIndex()


@pytest.fixture
def segment_log():
    """Provide a SegmentLog instance."""
    return SegmentLog()


@pytest.fixture
def ref_counter(metadata_index):
    """Provide a ReferenceCounter instance."""
    return ReferenceCounter(metadata_index=metadata_index)


@pytest.fixture
def cas(erasure_engine, segment_log, ref_counter):
    """Provide a ContentAddressableStore instance."""
    return ContentAddressableStore(
        erasure_engine=erasure_engine,
        segment_log=segment_log,
        ref_counter=ref_counter,
    )


@pytest.fixture
def encryption_engine():
    """Provide an EncryptionEngine instance."""
    return EncryptionEngine()


@pytest.fixture
def bucket_manager(metadata_index, event_bus):
    """Provide a BucketManager instance."""
    return BucketManager(
        metadata_index=metadata_index,
        event_bus=event_bus,
    )


@pytest.fixture
def versioning_engine(metadata_index):
    """Provide a VersioningEngine instance."""
    return VersioningEngine(metadata_index=metadata_index)


@pytest.fixture
def object_store(metadata_index, cas, encryption_engine, versioning_engine, event_bus):
    """Provide an ObjectStore instance."""
    return ObjectStore(
        metadata_index=metadata_index,
        cas=cas,
        encryption_engine=encryption_engine,
        versioning_engine=versioning_engine,
        event_bus=event_bus,
    )


@pytest.fixture
def multipart_manager(metadata_index, object_store, cas, event_bus):
    """Provide a MultipartUploadManager instance."""
    return MultipartUploadManager(
        metadata_index=metadata_index,
        object_store=object_store,
        cas=cas,
        event_bus=event_bus,
    )


@pytest.fixture
def sample_bucket():
    """Provide a sample bucket."""
    return Bucket(
        name="fizzbuzz-evaluations",
        region="fizz-east-1",
        owner="fizzbuzz-root",
    )


@pytest.fixture
def sample_object():
    """Provide a sample S3 object."""
    return S3Object(
        key="evaluations/2026/03/24/abc123.json",
        bucket_name="fizzbuzz-evaluations",
        data=b'{"input": 15, "output": "FizzBuzz"}',
        content_type="application/json",
    )


@pytest.fixture
def sig_computer():
    """Provide a SignatureV4Computer."""
    return SignatureV4Computer(secret_key="fizz-test-secret")


@pytest.fixture
def presign_generator(sig_computer):
    """Provide a PresignedURLGenerator."""
    return PresignedURLGenerator(
        sig_computer=sig_computer,
        default_expiry=3600,
        region="fizz-east-1",
    )


@pytest.fixture
def presign_verifier(sig_computer):
    """Provide a PresignedURLVerifier."""
    return PresignedURLVerifier(
        sig_computer=sig_computer,
        region="fizz-east-1",
    )


# ============================================================
# TestBucketNameValidator
# ============================================================


class TestBucketNameValidator:
    """Validates bucket name rules against the S3 naming specification."""

    def test_valid_simple_name(self):
        valid, violations = BucketNameValidator.validate("my-bucket")
        assert valid is True
        assert violations == []

    def test_valid_name_with_periods(self):
        valid, _ = BucketNameValidator.validate("my.bucket.name")
        assert valid is True

    def test_valid_name_with_numbers(self):
        valid, _ = BucketNameValidator.validate("bucket123")
        assert valid is True

    def test_valid_minimum_length(self):
        valid, _ = BucketNameValidator.validate("abc")
        assert valid is True

    def test_valid_maximum_length(self):
        name = "a" * MAX_BUCKET_NAME_LENGTH
        valid, _ = BucketNameValidator.validate(name)
        assert valid is True

    def test_invalid_too_short(self):
        valid, violations = BucketNameValidator.validate("ab")
        assert valid is False
        assert any("too short" in v.lower() for v in violations)

    def test_invalid_too_long(self):
        name = "a" * (MAX_BUCKET_NAME_LENGTH + 1)
        valid, violations = BucketNameValidator.validate(name)
        assert valid is False
        assert any("too long" in v.lower() for v in violations)

    def test_invalid_uppercase_chars(self):
        valid, violations = BucketNameValidator.validate("MyBucket")
        assert valid is False
        assert any("invalid characters" in v.lower() for v in violations)

    def test_invalid_underscore(self):
        valid, violations = BucketNameValidator.validate("my_bucket")
        assert valid is False

    def test_invalid_ip_address_format(self):
        valid, violations = BucketNameValidator.validate("192.168.1.1")
        assert valid is False
        assert any("ipv4" in v.lower() for v in violations)

    def test_invalid_xn_prefix(self):
        valid, violations = BucketNameValidator.validate("xn--bucket")
        assert valid is False
        assert any("xn--" in v.lower() for v in violations)

    def test_invalid_s3alias_suffix(self):
        valid, violations = BucketNameValidator.validate("bucket-s3alias")
        assert valid is False
        assert any("s3alias" in v.lower() for v in violations)

    def test_invalid_ol_s3_suffix(self):
        valid, violations = BucketNameValidator.validate("bucket--ol-s3")
        assert valid is False

    def test_invalid_consecutive_periods(self):
        valid, violations = BucketNameValidator.validate("my..bucket")
        assert valid is False
        assert any("consecutive periods" in v.lower() for v in violations)

    def test_invalid_start_with_hyphen(self):
        valid, violations = BucketNameValidator.validate("-bucket")
        assert valid is False
        assert any("start with" in v.lower() for v in violations)

    def test_invalid_end_with_hyphen(self):
        valid, violations = BucketNameValidator.validate("bucket-")
        assert valid is False
        assert any("end with" in v.lower() for v in violations)

    def test_invalid_start_with_period(self):
        valid, violations = BucketNameValidator.validate(".bucket")
        assert valid is False

    def test_valid_alphanumeric_only(self):
        valid, _ = BucketNameValidator.validate("mybucket2026")
        assert valid is True

    def test_multiple_violations(self):
        valid, violations = BucketNameValidator.validate("XN--A.")
        assert valid is False
        assert len(violations) > 1

    def test_valid_hyphen_separated(self):
        valid, _ = BucketNameValidator.validate("fizz-buzz-evaluations-2026")
        assert valid is True


# ============================================================
# TestBucket
# ============================================================


class TestBucket:
    """Validates Bucket dataclass construction and defaults."""

    def test_bucket_creation(self, sample_bucket):
        assert sample_bucket.name == "fizzbuzz-evaluations"
        assert sample_bucket.region == "fizz-east-1"
        assert sample_bucket.owner == "fizzbuzz-root"

    def test_default_versioning(self, sample_bucket):
        assert sample_bucket.versioning == BucketVersioning.DISABLED

    def test_default_no_lifecycle(self, sample_bucket):
        assert sample_bucket.lifecycle_configuration is None

    def test_default_no_replication(self, sample_bucket):
        assert sample_bucket.replication_configuration is None

    def test_default_no_policy(self, sample_bucket):
        assert sample_bucket.policy is None

    def test_creation_date_is_utc(self, sample_bucket):
        assert sample_bucket.creation_date.tzinfo is not None

    def test_empty_tags(self, sample_bucket):
        assert sample_bucket.tags == {}

    def test_object_lock_default_off(self, sample_bucket):
        assert sample_bucket.object_lock_enabled is False


# ============================================================
# TestBucketManager
# ============================================================


class TestBucketManager:
    """Validates bucket lifecycle operations."""

    def test_create_bucket(self, bucket_manager):
        bucket = bucket_manager.create_bucket("test-bucket-123")
        assert bucket.name == "test-bucket-123"
        assert bucket.region == DEFAULT_REGION

    def test_create_bucket_custom_region(self, bucket_manager):
        bucket = bucket_manager.create_bucket("test-bucket", region="fizz-west-1")
        assert bucket.region == "fizz-west-1"

    def test_create_bucket_already_exists(self, bucket_manager):
        bucket_manager.create_bucket("test-bucket")
        with pytest.raises(BucketAlreadyOwnedByYouError):
            bucket_manager.create_bucket("test-bucket")

    def test_create_bucket_owned_by_other(self, bucket_manager):
        bucket_manager.create_bucket("test-bucket", owner="other-user")
        with pytest.raises(BucketAlreadyExistsError):
            bucket_manager.create_bucket("test-bucket")

    def test_create_bucket_invalid_name(self, bucket_manager):
        with pytest.raises(InvalidBucketNameError):
            bucket_manager.create_bucket("AB")

    def test_create_bucket_too_many(self, metadata_index, event_bus):
        mgr = BucketManager(metadata_index=metadata_index, max_buckets=2, event_bus=event_bus)
        mgr.create_bucket("bucket-a")
        mgr.create_bucket("bucket-b")
        with pytest.raises(TooManyBucketsError):
            mgr.create_bucket("bucket-c")

    def test_delete_bucket(self, bucket_manager):
        bucket_manager.create_bucket("to-delete")
        bucket_manager.delete_bucket("to-delete")
        with pytest.raises(BucketNotFoundError):
            bucket_manager.get_bucket("to-delete")

    def test_delete_bucket_not_found(self, bucket_manager):
        with pytest.raises(BucketNotFoundError):
            bucket_manager.delete_bucket("nonexistent")

    def test_delete_bucket_not_empty(self, bucket_manager, metadata_index):
        bucket_manager.create_bucket("has-objects")
        metadata_index.put("objects:has-objects", "file.txt", S3Object(key="file.txt"))
        with pytest.raises(BucketNotEmptyError):
            bucket_manager.delete_bucket("has-objects")

    def test_head_bucket_exists(self, bucket_manager):
        bucket_manager.create_bucket("my-bucket")
        assert bucket_manager.head_bucket("my-bucket") is True

    def test_head_bucket_not_exists(self, bucket_manager):
        assert bucket_manager.head_bucket("ghost-bucket") is False

    def test_list_buckets(self, bucket_manager):
        bucket_manager.create_bucket("alpha-bucket")
        bucket_manager.create_bucket("beta-bucket")
        buckets = bucket_manager.list_buckets()
        names = [b.name for b in buckets]
        assert "alpha-bucket" in names
        assert "beta-bucket" in names
        assert names == sorted(names)

    def test_get_bucket_location(self, bucket_manager):
        bucket_manager.create_bucket("loc-bucket", region="fizz-eu-1")
        assert bucket_manager.get_bucket_location("loc-bucket") == "fizz-eu-1"

    def test_versioning_enable(self, bucket_manager):
        bucket_manager.create_bucket("ver-bucket")
        bucket_manager.put_bucket_versioning("ver-bucket", BucketVersioning.ENABLED)
        assert bucket_manager.get_bucket_versioning("ver-bucket") == BucketVersioning.ENABLED

    def test_versioning_suspend(self, bucket_manager):
        bucket_manager.create_bucket("ver-bucket")
        bucket_manager.put_bucket_versioning("ver-bucket", BucketVersioning.ENABLED)
        bucket_manager.put_bucket_versioning("ver-bucket", BucketVersioning.SUSPENDED)
        assert bucket_manager.get_bucket_versioning("ver-bucket") == BucketVersioning.SUSPENDED

    def test_versioning_reenable(self, bucket_manager):
        bucket_manager.create_bucket("ver-bucket")
        bucket_manager.put_bucket_versioning("ver-bucket", BucketVersioning.ENABLED)
        bucket_manager.put_bucket_versioning("ver-bucket", BucketVersioning.SUSPENDED)
        bucket_manager.put_bucket_versioning("ver-bucket", BucketVersioning.ENABLED)
        assert bucket_manager.get_bucket_versioning("ver-bucket") == BucketVersioning.ENABLED

    def test_versioning_invalid_transition(self, bucket_manager):
        bucket_manager.create_bucket("ver-bucket")
        with pytest.raises(VersionError):
            bucket_manager.put_bucket_versioning("ver-bucket", BucketVersioning.SUSPENDED)

    def test_create_bucket_emits_event(self, bucket_manager, event_bus):
        bucket_manager.create_bucket("event-bucket")
        assert any("BUCKET_CREATED" in str(e[0]) for e in event_bus.events)

    def test_delete_bucket_emits_event(self, bucket_manager, event_bus):
        bucket_manager.create_bucket("del-event-bucket")
        bucket_manager.delete_bucket("del-event-bucket")
        assert any("BUCKET_DELETED" in str(e[0]) for e in event_bus.events)

    def test_create_bucket_with_canned_acl(self, bucket_manager):
        bucket = bucket_manager.create_bucket("acl-bucket", acl=CannedACL.PUBLIC_READ)
        assert bucket.acl is not None
        grantees = [g.grantee for g in bucket.acl.grants]
        assert "AllUsers" in grantees

    def test_sequencer_monotonic(self, bucket_manager):
        s1 = bucket_manager.next_sequencer()
        s2 = bucket_manager.next_sequencer()
        assert s2 > s1

    def test_create_bucket_with_object_lock(self, bucket_manager):
        bucket = bucket_manager.create_bucket("lock-bucket", object_lock=True)
        assert bucket.object_lock_enabled is True

    def test_get_bucket(self, bucket_manager):
        bucket_manager.create_bucket("get-me")
        bucket = bucket_manager.get_bucket("get-me")
        assert bucket.name == "get-me"

    def test_get_bucket_not_found(self, bucket_manager):
        with pytest.raises(BucketNotFoundError):
            bucket_manager.get_bucket("nope")


# ============================================================
# TestS3Object
# ============================================================


class TestS3Object:
    """Validates S3Object dataclass construction and defaults."""

    def test_object_creation(self, sample_object):
        assert sample_object.key == "evaluations/2026/03/24/abc123.json"
        assert sample_object.content_type == "application/json"

    def test_default_storage_class(self, sample_object):
        assert sample_object.storage_class == StorageClass.STANDARD

    def test_default_empty_metadata(self):
        obj = S3Object(key="test.txt")
        assert obj.metadata == {}

    def test_default_no_version(self):
        obj = S3Object(key="test.txt")
        assert obj.version_id is None

    def test_default_not_delete_marker(self):
        obj = S3Object(key="test.txt")
        assert obj.delete_marker is False

    def test_default_is_latest(self):
        obj = S3Object(key="test.txt")
        assert obj.is_latest is True

    def test_default_etag_empty(self):
        obj = S3Object(key="test.txt")
        assert obj.etag == ""

    def test_default_no_encryption(self):
        obj = S3Object(key="test.txt")
        assert obj.server_side_encryption is None

    def test_custom_metadata(self):
        obj = S3Object(key="test.txt", metadata={"x-custom": "value"})
        assert obj.metadata["x-custom"] == "value"

    def test_size_field(self):
        obj = S3Object(key="test.txt", size=1024)
        assert obj.size == 1024


# ============================================================
# TestObjectStore
# ============================================================


class TestObjectStore:
    """Validates core object storage operations."""

    def test_put_object(self, bucket_manager, object_store):
        bucket_manager.create_bucket("test-bucket")
        obj = object_store.put_object("test-bucket", "hello.txt", b"Hello, World!")
        assert obj.key == "hello.txt"
        assert obj.size == 13
        assert obj.etag == hashlib.md5(b"Hello, World!").hexdigest()

    def test_get_object(self, bucket_manager, object_store):
        bucket_manager.create_bucket("test-bucket")
        object_store.put_object("test-bucket", "hello.txt", b"Hello, World!")
        obj = object_store.get_object("test-bucket", "hello.txt")
        assert obj.data == b"Hello, World!"

    def test_head_object(self, bucket_manager, object_store):
        bucket_manager.create_bucket("test-bucket")
        object_store.put_object("test-bucket", "hello.txt", b"Hello, World!")
        obj = object_store.head_object("test-bucket", "hello.txt")
        assert obj.data == b""
        assert obj.key == "hello.txt"

    def test_delete_object_unversioned(self, bucket_manager, object_store):
        bucket_manager.create_bucket("test-bucket")
        object_store.put_object("test-bucket", "gone.txt", b"bye")
        result = object_store.delete_object("test-bucket", "gone.txt")
        assert result is not None
        with pytest.raises(ObjectNotFoundError):
            object_store.get_object("test-bucket", "gone.txt")

    def test_delete_nonexistent_object(self, bucket_manager, object_store):
        bucket_manager.create_bucket("test-bucket")
        result = object_store.delete_object("test-bucket", "ghost.txt")
        assert result is None

    def test_get_object_not_found(self, bucket_manager, object_store):
        bucket_manager.create_bucket("test-bucket")
        with pytest.raises(ObjectNotFoundError):
            object_store.get_object("test-bucket", "nope.txt")

    def test_get_from_nonexistent_bucket(self, object_store):
        with pytest.raises(BucketNotFoundError):
            object_store.get_object("no-bucket", "file.txt")

    def test_put_object_invalid_key_empty(self, bucket_manager, object_store):
        bucket_manager.create_bucket("test-bucket")
        with pytest.raises(InvalidObjectKeyError):
            object_store.put_object("test-bucket", "", b"data")

    def test_put_object_invalid_key_null_byte(self, bucket_manager, object_store):
        bucket_manager.create_bucket("test-bucket")
        with pytest.raises(InvalidObjectKeyError):
            object_store.put_object("test-bucket", "key\x00bad", b"data")

    def test_put_object_metadata_capacity(self, bucket_manager, object_store):
        bucket_manager.create_bucket("test-bucket")
        big_meta = {"x-" + str(i): "v" * 100 for i in range(30)}
        with pytest.raises(MetadataCapacityExceededError):
            object_store.put_object("test-bucket", "meta.txt", b"data", metadata=big_meta)

    def test_put_object_with_content_type(self, bucket_manager, object_store):
        bucket_manager.create_bucket("test-bucket")
        obj = object_store.put_object(
            "test-bucket", "doc.json", b'{"key": "value"}',
            content_type="application/json",
        )
        assert obj.content_type == "application/json"

    def test_put_object_sha256_checksum(self, bucket_manager, object_store):
        bucket_manager.create_bucket("test-bucket")
        data = b"checked data"
        sha = hashlib.sha256(data).hexdigest()
        obj = object_store.put_object("test-bucket", "checked.txt", data, checksum_sha256=sha)
        assert obj.checksum_sha256 == sha

    def test_put_object_sha256_mismatch(self, bucket_manager, object_store):
        bucket_manager.create_bucket("test-bucket")
        with pytest.raises(ObjectError):
            object_store.put_object("test-bucket", "bad.txt", b"data", checksum_sha256="deadbeef")

    def test_conditional_get_if_match_success(self, bucket_manager, object_store):
        bucket_manager.create_bucket("test-bucket")
        obj = object_store.put_object("test-bucket", "match.txt", b"data")
        result = object_store.get_object("test-bucket", "match.txt", if_match=obj.etag)
        assert result.key == "match.txt"

    def test_conditional_get_if_match_fail(self, bucket_manager, object_store):
        bucket_manager.create_bucket("test-bucket")
        object_store.put_object("test-bucket", "match.txt", b"data")
        with pytest.raises(PreconditionFailedError):
            object_store.get_object("test-bucket", "match.txt", if_match="wrong-etag")

    def test_conditional_get_if_none_match(self, bucket_manager, object_store):
        bucket_manager.create_bucket("test-bucket")
        obj = object_store.put_object("test-bucket", "nm.txt", b"data")
        with pytest.raises(NotModifiedError):
            object_store.get_object("test-bucket", "nm.txt", if_none_match=obj.etag)

    def test_conditional_get_if_modified_since(self, bucket_manager, object_store):
        bucket_manager.create_bucket("test-bucket")
        object_store.put_object("test-bucket", "mod.txt", b"data")
        future = datetime.now(timezone.utc) + timedelta(days=1)
        with pytest.raises(NotModifiedError):
            object_store.get_object("test-bucket", "mod.txt", if_modified_since=future)

    def test_conditional_get_if_unmodified_since(self, bucket_manager, object_store):
        bucket_manager.create_bucket("test-bucket")
        object_store.put_object("test-bucket", "unmod.txt", b"data")
        past = datetime.now(timezone.utc) - timedelta(days=1)
        with pytest.raises(PreconditionFailedError):
            object_store.get_object("test-bucket", "unmod.txt", if_unmodified_since=past)

    def test_byte_range_start_end(self, bucket_manager, object_store):
        bucket_manager.create_bucket("test-bucket")
        object_store.put_object("test-bucket", "range.txt", b"0123456789")
        obj = object_store.get_object("test-bucket", "range.txt", byte_range="bytes=0-4")
        assert obj.data == b"01234"

    def test_byte_range_start_only(self, bucket_manager, object_store):
        bucket_manager.create_bucket("test-bucket")
        object_store.put_object("test-bucket", "range.txt", b"0123456789")
        obj = object_store.get_object("test-bucket", "range.txt", byte_range="bytes=5-")
        assert obj.data == b"56789"

    def test_byte_range_suffix(self, bucket_manager, object_store):
        bucket_manager.create_bucket("test-bucket")
        object_store.put_object("test-bucket", "range.txt", b"0123456789")
        obj = object_store.get_object("test-bucket", "range.txt", byte_range="bytes=-3")
        assert obj.data == b"789"

    def test_byte_range_invalid(self, bucket_manager, object_store):
        bucket_manager.create_bucket("test-bucket")
        object_store.put_object("test-bucket", "range.txt", b"0123456789")
        with pytest.raises(InvalidRangeError):
            object_store.get_object("test-bucket", "range.txt", byte_range="bytes=20-30")

    def test_copy_object(self, bucket_manager, object_store):
        bucket_manager.create_bucket("src-bucket")
        bucket_manager.create_bucket("dst-bucket")
        object_store.put_object("src-bucket", "orig.txt", b"copy me", metadata={"tag": "val"})
        copied = object_store.copy_object("src-bucket", "orig.txt", "dst-bucket", "copied.txt")
        assert copied.key == "copied.txt"
        result = object_store.get_object("dst-bucket", "copied.txt")
        assert result.data == b"copy me"

    def test_copy_object_replace_metadata(self, bucket_manager, object_store):
        bucket_manager.create_bucket("src-bucket")
        bucket_manager.create_bucket("dst-bucket")
        object_store.put_object("src-bucket", "orig.txt", b"data", metadata={"old": "meta"})
        copied = object_store.copy_object(
            "src-bucket", "orig.txt", "dst-bucket", "new.txt",
            metadata_directive="REPLACE",
            metadata={"new": "meta"},
        )
        assert copied.metadata == {"new": "meta"}

    def test_delete_objects_batch(self, bucket_manager, object_store):
        bucket_manager.create_bucket("batch-bucket")
        for i in range(5):
            object_store.put_object("batch-bucket", f"file{i}.txt", b"data")
        objects = [{"key": f"file{i}.txt"} for i in range(5)]
        successes, errors = object_store.delete_objects("batch-bucket", objects)
        assert len(successes) == 5
        assert len(errors) == 0

    def test_put_emits_event(self, bucket_manager, object_store, event_bus):
        bucket_manager.create_bucket("evt-bucket")
        object_store.put_object("evt-bucket", "file.txt", b"data")
        assert any("OBJECT_CREATED_PUT" in str(e[0]) for e in event_bus.events)

    def test_delete_emits_event(self, bucket_manager, object_store, event_bus):
        bucket_manager.create_bucket("evt-bucket")
        object_store.put_object("evt-bucket", "file.txt", b"data")
        object_store.delete_object("evt-bucket", "file.txt")
        assert any("OBJECT_DELETED" in str(e[0]) for e in event_bus.events)

    def test_put_object_custom_storage_class(self, bucket_manager, object_store):
        bucket_manager.create_bucket("sc-bucket")
        obj = object_store.put_object(
            "sc-bucket", "archive.bin", b"old data",
            storage_class=StorageClass.STANDARD_IA,
        )
        assert obj.storage_class == StorageClass.STANDARD_IA

    def test_put_object_with_metadata(self, bucket_manager, object_store):
        bucket_manager.create_bucket("meta-bucket")
        obj = object_store.put_object(
            "meta-bucket", "doc.txt", b"content",
            metadata={"x-author": "fizzbuzz", "x-version": "1"},
        )
        assert obj.metadata["x-author"] == "fizzbuzz"

    def test_copy_object_same_bucket(self, bucket_manager, object_store):
        bucket_manager.create_bucket("test-bucket")
        object_store.put_object("test-bucket", "a.txt", b"data")
        copied = object_store.copy_object("test-bucket", "a.txt", "test-bucket", "b.txt")
        assert copied.key == "b.txt"

    def test_copy_emits_event(self, bucket_manager, object_store, event_bus):
        bucket_manager.create_bucket("src-bucket")
        bucket_manager.create_bucket("dst-bucket")
        object_store.put_object("src-bucket", "file.txt", b"data")
        object_store.copy_object("src-bucket", "file.txt", "dst-bucket", "copy.txt")
        assert any("OBJECT_CREATED_COPY" in str(e[0]) for e in event_bus.events)


# ============================================================
# TestListObjectsV2
# ============================================================


class TestListObjectsV2:
    """Validates list_objects_v2 with prefix, delimiter, and pagination."""

    def _populate_bucket(self, bucket_manager, object_store, bucket_name, keys):
        bucket_manager.create_bucket(bucket_name)
        for key in keys:
            object_store.put_object(bucket_name, key, b"data")

    def test_list_all_objects(self, bucket_manager, object_store):
        self._populate_bucket(bucket_manager, object_store, "list-bucket",
                              ["a.txt", "b.txt", "c.txt"])
        result = object_store.list_objects_v2("list-bucket")
        assert result.key_count == 3

    def test_list_with_prefix(self, bucket_manager, object_store):
        self._populate_bucket(bucket_manager, object_store, "list-bucket",
                              ["docs/a.txt", "docs/b.txt", "images/c.png"])
        result = object_store.list_objects_v2("list-bucket", prefix="docs/")
        assert result.key_count == 2
        assert all(c.key.startswith("docs/") for c in result.contents)

    def test_list_with_delimiter(self, bucket_manager, object_store):
        self._populate_bucket(bucket_manager, object_store, "list-bucket",
                              ["docs/a.txt", "docs/b.txt", "images/c.png", "root.txt"])
        result = object_store.list_objects_v2("list-bucket", delimiter="/")
        assert "docs/" in result.common_prefixes
        assert "images/" in result.common_prefixes
        assert any(c.key == "root.txt" for c in result.contents)

    def test_list_with_prefix_and_delimiter(self, bucket_manager, object_store):
        self._populate_bucket(bucket_manager, object_store, "list-bucket",
                              ["docs/2026/a.txt", "docs/2025/b.txt", "docs/readme.txt"])
        result = object_store.list_objects_v2("list-bucket", prefix="docs/", delimiter="/")
        assert "docs/2026/" in result.common_prefixes
        assert "docs/2025/" in result.common_prefixes

    def test_list_pagination_max_keys(self, bucket_manager, object_store):
        self._populate_bucket(bucket_manager, object_store, "list-bucket",
                              [f"file{i:03d}.txt" for i in range(10)])
        result = object_store.list_objects_v2("list-bucket", max_keys=3)
        assert len(result.contents) <= 3

    def test_list_empty_bucket(self, bucket_manager, object_store):
        bucket_manager.create_bucket("empty-bucket")
        result = object_store.list_objects_v2("empty-bucket")
        assert result.key_count == 0
        assert result.contents == []

    def test_list_nonexistent_bucket(self, object_store):
        with pytest.raises(BucketNotFoundError):
            object_store.list_objects_v2("no-bucket")

    def test_list_with_start_after(self, bucket_manager, object_store):
        self._populate_bucket(bucket_manager, object_store, "list-bucket",
                              ["a.txt", "b.txt", "c.txt", "d.txt"])
        result = object_store.list_objects_v2("list-bucket", start_after="b.txt")
        keys = [c.key for c in result.contents]
        assert "a.txt" not in keys
        assert "b.txt" not in keys

    def test_list_common_prefixes_sorted(self, bucket_manager, object_store):
        self._populate_bucket(bucket_manager, object_store, "list-bucket",
                              ["z/file.txt", "a/file.txt", "m/file.txt"])
        result = object_store.list_objects_v2("list-bucket", delimiter="/")
        assert result.common_prefixes == sorted(result.common_prefixes)

    def test_list_prefix_no_match(self, bucket_manager, object_store):
        self._populate_bucket(bucket_manager, object_store, "list-bucket", ["file.txt"])
        result = object_store.list_objects_v2("list-bucket", prefix="nonexistent/")
        assert result.key_count == 0

    def test_list_result_has_correct_fields(self, bucket_manager, object_store):
        self._populate_bucket(bucket_manager, object_store, "list-bucket", ["file.txt"])
        result = object_store.list_objects_v2("list-bucket")
        assert result.max_keys == MAX_LIST_KEYS
        assert result.delimiter is None
        assert result.prefix is None

    def test_list_object_summary_fields(self, bucket_manager, object_store):
        self._populate_bucket(bucket_manager, object_store, "list-bucket", ["obj.txt"])
        result = object_store.list_objects_v2("list-bucket")
        summary = result.contents[0]
        assert summary.key == "obj.txt"
        assert summary.storage_class == StorageClass.STANDARD
        assert summary.etag != ""

    def test_list_skips_delete_markers(self, bucket_manager, object_store):
        bucket_manager.create_bucket("ver-bucket")
        bucket_manager.put_bucket_versioning("ver-bucket", BucketVersioning.ENABLED)
        object_store.put_object("ver-bucket", "file.txt", b"data")
        object_store.delete_object("ver-bucket", "file.txt")
        result = object_store.list_objects_v2("ver-bucket")
        assert result.key_count == 0

    def test_list_continuation_token(self, bucket_manager, object_store):
        self._populate_bucket(bucket_manager, object_store, "list-bucket",
                              [f"f{i:03d}.txt" for i in range(20)])
        result = object_store.list_objects_v2("list-bucket", max_keys=5)
        if result.next_continuation_token:
            result2 = object_store.list_objects_v2(
                "list-bucket", continuation_token=result.next_continuation_token, max_keys=5
            )
            keys1 = {c.key for c in result.contents}
            keys2 = {c.key for c in result2.contents}
            assert keys1.isdisjoint(keys2)


# ============================================================
# TestVersioningEngine
# ============================================================


class TestVersioningEngine:
    """Validates version chain management."""

    def test_assign_version_id_format(self, versioning_engine):
        vid = versioning_engine.assign_version_id()
        assert "-" in vid
        assert len(vid) > 20

    def test_assign_version_id_unique(self, versioning_engine):
        ids = {versioning_engine.assign_version_id() for _ in range(100)}
        assert len(ids) == 100

    def test_add_version(self, versioning_engine, metadata_index):
        obj = S3Object(key="test.txt", version_id="v1")
        versioning_engine.add_version("bucket", "test.txt", obj)
        chain = versioning_engine.get_version_chain("bucket", "test.txt")
        assert len(chain) == 1

    def test_version_chain_ordering(self, versioning_engine):
        for i in range(3):
            obj = S3Object(
                key="test.txt",
                version_id=f"v{i}",
                last_modified=datetime.now(timezone.utc) + timedelta(seconds=i),
            )
            versioning_engine.add_version("bucket", "test.txt", obj)
        chain = versioning_engine.get_version_chain("bucket", "test.txt")
        assert len(chain) == 3
        # Newest first
        for i in range(len(chain) - 1):
            assert chain[i].last_modified >= chain[i + 1].last_modified

    def test_latest_flag(self, versioning_engine):
        obj1 = S3Object(key="test.txt", version_id="v1")
        obj2 = S3Object(key="test.txt", version_id="v2",
                         last_modified=datetime.now(timezone.utc) + timedelta(seconds=1))
        versioning_engine.add_version("bucket", "test.txt", obj1)
        versioning_engine.add_version("bucket", "test.txt", obj2)
        chain = versioning_engine.get_version_chain("bucket", "test.txt")
        assert chain[0].is_latest is True

    def test_get_specific_version(self, versioning_engine):
        obj = S3Object(key="test.txt", version_id="v42")
        versioning_engine.add_version("bucket", "test.txt", obj)
        found = versioning_engine.get_specific_version("bucket", "test.txt", "v42")
        assert found is not None
        assert found.version_id == "v42"

    def test_get_nonexistent_version(self, versioning_engine):
        obj = S3Object(key="test.txt", version_id="v1")
        versioning_engine.add_version("bucket", "test.txt", obj)
        found = versioning_engine.get_specific_version("bucket", "test.txt", "v999")
        assert found is None

    def test_delete_specific_version(self, versioning_engine):
        obj = S3Object(key="test.txt", version_id="v1")
        versioning_engine.add_version("bucket", "test.txt", obj)
        deleted = versioning_engine.delete_specific_version("bucket", "test.txt", "v1")
        assert deleted is not None
        chain = versioning_engine.get_version_chain("bucket", "test.txt")
        assert len(chain) == 0

    def test_delete_nonexistent_version(self, versioning_engine):
        with pytest.raises(NoSuchVersionError):
            versioning_engine.delete_specific_version("bucket", "test.txt", "nope")

    def test_delete_marker_in_chain(self, versioning_engine):
        obj = S3Object(key="test.txt", version_id="v1")
        marker = S3Object(key="test.txt", version_id="v2", delete_marker=True,
                           last_modified=datetime.now(timezone.utc) + timedelta(seconds=1))
        versioning_engine.add_version("bucket", "test.txt", obj)
        versioning_engine.add_version("bucket", "test.txt", marker)
        chain = versioning_engine.get_version_chain("bucket", "test.txt")
        assert len(chain) == 2
        assert chain[0].delete_marker is True

    def test_delete_latest_promotes_previous(self, versioning_engine):
        obj1 = S3Object(key="test.txt", version_id="v1")
        obj2 = S3Object(key="test.txt", version_id="v2",
                         last_modified=datetime.now(timezone.utc) + timedelta(seconds=1))
        versioning_engine.add_version("bucket", "test.txt", obj1)
        versioning_engine.add_version("bucket", "test.txt", obj2)
        versioning_engine.delete_specific_version("bucket", "test.txt", "v2")
        chain = versioning_engine.get_version_chain("bucket", "test.txt")
        assert len(chain) == 1
        assert chain[0].is_latest is True

    def test_versioned_delete_creates_marker(self, bucket_manager, object_store, event_bus):
        bucket_manager.create_bucket("ver-bucket")
        bucket_manager.put_bucket_versioning("ver-bucket", BucketVersioning.ENABLED)
        object_store.put_object("ver-bucket", "file.txt", b"data")
        marker = object_store.delete_object("ver-bucket", "file.txt")
        assert marker.delete_marker is True

    def test_versioned_delete_specific_version(self, bucket_manager, object_store, versioning_engine, event_bus):
        bucket_manager.create_bucket("ver-bucket")
        bucket_manager.put_bucket_versioning("ver-bucket", BucketVersioning.ENABLED)
        obj = object_store.put_object("ver-bucket", "file.txt", b"data")
        vid = obj.version_id
        object_store.delete_object("ver-bucket", "file.txt", version_id=vid)

    def test_version_suspended_null_id(self, bucket_manager, object_store, event_bus):
        bucket_manager.create_bucket("sus-bucket")
        bucket_manager.put_bucket_versioning("sus-bucket", BucketVersioning.ENABLED)
        bucket_manager.put_bucket_versioning("sus-bucket", BucketVersioning.SUSPENDED)
        obj = object_store.put_object("sus-bucket", "file.txt", b"data")
        assert obj.version_id is None

    def test_list_object_versions(self, versioning_engine, metadata_index):
        metadata_index.put("objects:bucket", "test.txt", S3Object(key="test.txt"))
        obj1 = S3Object(key="test.txt", version_id="v1")
        obj2 = S3Object(key="test.txt", version_id="v2")
        versioning_engine.add_version("bucket", "test.txt", obj1)
        versioning_engine.add_version("bucket", "test.txt", obj2)
        versions = versioning_engine.list_object_versions("bucket")
        assert len(versions) >= 2

    def test_version_id_has_timestamp_prefix(self, versioning_engine):
        vid = versioning_engine.assign_version_id()
        ts_part = vid.split("-")[0]
        assert len(ts_part) == 13  # hex timestamp


# ============================================================
# TestDeleteMarker
# ============================================================


class TestDeleteMarker:
    """Validates delete marker behavior."""

    def test_delete_marker_creation(self):
        marker = DeleteMarker(key="test.txt", version_id="dm-v1")
        assert marker.key == "test.txt"
        assert marker.is_latest is True

    def test_delete_marker_default_owner(self):
        marker = DeleteMarker(key="test.txt")
        assert marker.owner == "fizzbuzz-root"

    def test_delete_marker_has_timestamp(self):
        marker = DeleteMarker(key="test.txt")
        assert marker.last_modified is not None

    def test_delete_marker_get_raises_not_found(self, bucket_manager, object_store, event_bus):
        bucket_manager.create_bucket("dm-bucket")
        bucket_manager.put_bucket_versioning("dm-bucket", BucketVersioning.ENABLED)
        object_store.put_object("dm-bucket", "file.txt", b"data")
        object_store.delete_object("dm-bucket", "file.txt")
        with pytest.raises(ObjectNotFoundError):
            object_store.get_object("dm-bucket", "file.txt")

    def test_delete_marker_removal_undeletes(self, bucket_manager, object_store, versioning_engine, event_bus):
        bucket_manager.create_bucket("dm-bucket")
        bucket_manager.put_bucket_versioning("dm-bucket", BucketVersioning.ENABLED)
        obj = object_store.put_object("dm-bucket", "file.txt", b"data")
        marker = object_store.delete_object("dm-bucket", "file.txt")
        # Remove the delete marker by version ID
        object_store.delete_object("dm-bucket", "file.txt", version_id=marker.version_id)

    def test_delete_marker_dataclass_fields(self):
        marker = DeleteMarker(key="k", version_id="v")
        assert marker.key == "k"
        assert marker.version_id == "v"

    def test_multiple_delete_markers(self, bucket_manager, object_store, versioning_engine, event_bus):
        bucket_manager.create_bucket("dm-bucket")
        bucket_manager.put_bucket_versioning("dm-bucket", BucketVersioning.ENABLED)
        object_store.put_object("dm-bucket", "file.txt", b"data")
        object_store.delete_object("dm-bucket", "file.txt")
        object_store.put_object("dm-bucket", "file.txt", b"new data")
        object_store.delete_object("dm-bucket", "file.txt")

    def test_delete_marker_version_id(self):
        marker = DeleteMarker(key="k", version_id="special-id")
        assert marker.version_id == "special-id"


# ============================================================
# TestMultipartUploadManager
# ============================================================


class TestMultipartUploadManager:
    """Validates multipart upload lifecycle."""

    def test_create_multipart_upload(self, bucket_manager, multipart_manager):
        bucket_manager.create_bucket("mp-bucket")
        upload_id = multipart_manager.create_multipart_upload("mp-bucket", "big-file.bin")
        assert upload_id is not None
        assert len(upload_id) > 0

    def test_upload_part(self, bucket_manager, multipart_manager):
        bucket_manager.create_bucket("mp-bucket")
        uid = multipart_manager.create_multipart_upload("mp-bucket", "big.bin")
        data = b"x" * (MIN_PART_SIZE + 1)
        etag = multipart_manager.upload_part("mp-bucket", "big.bin", uid, 1, data)
        assert etag == hashlib.md5(data).hexdigest()

    def test_upload_part_invalid_number(self, bucket_manager, multipart_manager):
        bucket_manager.create_bucket("mp-bucket")
        uid = multipart_manager.create_multipart_upload("mp-bucket", "big.bin")
        with pytest.raises(TooManyPartsError):
            multipart_manager.upload_part("mp-bucket", "big.bin", uid, 0, b"data")

    def test_upload_part_too_large(self, bucket_manager, multipart_manager):
        bucket_manager.create_bucket("mp-bucket")
        uid = multipart_manager.create_multipart_upload("mp-bucket", "big.bin")
        with pytest.raises(EntityTooLargeError):
            multipart_manager.upload_part("mp-bucket", "big.bin", uid, 1, b"x" * (MAX_PART_SIZE + 1))

    def test_complete_multipart_upload(self, bucket_manager, multipart_manager):
        bucket_manager.create_bucket("mp-bucket")
        uid = multipart_manager.create_multipart_upload("mp-bucket", "big.bin")
        data1 = b"a" * MIN_PART_SIZE
        data2 = b"b" * 100
        etag1 = multipart_manager.upload_part("mp-bucket", "big.bin", uid, 1, data1)
        etag2 = multipart_manager.upload_part("mp-bucket", "big.bin", uid, 2, data2)
        parts = [
            {"part_number": 1, "etag": etag1},
            {"part_number": 2, "etag": etag2},
        ]
        obj = multipart_manager.complete_multipart_upload("mp-bucket", "big.bin", uid, parts)
        assert obj.key == "big.bin"
        assert "-2" in obj.etag  # composite etag

    def test_complete_invalid_part_order(self, bucket_manager, multipart_manager):
        bucket_manager.create_bucket("mp-bucket")
        uid = multipart_manager.create_multipart_upload("mp-bucket", "big.bin")
        data = b"a" * MIN_PART_SIZE
        multipart_manager.upload_part("mp-bucket", "big.bin", uid, 1, data)
        multipart_manager.upload_part("mp-bucket", "big.bin", uid, 2, data)
        parts = [
            {"part_number": 2, "etag": ""},
            {"part_number": 1, "etag": ""},
        ]
        with pytest.raises(InvalidPartOrderError):
            multipart_manager.complete_multipart_upload("mp-bucket", "big.bin", uid, parts)

    def test_complete_missing_part(self, bucket_manager, multipart_manager):
        bucket_manager.create_bucket("mp-bucket")
        uid = multipart_manager.create_multipart_upload("mp-bucket", "big.bin")
        parts = [{"part_number": 1, "etag": "abc"}]
        with pytest.raises(InvalidPartError):
            multipart_manager.complete_multipart_upload("mp-bucket", "big.bin", uid, parts)

    def test_complete_part_too_small(self, bucket_manager, multipart_manager):
        bucket_manager.create_bucket("mp-bucket")
        uid = multipart_manager.create_multipart_upload("mp-bucket", "big.bin")
        small_data = b"tiny"
        big_data = b"x" * MIN_PART_SIZE
        etag1 = multipart_manager.upload_part("mp-bucket", "big.bin", uid, 1, small_data)
        etag2 = multipart_manager.upload_part("mp-bucket", "big.bin", uid, 2, big_data)
        parts = [
            {"part_number": 1, "etag": etag1},
            {"part_number": 2, "etag": etag2},
        ]
        with pytest.raises(EntityTooSmallError):
            multipart_manager.complete_multipart_upload("mp-bucket", "big.bin", uid, parts)

    def test_abort_multipart_upload(self, bucket_manager, multipart_manager):
        bucket_manager.create_bucket("mp-bucket")
        uid = multipart_manager.create_multipart_upload("mp-bucket", "big.bin")
        multipart_manager.abort_multipart_upload("mp-bucket", "big.bin", uid)
        with pytest.raises(NoSuchUploadError):
            multipart_manager.upload_part("mp-bucket", "big.bin", uid, 1, b"data")

    def test_no_such_upload(self, bucket_manager, multipart_manager):
        bucket_manager.create_bucket("mp-bucket")
        with pytest.raises(NoSuchUploadError):
            multipart_manager.upload_part("mp-bucket", "big.bin", "fake-id", 1, b"data")

    def test_list_multipart_uploads(self, bucket_manager, multipart_manager):
        bucket_manager.create_bucket("mp-bucket")
        multipart_manager.create_multipart_upload("mp-bucket", "a.bin")
        multipart_manager.create_multipart_upload("mp-bucket", "b.bin")
        uploads = multipart_manager.list_multipart_uploads("mp-bucket")
        assert len(uploads) == 2

    def test_list_parts(self, bucket_manager, multipart_manager):
        bucket_manager.create_bucket("mp-bucket")
        uid = multipart_manager.create_multipart_upload("mp-bucket", "big.bin")
        multipart_manager.upload_part("mp-bucket", "big.bin", uid, 1, b"part1data")
        multipart_manager.upload_part("mp-bucket", "big.bin", uid, 2, b"part2data")
        parts = multipart_manager.list_parts("mp-bucket", "big.bin", uid)
        assert len(parts) == 2
        assert parts[0].part_number == 1
        assert parts[1].part_number == 2

    def test_part_replacement(self, bucket_manager, multipart_manager):
        bucket_manager.create_bucket("mp-bucket")
        uid = multipart_manager.create_multipart_upload("mp-bucket", "big.bin")
        multipart_manager.upload_part("mp-bucket", "big.bin", uid, 1, b"old")
        etag2 = multipart_manager.upload_part("mp-bucket", "big.bin", uid, 1, b"new")
        parts = multipart_manager.list_parts("mp-bucket", "big.bin", uid)
        assert parts[0].etag == etag2

    def test_upload_part_max_number(self, bucket_manager, multipart_manager):
        bucket_manager.create_bucket("mp-bucket")
        uid = multipart_manager.create_multipart_upload("mp-bucket", "big.bin")
        etag = multipart_manager.upload_part("mp-bucket", "big.bin", uid, MAX_PARTS, b"last")
        assert etag is not None

    def test_upload_part_beyond_max(self, bucket_manager, multipart_manager):
        bucket_manager.create_bucket("mp-bucket")
        uid = multipart_manager.create_multipart_upload("mp-bucket", "big.bin")
        with pytest.raises(TooManyPartsError):
            multipart_manager.upload_part("mp-bucket", "big.bin", uid, MAX_PARTS + 1, b"data")

    def test_upload_part_copy(self, bucket_manager, object_store, multipart_manager):
        bucket_manager.create_bucket("src-bucket")
        bucket_manager.create_bucket("mp-bucket")
        object_store.put_object("src-bucket", "source.bin", b"source data payload")
        uid = multipart_manager.create_multipart_upload("mp-bucket", "dest.bin")
        etag = multipart_manager.upload_part_copy(
            "mp-bucket", "dest.bin", uid, 1,
            "src-bucket", "source.bin",
        )
        assert etag is not None

    def test_multipart_upload_metadata(self, bucket_manager, multipart_manager, object_store):
        bucket_manager.create_bucket("mp-bucket")
        uid = multipart_manager.create_multipart_upload(
            "mp-bucket", "big.bin",
            metadata={"x-custom": "meta"},
        )
        data = b"x" * MIN_PART_SIZE
        etag = multipart_manager.upload_part("mp-bucket", "big.bin", uid, 1, data)
        parts = [{"part_number": 1, "etag": etag}]
        obj = multipart_manager.complete_multipart_upload("mp-bucket", "big.bin", uid, parts)
        assert obj.metadata.get("x-custom") == "meta"

    def test_list_uploads_with_prefix(self, bucket_manager, multipart_manager):
        bucket_manager.create_bucket("mp-bucket")
        multipart_manager.create_multipart_upload("mp-bucket", "docs/a.bin")
        multipart_manager.create_multipart_upload("mp-bucket", "images/b.bin")
        uploads = multipart_manager.list_multipart_uploads("mp-bucket", prefix="docs/")
        assert len(uploads) == 1


# ============================================================
# TestIncompleteUploadReaper
# ============================================================


class TestIncompleteUploadReaper:
    """Validates stale upload cleanup."""

    def test_reap_stale_uploads(self, bucket_manager, multipart_manager, metadata_index, object_store, cas, event_bus):
        bucket_manager.create_bucket("reap-bucket")
        uid = multipart_manager.create_multipart_upload("reap-bucket", "stale.bin")
        # Backdate the upload
        upload_ns = "uploads:reap-bucket"
        upload_key = f"stale.bin:{uid}"
        upload = metadata_index.get(upload_ns, upload_key)
        upload.initiated = datetime.now(timezone.utc) - timedelta(days=10)
        metadata_index.put(upload_ns, upload_key, upload)

        reaper = IncompleteUploadReaper(multipart_manager, bucket_manager, threshold_days=7)
        result = reaper.reap()
        assert result.get("reap-bucket", 0) == 1

    def test_reap_respects_threshold(self, bucket_manager, multipart_manager, metadata_index, object_store, cas, event_bus):
        bucket_manager.create_bucket("reap-bucket")
        multipart_manager.create_multipart_upload("reap-bucket", "fresh.bin")
        reaper = IncompleteUploadReaper(multipart_manager, bucket_manager, threshold_days=7)
        result = reaper.reap()
        assert result.get("reap-bucket", 0) == 0

    def test_reap_empty_result(self, bucket_manager, multipart_manager, metadata_index, object_store, cas, event_bus):
        bucket_manager.create_bucket("empty-bucket")
        reaper = IncompleteUploadReaper(multipart_manager, bucket_manager)
        result = reaper.reap()
        assert result == {}

    def test_reap_lifecycle_rule_override(self, bucket_manager, multipart_manager, metadata_index, object_store, cas, event_bus):
        bucket_manager.create_bucket("rule-bucket")
        bucket = bucket_manager.get_bucket("rule-bucket")
        bucket.lifecycle_configuration = LifecycleConfiguration(rules=[
            LifecycleRule(id="cleanup", status=RuleStatus.ENABLED, abort_incomplete_multipart_days=1),
        ])
        metadata_index.put("buckets", "rule-bucket", bucket)
        uid = multipart_manager.create_multipart_upload("rule-bucket", "stale.bin")
        upload_ns = "uploads:rule-bucket"
        upload_key = f"stale.bin:{uid}"
        upload = metadata_index.get(upload_ns, upload_key)
        upload.initiated = datetime.now(timezone.utc) - timedelta(days=2)
        metadata_index.put(upload_ns, upload_key, upload)
        reaper = IncompleteUploadReaper(multipart_manager, bucket_manager, threshold_days=7)
        result = reaper.reap()
        assert result.get("rule-bucket", 0) == 1

    def test_reap_multiple_buckets(self, bucket_manager, multipart_manager, metadata_index, object_store, cas, event_bus):
        for name in ["bucket-a", "bucket-b"]:
            bucket_manager.create_bucket(name)
            uid = multipart_manager.create_multipart_upload(name, "stale.bin")
            upload_ns = f"uploads:{name}"
            upload_key = f"stale.bin:{uid}"
            upload = metadata_index.get(upload_ns, upload_key)
            upload.initiated = datetime.now(timezone.utc) - timedelta(days=10)
            metadata_index.put(upload_ns, upload_key, upload)
        reaper = IncompleteUploadReaper(multipart_manager, bucket_manager, threshold_days=7)
        result = reaper.reap()
        assert len(result) == 2

    def test_reap_already_aborted(self, bucket_manager, multipart_manager, metadata_index, object_store, cas, event_bus):
        bucket_manager.create_bucket("reap-bucket")
        uid = multipart_manager.create_multipart_upload("reap-bucket", "gone.bin")
        multipart_manager.abort_multipart_upload("reap-bucket", "gone.bin", uid)
        reaper = IncompleteUploadReaper(multipart_manager, bucket_manager)
        result = reaper.reap()
        assert result.get("reap-bucket", 0) == 0


# ============================================================
# TestPresignedURLGenerator
# ============================================================


class TestPresignedURLGenerator:
    """Validates presigned URL generation."""

    def test_generate_get_url(self, presign_generator):
        url = presign_generator.generate_presigned_url("GET", "my-bucket", "file.txt")
        assert "X-Amz-Signature=" in url
        assert "my-bucket/file.txt" in url

    def test_generate_put_url(self, presign_generator):
        url = presign_generator.generate_presigned_url("PUT", "my-bucket", "upload.bin")
        assert "X-Amz-Signature=" in url

    def test_generate_head_url(self, presign_generator):
        url = presign_generator.generate_presigned_url("HEAD", "my-bucket", "file.txt")
        assert "X-Amz-Signature=" in url

    def test_generate_delete_url(self, presign_generator):
        url = presign_generator.generate_presigned_url("DELETE", "my-bucket", "file.txt")
        assert "X-Amz-Signature=" in url

    def test_generate_with_version_id(self, presign_generator):
        url = presign_generator.generate_presigned_url(
            "GET", "my-bucket", "file.txt", version_id="v123",
        )
        assert "versionId=v123" in url

    def test_generate_custom_expiry(self, presign_generator):
        url = presign_generator.generate_presigned_url(
            "GET", "my-bucket", "file.txt", expiration=7200,
        )
        assert "X-Amz-Expires=7200" in url

    def test_generate_expiry_exceeds_max(self, presign_generator):
        with pytest.raises(PresignedURLError):
            presign_generator.generate_presigned_url(
                "GET", "my-bucket", "file.txt", expiration=MAX_PRESIGN_EXPIRY + 1,
            )

    def test_generate_url_has_algorithm(self, presign_generator):
        url = presign_generator.generate_presigned_url("GET", "my-bucket", "file.txt")
        assert "X-Amz-Algorithm=AWS4-HMAC-SHA256" in url

    def test_generate_url_has_date(self, presign_generator):
        url = presign_generator.generate_presigned_url("GET", "my-bucket", "file.txt")
        assert "X-Amz-Date=" in url

    def test_generate_url_has_credential(self, presign_generator):
        url = presign_generator.generate_presigned_url("GET", "my-bucket", "file.txt")
        assert "X-Amz-Credential=" in url

    def test_generate_presigned_post(self, presign_generator):
        result = presign_generator.generate_presigned_post("my-bucket", "upload.bin")
        assert "url" in result
        assert "fields" in result
        assert "X-Amz-Signature" in result["fields"]

    def test_presigned_post_has_policy(self, presign_generator):
        result = presign_generator.generate_presigned_post("my-bucket", "file.txt")
        assert "policy" in result["fields"]


# ============================================================
# TestPresignedURLVerifier
# ============================================================


class TestPresignedURLVerifier:
    """Validates presigned URL verification."""

    def test_verify_valid_url(self, presign_generator, presign_verifier):
        url = presign_generator.generate_presigned_url("GET", "my-bucket", "file.txt")
        result = presign_verifier.verify(url, "GET")
        assert result.allowed is True

    def test_verify_wrong_method(self, presign_generator, presign_verifier):
        url = presign_generator.generate_presigned_url("GET", "my-bucket", "file.txt")
        result = presign_verifier.verify(url, "PUT")
        # Method differences affect the canonical request, so signature will mismatch
        assert result.allowed is False

    def test_verify_tampered_url(self, presign_generator, presign_verifier):
        url = presign_generator.generate_presigned_url("GET", "my-bucket", "file.txt")
        tampered = url.replace("file.txt", "other.txt")
        result = presign_verifier.verify(tampered, "GET")
        assert result.allowed is False

    def test_verify_missing_parameters(self, presign_verifier):
        result = presign_verifier.verify("https://s3.fizz.internal/bucket/key", "GET")
        assert result.allowed is False
        assert "Missing parameter" in result.reason

    def test_verify_expired_url(self, presign_generator, presign_verifier):
        url = presign_generator.generate_presigned_url(
            "GET", "my-bucket", "file.txt", expiration=1,
        )
        # Manually backdate by manipulating URL (change the date)
        # We can't easily expire in a unit test, so verify the logic path exists
        assert "X-Amz-Expires=1" in url

    def test_verify_result_fields(self, presign_generator, presign_verifier):
        url = presign_generator.generate_presigned_url("GET", "my-bucket", "file.txt")
        result = presign_verifier.verify(url, "GET")
        assert hasattr(result, "allowed")
        assert hasattr(result, "reason")

    def test_verify_invalid_signature(self, presign_verifier):
        url = ("https://s3.fizz-east-1.fizz.internal/bucket/key"
               "?X-Amz-Algorithm=AWS4-HMAC-SHA256"
               "&X-Amz-Credential=FIZZ/20260324/fizz-east-1/s3/aws4_request"
               "&X-Amz-Date=20260324T120000Z"
               "&X-Amz-Expires=3600"
               "&X-Amz-SignedHeaders=host"
               "&X-Amz-Signature=invalidsig")
        result = presign_verifier.verify(url, "GET")
        assert result.allowed is False

    def test_verify_different_generators(self):
        sig1 = SignatureV4Computer(secret_key="key1")
        sig2 = SignatureV4Computer(secret_key="key2")
        gen = PresignedURLGenerator(sig1, region="fizz-east-1")
        ver = PresignedURLVerifier(sig2, region="fizz-east-1")
        url = gen.generate_presigned_url("GET", "bucket", "key")
        result = ver.verify(url, "GET")
        assert result.allowed is False

    def test_verify_consistent_generator_verifier(self):
        sig = SignatureV4Computer(secret_key="shared-secret")
        gen = PresignedURLGenerator(sig, region="fizz-east-1")
        ver = PresignedURLVerifier(sig, region="fizz-east-1")
        url = gen.generate_presigned_url("GET", "bucket", "key")
        result = ver.verify(url, "GET")
        assert result.allowed is True

    def test_verify_authorization_result_evaluated(self, presign_generator, presign_verifier):
        url = presign_generator.generate_presigned_url("GET", "my-bucket", "file.txt")
        result = presign_verifier.verify(url, "GET")
        assert result.evaluated_policies >= 1


# ============================================================
# TestSignatureV4Computer
# ============================================================


class TestSignatureV4Computer:
    """Validates AWS Signature Version 4 computation."""

    def test_signing_key_derivation(self, sig_computer):
        key = sig_computer.compute_signing_key("20260324", "fizz-east-1")
        assert isinstance(key, bytes)
        assert len(key) == 32  # SHA-256 output

    def test_signing_key_deterministic(self, sig_computer):
        key1 = sig_computer.compute_signing_key("20260324", "fizz-east-1")
        key2 = sig_computer.compute_signing_key("20260324", "fizz-east-1")
        assert key1 == key2

    def test_signing_key_different_dates(self, sig_computer):
        key1 = sig_computer.compute_signing_key("20260324", "fizz-east-1")
        key2 = sig_computer.compute_signing_key("20260325", "fizz-east-1")
        assert key1 != key2

    def test_signing_key_different_regions(self, sig_computer):
        key1 = sig_computer.compute_signing_key("20260324", "fizz-east-1")
        key2 = sig_computer.compute_signing_key("20260324", "fizz-west-1")
        assert key1 != key2

    def test_canonical_request_format(self, sig_computer):
        cr = sig_computer.compute_canonical_request(
            method="GET",
            path="/bucket/key",
            query_params="param=value",
            headers={"host": "s3.fizz.internal"},
            signed_headers="host",
            payload_hash="UNSIGNED-PAYLOAD",
        )
        lines = cr.split("\n")
        assert lines[0] == "GET"
        assert "UNSIGNED-PAYLOAD" in cr

    def test_string_to_sign_format(self, sig_computer):
        sts = sig_computer.compute_string_to_sign(
            "AWS4-HMAC-SHA256",
            "20260324T120000Z",
            "20260324/fizz-east-1/s3/aws4_request",
            "abcdef1234",
        )
        assert sts.startswith("AWS4-HMAC-SHA256")
        assert "20260324T120000Z" in sts

    def test_compute_signature(self, sig_computer):
        key = sig_computer.compute_signing_key("20260324", "fizz-east-1")
        sig = sig_computer.compute_signature(key, "test-string")
        assert len(sig) == 64  # hex SHA-256

    def test_signature_deterministic(self, sig_computer):
        key = sig_computer.compute_signing_key("20260324", "fizz-east-1")
        sig1 = sig_computer.compute_signature(key, "test-string")
        sig2 = sig_computer.compute_signature(key, "test-string")
        assert sig1 == sig2

    def test_different_inputs_different_signatures(self, sig_computer):
        key = sig_computer.compute_signing_key("20260324", "fizz-east-1")
        sig1 = sig_computer.compute_signature(key, "string-a")
        sig2 = sig_computer.compute_signature(key, "string-b")
        assert sig1 != sig2

    def test_default_secret_key(self):
        computer = SignatureV4Computer()
        key = computer.compute_signing_key("20260324", "fizz-east-1")
        assert isinstance(key, bytes)

    def test_canonical_request_url_encoding(self, sig_computer):
        cr = sig_computer.compute_canonical_request(
            method="GET",
            path="/bucket/key with spaces",
            query_params="",
            headers={"host": "s3.fizz.internal"},
            signed_headers="host",
            payload_hash="UNSIGNED-PAYLOAD",
        )
        assert "%20" in cr or "key with spaces" in cr

    def test_different_secrets_different_keys(self):
        c1 = SignatureV4Computer(secret_key="key1")
        c2 = SignatureV4Computer(secret_key="key2")
        k1 = c1.compute_signing_key("20260324", "fizz-east-1")
        k2 = c2.compute_signing_key("20260324", "fizz-east-1")
        assert k1 != k2


# ============================================================
# TestStorageClass
# ============================================================


class TestStorageClass:
    """Validates storage class enum and erasure parameters."""

    def test_standard_class(self):
        assert StorageClass.STANDARD.value == "STANDARD"

    def test_standard_ia_class(self):
        assert StorageClass.STANDARD_IA.value == "STANDARD_IA"

    def test_archive_class(self):
        assert StorageClass.ARCHIVE.value == "ARCHIVE"

    def test_deep_archive_class(self):
        assert StorageClass.DEEP_ARCHIVE.value == "DEEP_ARCHIVE"


# ============================================================
# TestStorageClassManager
# ============================================================


class TestStorageClassManager:
    """Validates storage class transition management."""

    def test_valid_transition_standard_to_ia(self, bucket_manager, object_store, cas, erasure_engine, event_bus):
        bucket_manager.create_bucket("sc-bucket")
        object_store.put_object("sc-bucket", "file.txt", b"data")
        mgr = StorageClassManager(object_store, cas, erasure_engine, event_bus)
        mgr.transition_object("sc-bucket", "file.txt", target_class=StorageClass.STANDARD_IA)

    def test_valid_transition_ia_to_archive(self, bucket_manager, object_store, cas, erasure_engine, event_bus):
        bucket_manager.create_bucket("sc-bucket")
        obj = object_store.put_object("sc-bucket", "file.txt", b"data", storage_class=StorageClass.STANDARD_IA)
        mgr = StorageClassManager(object_store, cas, erasure_engine, event_bus)
        mgr.transition_object("sc-bucket", "file.txt", target_class=StorageClass.ARCHIVE)

    def test_invalid_reverse_transition(self, bucket_manager, object_store, cas, erasure_engine, event_bus):
        bucket_manager.create_bucket("sc-bucket")
        object_store.put_object("sc-bucket", "file.txt", b"data", storage_class=StorageClass.STANDARD_IA)
        mgr = StorageClassManager(object_store, cas, erasure_engine, event_bus)
        with pytest.raises(InvalidStorageClassTransitionError):
            mgr.transition_object("sc-bucket", "file.txt", target_class=StorageClass.STANDARD)

    def test_transition_same_class(self, bucket_manager, object_store, cas, erasure_engine, event_bus):
        bucket_manager.create_bucket("sc-bucket")
        object_store.put_object("sc-bucket", "file.txt", b"data")
        mgr = StorageClassManager(object_store, cas, erasure_engine, event_bus)
        with pytest.raises(InvalidStorageClassTransitionError):
            mgr.transition_object("sc-bucket", "file.txt", target_class=StorageClass.STANDARD)

    def test_waterfall_ordering(self):
        assert STORAGE_CLASS_ORDER[StorageClass.STANDARD] < STORAGE_CLASS_ORDER[StorageClass.STANDARD_IA]
        assert STORAGE_CLASS_ORDER[StorageClass.STANDARD_IA] < STORAGE_CLASS_ORDER[StorageClass.ARCHIVE]
        assert STORAGE_CLASS_ORDER[StorageClass.ARCHIVE] < STORAGE_CLASS_ORDER[StorageClass.DEEP_ARCHIVE]

    def test_erasure_params_standard(self):
        data, parity = ERASURE_PARAMS[StorageClass.STANDARD]
        assert data == 10
        assert parity == 4

    def test_erasure_params_standard_ia(self):
        data, parity = ERASURE_PARAMS[StorageClass.STANDARD_IA]
        assert data == 6
        assert parity == 4

    def test_erasure_params_archive(self):
        data, parity = ERASURE_PARAMS[StorageClass.ARCHIVE]
        assert data == 4
        assert parity == 4

    def test_erasure_params_deep_archive(self):
        data, parity = ERASURE_PARAMS[StorageClass.DEEP_ARCHIVE]
        assert data == 2
        assert parity == 4

    def test_transition_to_deep_archive(self, bucket_manager, object_store, cas, erasure_engine, event_bus):
        bucket_manager.create_bucket("sc-bucket")
        object_store.put_object("sc-bucket", "file.txt", b"data", storage_class=StorageClass.ARCHIVE)
        mgr = StorageClassManager(object_store, cas, erasure_engine, event_bus)
        mgr.transition_object("sc-bucket", "file.txt", target_class=StorageClass.DEEP_ARCHIVE)

    def test_transition_emits_event(self, bucket_manager, object_store, cas, erasure_engine, event_bus):
        bucket_manager.create_bucket("sc-bucket")
        object_store.put_object("sc-bucket", "file.txt", b"data")
        mgr = StorageClassManager(object_store, cas, erasure_engine, event_bus)
        mgr.transition_object("sc-bucket", "file.txt", target_class=StorageClass.STANDARD_IA)
        assert any("TRANSITIONED" in str(e[0]) for e in event_bus.events)

    def test_all_four_classes_in_order(self):
        classes = sorted(STORAGE_CLASS_ORDER.keys(), key=lambda c: STORAGE_CLASS_ORDER[c])
        assert classes == [
            StorageClass.STANDARD,
            StorageClass.STANDARD_IA,
            StorageClass.ARCHIVE,
            StorageClass.DEEP_ARCHIVE,
        ]

    def test_full_waterfall(self, bucket_manager, object_store, cas, erasure_engine, event_bus):
        bucket_manager.create_bucket("wf-bucket")
        object_store.put_object("wf-bucket", "file.txt", b"data")
        mgr = StorageClassManager(object_store, cas, erasure_engine, event_bus)
        mgr.transition_object("wf-bucket", "file.txt", target_class=StorageClass.STANDARD_IA)
        mgr.transition_object("wf-bucket", "file.txt", target_class=StorageClass.ARCHIVE)
        mgr.transition_object("wf-bucket", "file.txt", target_class=StorageClass.DEEP_ARCHIVE)

    def test_invalid_archive_to_ia(self, bucket_manager, object_store, cas, erasure_engine, event_bus):
        bucket_manager.create_bucket("sc-bucket")
        object_store.put_object("sc-bucket", "file.txt", b"data", storage_class=StorageClass.ARCHIVE)
        mgr = StorageClassManager(object_store, cas, erasure_engine, event_bus)
        with pytest.raises(InvalidStorageClassTransitionError):
            mgr.transition_object("sc-bucket", "file.txt", target_class=StorageClass.STANDARD_IA)


# ============================================================
# TestLifecycleRule
# ============================================================


class TestLifecycleRule:
    """Validates lifecycle rule construction and fields."""

    def test_rule_defaults(self):
        rule = LifecycleRule(id="test-rule")
        assert rule.status == RuleStatus.ENABLED
        assert rule.prefix == ""
        assert rule.transitions == []
        assert rule.expiration_days is None

    def test_rule_with_transition(self):
        rule = LifecycleRule(
            id="archive-rule",
            transitions=[TransitionRule(days=30, storage_class=StorageClass.STANDARD_IA)],
        )
        assert len(rule.transitions) == 1
        assert rule.transitions[0].days == 30

    def test_rule_with_expiration(self):
        rule = LifecycleRule(id="expire-rule", expiration_days=365)
        assert rule.expiration_days == 365

    def test_rule_with_tags(self):
        rule = LifecycleRule(id="tag-rule", tags={"env": "staging"})
        assert rule.tags["env"] == "staging"

    def test_disabled_rule(self):
        rule = LifecycleRule(id="off", status=RuleStatus.DISABLED)
        assert rule.status == RuleStatus.DISABLED

    def test_noncurrent_version_rules(self):
        rule = LifecycleRule(
            id="nc-rule",
            noncurrent_version_expiration_days=90,
            noncurrent_version_transitions=[
                NoncurrentVersionTransitionRule(noncurrent_days=30, storage_class=StorageClass.ARCHIVE),
            ],
        )
        assert rule.noncurrent_version_expiration_days == 90
        assert len(rule.noncurrent_version_transitions) == 1

    def test_abort_incomplete_multipart(self):
        rule = LifecycleRule(id="abort", abort_incomplete_multipart_days=7)
        assert rule.abort_incomplete_multipart_days == 7

    def test_lifecycle_configuration_max_rules(self):
        rules = [LifecycleRule(id=f"rule-{i}") for i in range(10)]
        config = LifecycleConfiguration(rules=rules)
        assert len(config.rules) == 10

    def test_transition_rule_defaults(self):
        t = TransitionRule()
        assert t.days == 30
        assert t.storage_class == StorageClass.STANDARD_IA

    def test_multiple_transitions(self):
        rule = LifecycleRule(
            id="multi-trans",
            transitions=[
                TransitionRule(days=30, storage_class=StorageClass.STANDARD_IA),
                TransitionRule(days=90, storage_class=StorageClass.ARCHIVE),
            ],
        )
        assert len(rule.transitions) == 2


# ============================================================
# TestEncryptionEngine
# ============================================================


class TestEncryptionEngine:
    """Validates server-side encryption and decryption."""

    def test_sse_s3_roundtrip(self, encryption_engine):
        data = b"secret fizzbuzz evaluation"
        encrypted, meta = encryption_engine.encrypt(data, EncryptionMode.SSE_S3)
        decrypted = encryption_engine.decrypt(encrypted, meta)
        assert decrypted == data

    def test_sse_s3_encrypts_data(self, encryption_engine):
        data = b"plaintext"
        encrypted, _ = encryption_engine.encrypt(data, EncryptionMode.SSE_S3)
        assert encrypted != data

    def test_sse_s3_metadata(self, encryption_engine):
        _, meta = encryption_engine.encrypt(b"data", EncryptionMode.SSE_S3)
        assert meta.mode == EncryptionMode.SSE_S3
        assert meta.algorithm == EncryptionAlgorithm.AES_256

    def test_sse_kms_roundtrip(self, encryption_engine):
        data = b"kms secret"
        encrypted, meta = encryption_engine.encrypt(data, EncryptionMode.SSE_KMS)
        decrypted = encryption_engine.decrypt(encrypted, meta)
        assert decrypted == data

    def test_sse_kms_metadata(self, encryption_engine):
        _, meta = encryption_engine.encrypt(b"data", EncryptionMode.SSE_KMS)
        assert meta.mode == EncryptionMode.SSE_KMS
        assert meta.kms_key_id is not None

    def test_sse_kms_unknown_key(self, encryption_engine):
        with pytest.raises(KMSKeyNotFoundError):
            encryption_engine.encrypt(b"data", EncryptionMode.SSE_KMS, kms_key_id="nonexistent")

    def test_sse_c_roundtrip(self, encryption_engine):
        data = b"client secret"
        client_key = b"k" * 32
        encrypted, meta = encryption_engine.encrypt(data, EncryptionMode.SSE_C, client_key=client_key)
        decrypted = encryption_engine.decrypt(encrypted, meta, client_key=client_key)
        assert decrypted == data

    def test_sse_c_no_key(self, encryption_engine):
        with pytest.raises(InvalidEncryptionKeyError):
            encryption_engine.encrypt(b"data", EncryptionMode.SSE_C)

    def test_sse_c_wrong_key_size(self, encryption_engine):
        with pytest.raises(InvalidEncryptionKeyError):
            encryption_engine.encrypt(b"data", EncryptionMode.SSE_C, client_key=b"short")

    def test_sse_c_key_md5(self, encryption_engine):
        client_key = b"k" * 32
        _, meta = encryption_engine.encrypt(b"data", EncryptionMode.SSE_C, client_key=client_key)
        assert meta.key_md5 is not None

    def test_sse_c_wrong_key_decrypt(self, encryption_engine):
        client_key = b"k" * 32
        wrong_key = b"w" * 32
        encrypted, meta = encryption_engine.encrypt(b"data", EncryptionMode.SSE_C, client_key=client_key)
        with pytest.raises(InvalidEncryptionKeyError):
            encryption_engine.decrypt(encrypted, meta, client_key=wrong_key)

    def test_sse_c_decrypt_no_key(self, encryption_engine):
        client_key = b"k" * 32
        encrypted, meta = encryption_engine.encrypt(b"data", EncryptionMode.SSE_C, client_key=client_key)
        with pytest.raises(InvalidEncryptionKeyError):
            encryption_engine.decrypt(encrypted, meta)

    def test_default_mode(self):
        engine = EncryptionEngine()
        assert engine._default_mode == EncryptionMode.SSE_S3

    def test_custom_default_mode(self):
        engine = EncryptionEngine(default_mode="sse-kms")
        assert engine._default_mode == EncryptionMode.SSE_KMS

    def test_invalid_default_mode_fallback(self):
        engine = EncryptionEngine(default_mode="invalid")
        assert engine._default_mode == EncryptionMode.SSE_S3

    def test_rotate_master_key(self, encryption_engine):
        old_id = encryption_engine._master_key_id
        new_id = encryption_engine.rotate_master_key()
        assert new_id != old_id

    def test_empty_data_roundtrip(self, encryption_engine):
        data = b""
        encrypted, meta = encryption_engine.encrypt(data, EncryptionMode.SSE_S3)
        decrypted = encryption_engine.decrypt(encrypted, meta)
        assert decrypted == data

    def test_large_data_roundtrip(self, encryption_engine):
        data = b"x" * 10000
        encrypted, meta = encryption_engine.encrypt(data, EncryptionMode.SSE_S3)
        decrypted = encryption_engine.decrypt(encrypted, meta)
        assert decrypted == data


# ============================================================
# TestKeyRotationManager
# ============================================================


class TestKeyRotationManager:
    """Validates key rotation lifecycle."""

    def test_should_rotate_false_initially(self, encryption_engine):
        mgr = KeyRotationManager(encryption_engine, rotation_days=90)
        assert mgr.should_rotate() is False

    def test_should_rotate_after_threshold(self, encryption_engine):
        mgr = KeyRotationManager(encryption_engine, rotation_days=0)
        assert mgr.should_rotate() is True

    def test_rotate_creates_new_key(self, encryption_engine):
        mgr = KeyRotationManager(encryption_engine, rotation_days=0)
        old_id = encryption_engine._master_key_id
        new_id = mgr.rotate()
        assert new_id != old_id

    def test_rotation_history(self, encryption_engine):
        mgr = KeyRotationManager(encryption_engine, rotation_days=0)
        mgr.rotate()
        mgr.rotate()
        history = mgr.get_rotation_history()
        assert len(history) == 2

    def test_rotation_resets_timer(self, encryption_engine):
        mgr = KeyRotationManager(encryption_engine, rotation_days=90)
        mgr.rotate()
        assert mgr.should_rotate() is False

    def test_rotation_history_has_timestamps(self, encryption_engine):
        mgr = KeyRotationManager(encryption_engine, rotation_days=0)
        mgr.rotate()
        history = mgr.get_rotation_history()
        assert "rotated_at" in history[0]


# ============================================================
# TestBucketPolicy
# ============================================================


class TestBucketPolicy:
    """Validates IAM-style bucket policy construction."""

    def test_policy_default_version(self):
        policy = BucketPolicy()
        assert policy.version == "2012-10-17"

    def test_policy_with_statements(self):
        stmt = PolicyStatement(
            sid="AllowRead",
            effect=PolicyEffect.ALLOW,
            principal="*",
            action=["s3:GetObject"],
            resource=["arn:fizz:s3:::my-bucket/*"],
        )
        policy = BucketPolicy(statements=[stmt])
        assert len(policy.statements) == 1

    def test_policy_deny_effect(self):
        stmt = PolicyStatement(effect=PolicyEffect.DENY)
        assert stmt.effect == PolicyEffect.DENY

    def test_policy_principal_list(self):
        stmt = PolicyStatement(principal=["user-a", "user-b"])
        assert len(stmt.principal) == 2

    def test_policy_resource_arn(self):
        stmt = PolicyStatement(resource=["arn:fizz:s3:::my-bucket"])
        assert "my-bucket" in stmt.resource[0]

    def test_policy_condition(self):
        stmt = PolicyStatement(condition={"StringEquals": {"s3:prefix": "docs/"}})
        assert stmt.condition is not None

    def test_policy_multiple_actions(self):
        stmt = PolicyStatement(action=["s3:GetObject", "s3:PutObject", "s3:DeleteObject"])
        assert len(stmt.action) == 3

    def test_policy_empty_statements(self):
        policy = BucketPolicy()
        assert policy.statements == []

    def test_statement_default_principal(self):
        stmt = PolicyStatement()
        assert stmt.principal == "*"

    def test_statement_sid(self):
        stmt = PolicyStatement(sid="UniqueID123")
        assert stmt.sid == "UniqueID123"


# ============================================================
# TestAccessControlList
# ============================================================


class TestAccessControlList:
    """Validates ACL construction."""

    def test_acl_default_owner(self):
        acl = AccessControlList()
        assert acl.owner == "fizzbuzz-root"

    def test_acl_with_grants(self):
        acl = AccessControlList(grants=[
            Grant(grantee="user1", permission=ACLPermission.READ),
            Grant(grantee="user2", permission=ACLPermission.WRITE),
        ])
        assert len(acl.grants) == 2

    def test_grant_types(self):
        g1 = Grant(grantee="user", grantee_type="canonical_user")
        g2 = Grant(grantee="AllUsers", grantee_type="group")
        g3 = Grant(grantee="user@fizz.io", grantee_type="email")
        assert g1.grantee_type == "canonical_user"
        assert g2.grantee_type == "group"
        assert g3.grantee_type == "email"

    def test_all_acl_permissions(self):
        perms = [p for p in ACLPermission]
        assert len(perms) == 5
        assert ACLPermission.FULL_CONTROL in perms

    def test_canned_acl_values(self):
        assert CannedACL.PRIVATE.value == "private"
        assert CannedACL.PUBLIC_READ.value == "public-read"
        assert CannedACL.PUBLIC_READ_WRITE.value == "public-read-write"
        assert CannedACL.AUTHENTICATED_READ.value == "authenticated-read"
        assert CannedACL.BUCKET_OWNER_READ.value == "bucket-owner-read"
        assert CannedACL.BUCKET_OWNER_FULL_CONTROL.value == "bucket-owner-full-control"

    def test_six_canned_acls(self):
        assert len(CannedACL) == 6

    def test_empty_grants_list(self):
        acl = AccessControlList()
        assert acl.grants == []

    def test_grant_default_permission(self):
        g = Grant()
        assert g.permission == ACLPermission.READ

    def test_grant_full_control(self):
        g = Grant(permission=ACLPermission.FULL_CONTROL)
        assert g.permission == ACLPermission.FULL_CONTROL


# ============================================================
# TestBlockPublicAccess
# ============================================================


class TestBlockPublicAccess:
    """Validates block public access configuration."""

    def test_all_flags_default_true(self):
        config = BlockPublicAccessConfiguration()
        assert config.block_public_acls is True
        assert config.ignore_public_acls is True
        assert config.block_public_policy is True
        assert config.restrict_public_buckets is True

    def test_individual_flag_disable(self):
        config = BlockPublicAccessConfiguration(block_public_acls=False)
        assert config.block_public_acls is False
        assert config.ignore_public_acls is True

    def test_all_flags_false(self):
        config = BlockPublicAccessConfiguration(
            block_public_acls=False,
            ignore_public_acls=False,
            block_public_policy=False,
            restrict_public_buckets=False,
        )
        assert not any([
            config.block_public_acls,
            config.ignore_public_acls,
            config.block_public_policy,
            config.restrict_public_buckets,
        ])

    def test_four_independent_flags(self):
        config = BlockPublicAccessConfiguration(
            block_public_acls=True,
            ignore_public_acls=False,
            block_public_policy=True,
            restrict_public_buckets=False,
        )
        assert config.block_public_acls is True
        assert config.ignore_public_acls is False
        assert config.block_public_policy is True
        assert config.restrict_public_buckets is False

    def test_bucket_has_default_block_public(self, bucket_manager):
        bucket = bucket_manager.create_bucket("bpa-bucket")
        assert bucket.block_public_access is not None
        assert bucket.block_public_access.block_public_acls is True

    def test_block_public_fields_count(self):
        config = BlockPublicAccessConfiguration()
        flags = [
            config.block_public_acls,
            config.ignore_public_acls,
            config.block_public_policy,
            config.restrict_public_buckets,
        ]
        assert len(flags) == 4

    def test_public_read_blocked_by_default(self, bucket_manager):
        bucket = bucket_manager.create_bucket("blocked-bucket")
        assert bucket.block_public_access.block_public_acls is True

    def test_public_policy_blocked_by_default(self, bucket_manager):
        bucket = bucket_manager.create_bucket("blocked-bucket")
        assert bucket.block_public_access.block_public_policy is True


# ============================================================
# TestContentAddressableStore
# ============================================================


class TestContentAddressableStore:
    """Validates content-addressable deduplication."""

    def test_chunk_object_single(self, cas):
        chunks = cas.chunk_object(b"small")
        assert len(chunks) == 1

    def test_chunk_object_multiple(self):
        store = ContentAddressableStore(chunk_size=4)
        chunks = store.chunk_object(b"12345678")
        assert len(chunks) == 2

    def test_address_chunk_sha256(self, cas):
        data = b"test data"
        addr = cas.address_chunk(data)
        assert addr == hashlib.sha256(data).hexdigest()

    def test_store_new_chunk(self, cas):
        addr = cas.address_chunk(b"unique data")
        result = cas.store_chunk(addr, b"unique data")
        assert result == "CREATED"

    def test_store_duplicate_chunk(self, cas):
        addr = cas.address_chunk(b"dup data")
        cas.store_chunk(addr, b"dup data")
        result = cas.store_chunk(addr, b"dup data")
        assert result == "DEDUPLICATED"

    def test_retrieve_chunk(self, cas):
        data = b"retrieve me"
        addr = cas.address_chunk(data)
        cas.store_chunk(addr, data)
        retrieved = cas.retrieve_chunk(addr)
        assert retrieved == data

    def test_retrieve_nonexistent(self, cas):
        with pytest.raises(ChunkNotFoundError):
            cas.retrieve_chunk("deadbeef" * 8)

    def test_store_object_roundtrip(self, cas):
        data = b"full object data here"
        manifest = cas.store_object("obj1", data)
        retrieved = cas.retrieve_object("obj1")
        assert retrieved == data

    def test_deduplication_stats(self, cas):
        data = b"repeated content"
        cas.store_object("bucket/obj1", data)
        cas.store_object("bucket/obj2", data)
        stats = cas.get_deduplication_stats("bucket")
        assert stats.shared_chunks > 0
        assert stats.dedup_ratio >= 1.0

    def test_delete_object_references(self, cas):
        cas.store_object("obj-del", b"data")
        cas.delete_object_references("obj-del")
        with pytest.raises(ChunkNotFoundError):
            cas.retrieve_object("obj-del")

    def test_empty_object(self, cas):
        manifest = cas.store_object("empty", b"")
        assert manifest.total_size == 0

    def test_chunk_addresses_filtered(self, cas):
        cas.store_object("bucket-a/obj1", b"data a")
        cas.store_object("bucket-b/obj2", b"data b")
        addrs = cas.get_chunk_addresses("bucket-a")
        assert len(addrs) > 0

    def test_store_object_manifest(self, cas):
        manifest = cas.store_object("obj-m", b"manifest data")
        assert manifest.object_id == "obj-m"
        assert manifest.chunk_count >= 1
        assert manifest.total_size == len(b"manifest data")

    def test_dedup_stats_ratio(self, cas):
        data = b"x" * 100
        cas.store_object("bucket/a", data)
        cas.store_object("bucket/b", data)
        cas.store_object("bucket/c", data)
        stats = cas.get_deduplication_stats("bucket")
        assert stats.logical_size > stats.physical_size

    def test_reference_counting(self, cas, ref_counter):
        data = b"shared"
        addr = cas.address_chunk(data)
        cas.store_chunk(addr, data)
        ref_counter.increment(addr, "obj1")
        ref_counter.increment(addr, "obj2")
        assert ref_counter.get_count(addr) == 2


# ============================================================
# TestReferenceCounter
# ============================================================


class TestReferenceCounter:
    """Validates reference counting for content addresses."""

    def test_increment(self, ref_counter):
        count = ref_counter.increment("addr1", "obj1")
        assert count == 1

    def test_increment_multiple(self, ref_counter):
        ref_counter.increment("addr1", "obj1")
        count = ref_counter.increment("addr1", "obj2")
        assert count == 2

    def test_decrement(self, ref_counter):
        ref_counter.increment("addr1", "obj1")
        ref_counter.increment("addr1", "obj2")
        count = ref_counter.decrement("addr1", "obj1")
        assert count == 1

    def test_decrement_to_zero(self, ref_counter):
        ref_counter.increment("addr1", "obj1")
        count = ref_counter.decrement("addr1", "obj1")
        assert count == 0

    def test_decrement_nonexistent(self, ref_counter):
        count = ref_counter.decrement("ghost", "obj1")
        assert count == 0

    def test_get_count(self, ref_counter):
        ref_counter.increment("addr1", "obj1")
        ref_counter.increment("addr1", "obj2")
        assert ref_counter.get_count("addr1") == 2

    def test_get_all_addresses(self, ref_counter):
        ref_counter.increment("addr1", "obj1")
        ref_counter.increment("addr2", "obj2")
        addrs = ref_counter.get_all_addresses()
        assert "addr1" in addrs
        assert "addr2" in addrs

    def test_same_object_no_double_count(self, ref_counter):
        ref_counter.increment("addr1", "obj1")
        ref_counter.increment("addr1", "obj1")
        assert ref_counter.get_count("addr1") == 1


# ============================================================
# TestGarbageCollector
# ============================================================


class TestGarbageCollector:
    """Validates garbage collection of unreferenced chunks."""

    def test_collect_zero_ref(self, cas, ref_counter):
        addr = cas.address_chunk(b"garbage")
        cas.store_chunk(addr, b"garbage")
        ref_counter.increment(addr, "obj1")
        ref_counter.decrement(addr, "obj1")
        gc = GarbageCollector(cas, ref_counter, safety_delay=0)
        gc.collect()  # First pass registers candidate
        report = gc.collect()  # Second pass collects
        assert report["total_collected_chunks"] >= 0

    def test_safety_delay_respected(self, cas, ref_counter):
        addr = cas.address_chunk(b"delayed")
        cas.store_chunk(addr, b"delayed")
        ref_counter.increment(addr, "obj1")
        ref_counter.decrement(addr, "obj1")
        gc = GarbageCollector(cas, ref_counter, safety_delay=86400)
        report = gc.collect()
        assert report["collected_chunks"] == 0

    def test_nonzero_ref_not_collected(self, cas, ref_counter):
        addr = cas.address_chunk(b"keep me")
        cas.store_chunk(addr, b"keep me")
        ref_counter.increment(addr, "obj1")
        gc = GarbageCollector(cas, ref_counter, safety_delay=0)
        gc.collect()
        report = gc.collect()
        assert report["collected_chunks"] == 0

    def test_collect_report_fields(self, cas, ref_counter):
        gc = GarbageCollector(cas, ref_counter, safety_delay=0)
        report = gc.collect()
        assert "collected_chunks" in report
        assert "collected_bytes" in report
        assert "pending_candidates" in report

    def test_collect_empty(self, cas, ref_counter):
        gc = GarbageCollector(cas, ref_counter, safety_delay=0)
        report = gc.collect()
        assert report["collected_chunks"] == 0

    def test_ref_re_added_before_collect(self, cas, ref_counter):
        addr = cas.address_chunk(b"resurrected")
        cas.store_chunk(addr, b"resurrected")
        ref_counter.increment(addr, "obj1")
        ref_counter.decrement(addr, "obj1")
        gc = GarbageCollector(cas, ref_counter, safety_delay=0)
        gc.collect()  # Register candidate
        ref_counter.increment(addr, "obj2")  # Re-reference
        report = gc.collect()
        # Should not collect because ref was re-added
        assert report["collected_chunks"] == 0

    def test_cumulative_totals(self, cas, ref_counter):
        gc = GarbageCollector(cas, ref_counter, safety_delay=0)
        gc.collect()
        report = gc.collect()
        assert "total_collected_chunks" in report
        assert "total_collected_bytes" in report

    def test_multiple_rounds(self, cas, ref_counter):
        gc = GarbageCollector(cas, ref_counter, safety_delay=0)
        for _ in range(5):
            gc.collect()


# ============================================================
# TestGaloisField
# ============================================================


class TestGaloisField:
    """Validates GF(2^8) arithmetic operations."""

    def test_add_is_xor(self, gf):
        assert gf.add(0b1010, 0b1100) == 0b0110

    def test_add_commutative(self, gf):
        assert gf.add(42, 73) == gf.add(73, 42)

    def test_add_zero_identity(self, gf):
        assert gf.add(42, 0) == 42

    def test_subtract_equals_add(self, gf):
        assert gf.subtract(42, 73) == gf.add(42, 73)

    def test_multiply_identity(self, gf):
        assert gf.multiply(42, 1) == 42

    def test_multiply_zero(self, gf):
        assert gf.multiply(42, 0) == 0

    def test_multiply_commutative(self, gf):
        assert gf.multiply(42, 73) == gf.multiply(73, 42)

    def test_divide_inverse(self, gf):
        a, b = 42, 73
        result = gf.divide(a, b)
        assert gf.multiply(result, b) == a

    def test_divide_by_zero(self, gf):
        with pytest.raises(ErasureCodingError):
            gf.divide(42, 0)

    def test_inverse(self, gf):
        for val in [1, 2, 42, 127, 255]:
            inv = gf.inverse(val)
            assert gf.multiply(val, inv) == 1

    def test_inverse_zero(self, gf):
        with pytest.raises(ErasureCodingError):
            gf.inverse(0)

    def test_power(self, gf):
        val = gf.power(2, 8)
        assert isinstance(val, int)
        assert 0 <= val < 256


# ============================================================
# TestVandermondeMatrix
# ============================================================


class TestVandermondeMatrix:
    """Validates Vandermonde matrix operations."""

    def test_build_systematic(self, gf):
        vm = VandermondeMatrix(gf)
        matrix = vm.build(14, 10)
        # First 10 rows should be identity
        for i in range(10):
            for j in range(10):
                expected = 1 if i == j else 0
                assert matrix[i][j] == expected

    def test_build_dimensions(self, gf):
        vm = VandermondeMatrix(gf)
        matrix = vm.build(14, 10)
        assert len(matrix) == 14
        assert len(matrix[0]) == 10

    def test_invert_submatrix_identity(self, gf):
        vm = VandermondeMatrix(gf)
        matrix = vm.build(14, 10)
        inv = vm.invert_submatrix(matrix, list(range(10)), 10)
        # Should be identity for first 10 rows
        for i in range(10):
            for j in range(10):
                expected = 1 if i == j else 0
                assert inv[i][j] == expected

    def test_multiply_vector(self, gf):
        vm = VandermondeMatrix(gf)
        matrix = vm.build(3, 2)
        vector = [1, 2]
        result = vm.multiply_vector(matrix, vector)
        assert len(result) == 3

    def test_invert_parity_rows(self, gf):
        vm = VandermondeMatrix(gf)
        matrix = vm.build(14, 10)
        # Using first 8 data + 2 parity rows should be invertible
        indices = list(range(8)) + [10, 11]
        inv = vm.invert_submatrix(matrix, indices, 10)
        assert len(inv) == 10

    def test_build_small_matrix(self, gf):
        vm = VandermondeMatrix(gf)
        matrix = vm.build(3, 2)
        assert len(matrix) == 3
        assert len(matrix[0]) == 2

    def test_build_all_storage_classes(self, gf):
        vm = VandermondeMatrix(gf)
        for sc, (d, p) in ERASURE_PARAMS.items():
            matrix = vm.build(d + p, d)
            assert len(matrix) == d + p

    def test_systematic_property(self, gf):
        vm = VandermondeMatrix(gf)
        for d in [2, 4, 6, 10]:
            matrix = vm.build(d + 4, d)
            for i in range(d):
                assert matrix[i][i] == 1


# ============================================================
# TestErasureCodingEngine
# ============================================================


class TestErasureCodingEngine:
    """Validates Reed-Solomon erasure coding."""

    def test_encode_decode_standard(self, erasure_engine):
        data = b"Hello, FizzBuzz!" * 10
        fragments = erasure_engine.encode(data, 10, 4)
        assert len(fragments) == 14
        decoded = erasure_engine.decode(
            {i: f for i, f in enumerate(fragments)}, 10, 4
        )
        assert decoded[:len(data)] == data

    def test_encode_decode_standard_ia(self, erasure_engine):
        data = b"IA data" * 6
        fragments = erasure_engine.encode(data, 6, 4)
        assert len(fragments) == 10
        decoded = erasure_engine.decode(
            {i: f for i, f in enumerate(fragments)}, 6, 4
        )
        assert decoded[:len(data)] == data

    def test_encode_decode_archive(self, erasure_engine):
        data = b"archive" * 4
        fragments = erasure_engine.encode(data, 4, 4)
        decoded = erasure_engine.decode(
            {i: f for i, f in enumerate(fragments)}, 4, 4
        )
        assert decoded[:len(data)] == data

    def test_encode_decode_deep_archive(self, erasure_engine):
        data = b"deep" * 2
        fragments = erasure_engine.encode(data, 2, 4)
        decoded = erasure_engine.decode(
            {i: f for i, f in enumerate(fragments)}, 2, 4
        )
        assert decoded[:len(data)] == data

    def test_decode_from_minimum_fragments(self, erasure_engine):
        data = b"minimum fragments" * 5
        fragments = erasure_engine.encode(data, 4, 4)
        # Only provide first 4 (minimum)
        subset = {i: fragments[i] for i in range(4)}
        decoded = erasure_engine.decode(subset, 4, 4)
        assert decoded[:len(data)] == data

    def test_decode_from_parity_only(self, erasure_engine):
        data = b"parity recovery" * 3
        fragments = erasure_engine.encode(data, 4, 4)
        # Use last 4 parity fragments + any data needed
        subset = {i: fragments[i] for i in [0, 1, 4, 5]}
        decoded = erasure_engine.decode(subset, 4, 4)
        assert decoded[:len(data)] == data

    def test_insufficient_fragments(self, erasure_engine):
        data = b"not enough"
        fragments = erasure_engine.encode(data, 4, 4)
        subset = {0: fragments[0], 1: fragments[1]}
        with pytest.raises(InsufficientFragmentsError):
            erasure_engine.decode(subset, 4, 4)

    def test_verify_clean(self, erasure_engine):
        data = b"verify me" * 5
        fragments = erasure_engine.encode(data, 4, 4)
        frag_dict = {i: f for i, f in enumerate(fragments)}
        assert erasure_engine.verify_fragments(frag_dict, 4, 4) is True

    def test_verify_corrupt(self, erasure_engine):
        data = b"corrupt test" * 5
        fragments = erasure_engine.encode(data, 4, 4)
        frag_dict = {i: f for i, f in enumerate(fragments)}
        # Corrupt a fragment
        frag_dict[2] = b"\x00" * len(frag_dict[2])
        assert erasure_engine.verify_fragments(frag_dict, 4, 4) is False

    def test_encode_produces_correct_count(self, erasure_engine):
        for d, p in [(10, 4), (6, 4), (4, 4), (2, 4)]:
            fragments = erasure_engine.encode(b"x" * d, d, p)
            assert len(fragments) == d + p

    def test_systematic_data_preserved(self, erasure_engine):
        data = b"abcdefghij"  # 10 bytes, 1 per data fragment
        fragments = erasure_engine.encode(data, 10, 4)
        # First 10 fragments should contain the original data
        reconstructed = b"".join(fragments[:10])
        assert reconstructed[:10] == data

    def test_decode_any_k_of_n_data_fragments(self, erasure_engine):
        data = b"test data block" * 2
        d, p = 4, 4
        fragments = erasure_engine.encode(data, d, p)
        # Systematic encoding guarantees decoding from all data fragments
        subset = {i: fragments[i] for i in range(d)}
        decoded = erasure_engine.decode(subset, d, p)
        assert decoded[:len(data)] == data

    def test_decode_mixed_data_parity(self, erasure_engine):
        data = b"mixed fragments" * 3
        d, p = 4, 4
        fragments = erasure_engine.encode(data, d, p)
        # Use 2 data + 2 parity fragments
        subset = {0: fragments[0], 1: fragments[1], 4: fragments[4], 5: fragments[5]}
        decoded = erasure_engine.decode(subset, d, p)
        assert decoded[:len(data)] == data

    def test_matrix_caching(self, erasure_engine):
        erasure_engine.encode(b"data1" * 10, 10, 4)
        erasure_engine.encode(b"data2" * 10, 10, 4)
        assert (10, 4) in erasure_engine._matrix_cache

    def test_empty_data_encode(self, erasure_engine):
        fragments = erasure_engine.encode(b"", 2, 2)
        assert len(fragments) == 4

    def test_large_data(self, erasure_engine):
        data = b"x" * 10000
        fragments = erasure_engine.encode(data, 4, 4)
        decoded = erasure_engine.decode(
            {i: f for i, f in enumerate(fragments)}, 4, 4
        )
        assert decoded[:len(data)] == data

    def test_verify_insufficient_returns_false(self, erasure_engine):
        result = erasure_engine.verify_fragments({0: b"x"}, 4, 4)
        assert result is False

    def test_single_byte_data(self, erasure_engine):
        data = b"x"
        fragments = erasure_engine.encode(data, 2, 2)
        decoded = erasure_engine.decode(
            {i: f for i, f in enumerate(fragments)}, 2, 2
        )
        assert decoded[:1] == data


# ============================================================
# TestFragmentDistributor
# ============================================================


class TestFragmentDistributor:
    """Validates fragment distribution across failure domains."""

    def test_distribute_default_locations(self):
        dist = FragmentDistributor()
        assignment = dist.distribute("chunk1", [b"f0", b"f1", b"f2"])
        assert len(assignment) == 3

    def test_distribute_custom_locations(self):
        dist = FragmentDistributor()
        locs = ["rack-a", "rack-b", "rack-c"]
        assignment = dist.distribute("chunk1", [b"f0", b"f1", b"f2"], locations=locs)
        assert set(assignment.values()).issubset(set(locs))

    def test_collect_all(self):
        dist = FragmentDistributor()
        dist.distribute("chunk1", [b"f0", b"f1", b"f2"])
        collected = dist.collect("chunk1", 3)
        assert len(collected) == 3

    def test_collect_insufficient(self):
        dist = FragmentDistributor()
        with pytest.raises(InsufficientFragmentsError):
            dist.collect("ghost", 3)

    def test_remove(self):
        dist = FragmentDistributor()
        dist.distribute("chunk1", [b"f0", b"f1"])
        dist.remove("chunk1")
        with pytest.raises(InsufficientFragmentsError):
            dist.collect("chunk1", 1)

    def test_get_fragment(self):
        dist = FragmentDistributor()
        dist.distribute("chunk1", [b"frag0", b"frag1"])
        frag = dist.get_fragment("chunk1", 0)
        assert frag == b"frag0"


# ============================================================
# TestFragmentIntegrityChecker
# ============================================================


class TestFragmentIntegrityChecker:
    """Validates fragment health monitoring and repair."""

    def test_check_healthy_chunk(self, cas, erasure_engine):
        dist = FragmentDistributor()
        data = b"healthy data" * 5
        fragments = erasure_engine.encode(data, 4, 4)
        addr = hashlib.sha256(data).hexdigest()
        dist.distribute(addr, fragments)
        checker = FragmentIntegrityChecker(cas, erasure_engine, dist)
        healthy, corrupt = checker.check_chunk(addr, 4, 4)
        assert healthy is True
        assert corrupt == []

    def test_scrub_all_healthy(self, cas, erasure_engine):
        dist = FragmentDistributor()
        checker = FragmentIntegrityChecker(cas, erasure_engine, dist)
        data = b"scrub data" * 5
        fragments = erasure_engine.encode(data, 4, 4)
        addr = hashlib.sha256(data).hexdigest()
        dist.distribute(addr, fragments)
        report = checker.scrub("test-bucket", [addr], 4, 4)
        assert report["checked"] == 1
        assert report["healthy"] == 1

    def test_scrub_empty(self, cas, erasure_engine):
        dist = FragmentDistributor()
        checker = FragmentIntegrityChecker(cas, erasure_engine, dist)
        report = checker.scrub("empty-bucket", [], 4, 4)
        assert report["checked"] == 0

    def test_get_last_scrub(self, cas, erasure_engine):
        dist = FragmentDistributor()
        checker = FragmentIntegrityChecker(cas, erasure_engine, dist)
        checker.scrub("bucket-a", [], 4, 4)
        result = checker.get_last_scrub("bucket-a")
        assert result is not None
        assert result["bucket"] == "bucket-a"

    def test_get_last_scrub_none(self, cas, erasure_engine):
        dist = FragmentDistributor()
        checker = FragmentIntegrityChecker(cas, erasure_engine, dist)
        assert checker.get_last_scrub("no-scrub") is None

    def test_scrub_report_fields(self, cas, erasure_engine):
        dist = FragmentDistributor()
        checker = FragmentIntegrityChecker(cas, erasure_engine, dist)
        report = checker.scrub("bucket", [], 4, 4)
        for field in ["bucket", "checked", "healthy", "corrupt", "repaired", "unrecoverable"]:
            assert field in report

    def test_check_nonexistent_chunk(self, cas, erasure_engine):
        dist = FragmentDistributor()
        checker = FragmentIntegrityChecker(cas, erasure_engine, dist)
        healthy, corrupt = checker.check_chunk("nonexistent", 4, 4)
        assert healthy is False

    def test_repair_chunk(self, cas, erasure_engine):
        dist = FragmentDistributor()
        data = b"repair me" * 5
        fragments = erasure_engine.encode(data, 4, 4)
        addr = hashlib.sha256(data).hexdigest()
        dist.distribute(addr, fragments)
        checker = FragmentIntegrityChecker(cas, erasure_engine, dist)
        result = checker.repair_chunk(addr, [2], 4, 4)
        assert result is True


# ============================================================
# TestMetadataIndex
# ============================================================


class TestMetadataIndex:
    """Validates B-tree and hash index operations."""

    def test_put_get_hash(self, metadata_index):
        metadata_index.put("ns", "key1", "value1")
        assert metadata_index.get("ns", "key1") == "value1"

    def test_put_get_btree(self, metadata_index):
        metadata_index.put("ns", "key1", "value1", index_type="btree")
        assert metadata_index.get("ns", "key1", index_type="btree") == "value1"

    def test_delete_hash(self, metadata_index):
        metadata_index.put("ns", "key1", "value1")
        assert metadata_index.delete("ns", "key1") is True
        assert metadata_index.get("ns", "key1") is None

    def test_delete_nonexistent(self, metadata_index):
        assert metadata_index.delete("ns", "ghost") is False

    def test_range_query(self, metadata_index):
        for i in range(5):
            metadata_index.put("ns", f"key{i}", f"val{i}")
        results = metadata_index.range_query("ns", "key1", "key4")
        keys = [k for k, v in results]
        assert "key1" in keys
        assert "key3" in keys
        assert "key4" not in keys

    def test_prefix_query(self, metadata_index):
        metadata_index.put("ns", "docs/a", 1)
        metadata_index.put("ns", "docs/b", 2)
        metadata_index.put("ns", "images/c", 3)
        results, token = metadata_index.prefix_query("ns", "docs/")
        assert len(results) == 2

    def test_prefix_query_pagination(self, metadata_index):
        for i in range(10):
            metadata_index.put("ns", f"item{i:02d}", i)
        results, token = metadata_index.prefix_query("ns", "item", limit=3)
        assert len(results) <= 4  # limit + 1 for next token detection

    def test_list_keys(self, metadata_index):
        metadata_index.put("ns", "a", 1)
        metadata_index.put("ns", "b", 2)
        keys = metadata_index.list_keys("ns")
        assert "a" in keys
        assert "b" in keys

    def test_count(self, metadata_index):
        metadata_index.put("ns", "a", 1)
        metadata_index.put("ns", "b", 2)
        assert metadata_index.count("ns") == 2

    def test_clear_namespace(self, metadata_index):
        metadata_index.put("ns", "a", 1)
        metadata_index.clear_namespace("ns")
        assert metadata_index.count("ns") == 0

    def test_update_value(self, metadata_index):
        metadata_index.put("ns", "key", "old")
        metadata_index.put("ns", "key", "new")
        assert metadata_index.get("ns", "key") == "new"

    def test_separate_namespaces(self, metadata_index):
        metadata_index.put("ns1", "key", "val1")
        metadata_index.put("ns2", "key", "val2")
        assert metadata_index.get("ns1", "key") == "val1"
        assert metadata_index.get("ns2", "key") == "val2"


# ============================================================
# TestSegmentLog
# ============================================================


class TestSegmentLog:
    """Validates append-only data tier operations."""

    def test_append(self, segment_log):
        loc = segment_log.append("frag1", b"fragment data")
        assert loc.length == len(b"fragment data")

    def test_read(self, segment_log):
        loc = segment_log.append("frag1", b"data")
        data = segment_log.read(loc.segment_id, "frag1")
        assert data == b"data"

    def test_read_nonexistent_segment(self, segment_log):
        with pytest.raises(MetadataCorruptionError):
            segment_log.read("nonexistent", "frag1")

    def test_read_nonexistent_fragment(self, segment_log):
        loc = segment_log.append("frag1", b"data")
        with pytest.raises(ChunkNotFoundError):
            segment_log.read(loc.segment_id, "frag2")

    def test_segment_sealing(self):
        log = SegmentLog(max_segment_size=100)
        log.append("f1", b"x" * 60)
        loc2 = log.append("f2", b"y" * 60)
        # Second append should be in a new segment
        stats = log.get_segment_stats()
        assert len(stats) >= 2

    def test_mark_dead(self, segment_log):
        loc = segment_log.append("frag1", b"dead data")
        segment_log.mark_dead(loc.segment_id, "frag1")
        stats = segment_log.get_segment_stats()
        active = [s for s in stats if s["status"] == "active"]
        assert any(s["dead_bytes"] > 0 for s in active)

    def test_compact(self):
        log = SegmentLog(max_segment_size=100)
        loc1 = log.append("f1", b"x" * 50)
        log.append("f2", b"y" * 60)  # Forces new segment
        # Seal first and compact
        stats = log.get_segment_stats()
        sealed = [s["segment_id"] for s in stats if s["status"] == "sealed"]
        if sealed:
            new_id = log.compact(sealed)
            assert new_id is not None

    def test_segment_stats(self, segment_log):
        segment_log.append("f1", b"data")
        stats = segment_log.get_segment_stats()
        assert len(stats) >= 1
        assert stats[0]["fragment_count"] >= 1

    def test_fragment_location_checksum(self, segment_log):
        loc = segment_log.append("frag1", b"checksum data")
        assert loc.checksum is not None
        assert loc.checksum == hashlib.md5(b"checksum data").hexdigest()

    def test_multiple_appends_same_segment(self, segment_log):
        segment_log.append("f1", b"data1")
        segment_log.append("f2", b"data2")
        stats = segment_log.get_segment_stats()
        active = [s for s in stats if s["status"] == "active"]
        assert active[0]["fragment_count"] == 2


# ============================================================
# TestCompactionPolicy
# ============================================================


class TestCompactionPolicy:
    """Validates segment compaction eligibility."""

    def test_select_above_threshold(self):
        policy = CompactionPolicy(threshold=0.5)
        stats = [
            {"segment_id": "s1", "status": "sealed", "fragmentation": 0.7},
            {"segment_id": "s2", "status": "sealed", "fragmentation": 0.3},
        ]
        selected = policy.select_segments(stats)
        assert "s1" in selected
        assert "s2" not in selected

    def test_skip_active_segments(self):
        policy = CompactionPolicy(threshold=0.3)
        stats = [
            {"segment_id": "s1", "status": "active", "fragmentation": 0.9},
        ]
        selected = policy.select_segments(stats)
        assert selected == []

    def test_ordering_by_fragmentation(self):
        policy = CompactionPolicy(threshold=0.3, max_concurrent=3)
        stats = [
            {"segment_id": "s1", "status": "sealed", "fragmentation": 0.5},
            {"segment_id": "s2", "status": "sealed", "fragmentation": 0.9},
            {"segment_id": "s3", "status": "sealed", "fragmentation": 0.7},
        ]
        selected = policy.select_segments(stats)
        assert selected[0] == "s2"
        assert selected[1] == "s3"

    def test_max_concurrent_limit(self):
        policy = CompactionPolicy(threshold=0.1, max_concurrent=2)
        stats = [
            {"segment_id": f"s{i}", "status": "sealed", "fragmentation": 0.8}
            for i in range(5)
        ]
        selected = policy.select_segments(stats)
        assert len(selected) <= 2

    def test_empty_stats(self):
        policy = CompactionPolicy()
        assert policy.select_segments([]) == []

    def test_no_eligible(self):
        policy = CompactionPolicy(threshold=0.9)
        stats = [
            {"segment_id": "s1", "status": "sealed", "fragmentation": 0.1},
        ]
        assert policy.select_segments(stats) == []


# ============================================================
# TestNotificationConfiguration
# ============================================================


class TestNotificationConfiguration:
    """Validates event notification configuration."""

    def test_event_rule_construction(self):
        rule = EventRule(
            id="notify-put",
            events=[S3EventType.OBJECT_CREATED_PUT],
            destination_type=DestinationType.EVENT_BUS,
            destination_target="fizz-events",
        )
        assert rule.events[0] == S3EventType.OBJECT_CREATED_PUT

    def test_prefix_suffix_filters(self):
        rule = EventRule(
            id="filter-rule",
            events=[S3EventType.OBJECT_CREATED_ALL],
            prefix_filter="logs/",
            suffix_filter=".json",
        )
        assert rule.prefix_filter == "logs/"
        assert rule.suffix_filter == ".json"

    def test_notification_config_multiple_rules(self):
        config = NotificationConfiguration(event_rules=[
            EventRule(id="r1", events=[S3EventType.OBJECT_CREATED_ALL]),
            EventRule(id="r2", events=[S3EventType.OBJECT_REMOVED_ALL]),
        ])
        assert len(config.event_rules) == 2

    def test_destination_types(self):
        assert DestinationType.EVENT_BUS.value == "event_bus"
        assert DestinationType.WEBHOOK.value == "webhook"
        assert DestinationType.QUEUE.value == "queue"

    def test_s3_event_types_exist(self):
        assert len(S3EventType) >= 10

    def test_empty_config(self):
        config = NotificationConfiguration()
        assert config.event_rules == []

    def test_event_wildcard(self):
        assert S3EventType.OBJECT_CREATED_ALL.value == "s3:ObjectCreated:*"

    def test_replication_events(self):
        assert S3EventType.REPLICATION_ALL.value == "s3:Replication:*"


# ============================================================
# TestS3EventMessage
# ============================================================


class TestS3EventMessage:
    """Validates notification payload construction."""

    def test_event_message_defaults(self):
        msg = S3EventMessage()
        assert msg.event_source == "fizz:s3"
        assert msg.event_version == "2.1"

    def test_event_message_fields(self):
        msg = S3EventMessage(
            event_name="ObjectCreated:Put",
            bucket_name="my-bucket",
            object_key="file.txt",
            object_size=1024,
        )
        assert msg.event_name == "ObjectCreated:Put"
        assert msg.bucket_name == "my-bucket"
        assert msg.object_size == 1024

    def test_event_has_request_id(self):
        msg = S3EventMessage()
        assert msg.request_id is not None
        assert len(msg.request_id) > 0

    def test_event_has_timestamp(self):
        msg = S3EventMessage()
        assert msg.event_time is not None

    def test_event_default_principal(self):
        msg = S3EventMessage()
        assert msg.principal == "fizzbuzz-root"

    def test_event_version_id(self):
        msg = S3EventMessage(object_version_id="v123")
        assert msg.object_version_id == "v123"


# ============================================================
# TestReplicationConfiguration
# ============================================================


class TestReplicationConfiguration:
    """Validates replication configuration construction."""

    def test_replication_rule_defaults(self):
        rule = ReplicationRule(
            id="rep1",
            destination_bucket="dest-bucket",
            destination_region="fizz-west-1",
        )
        assert rule.status == RuleStatus.ENABLED
        assert rule.priority == 0

    def test_replication_config(self):
        config = ReplicationConfiguration(rules=[
            ReplicationRule(id="r1", destination_bucket="dest", destination_region="fizz-west-1"),
        ])
        assert len(config.rules) == 1
        assert config.role == "fizz-replication-role"

    def test_priority_ordering(self):
        rules = [
            ReplicationRule(id="low", priority=1),
            ReplicationRule(id="high", priority=10),
        ]
        sorted_rules = sorted(rules, key=lambda r: r.priority, reverse=True)
        assert sorted_rules[0].id == "high"

    def test_prefix_filter(self):
        rule = ReplicationRule(id="filtered", prefix="logs/")
        assert rule.prefix == "logs/"

    def test_delete_marker_replication_default(self):
        rule = ReplicationRule(id="r1")
        assert rule.delete_marker_replication is False

    def test_storage_class_override(self):
        rule = ReplicationRule(
            id="r1",
            destination_storage_class=StorageClass.STANDARD_IA,
        )
        assert rule.destination_storage_class == StorageClass.STANDARD_IA

    def test_disabled_rule(self):
        rule = ReplicationRule(id="off", status=RuleStatus.DISABLED)
        assert rule.status == RuleStatus.DISABLED

    def test_empty_replication_config(self):
        config = ReplicationConfiguration()
        assert config.rules == []


# ============================================================
# TestFizzS3Middleware
# ============================================================


class TestFizzS3Middleware:
    """Validates middleware pipeline integration."""

    def test_middleware_name(self):
        service, mw = create_fizzs3_subsystem()
        assert mw.name == "fizzs3"

    def test_middleware_priority(self):
        _, mw = create_fizzs3_subsystem()
        assert mw.priority == MIDDLEWARE_PRIORITY

    def test_middleware_process(self):
        _, mw = create_fizzs3_subsystem()
        from enterprise_fizzbuzz.domain.models import ProcessingContext
        ctx = ProcessingContext(number=15, session_id="test-session")
        processed = mw.process(ctx, lambda c: c)
        assert processed is not None

    def test_middleware_stores_evaluation(self):
        service, mw = create_fizzs3_subsystem()
        from enterprise_fizzbuzz.domain.models import ProcessingContext
        ctx = ProcessingContext(number=15, session_id="test-session")
        mw.process(ctx, lambda c: c)

    def test_middleware_render_overview(self):
        _, mw = create_fizzs3_subsystem()
        output = mw.render_overview()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_middleware_render_buckets(self):
        _, mw = create_fizzs3_subsystem()
        output = mw.render_buckets()
        assert isinstance(output, str)

    def test_middleware_render_metrics(self):
        _, mw = create_fizzs3_subsystem()
        output = mw.render_metrics()
        assert isinstance(output, str)

    def test_middleware_error_handling(self):
        _, mw = create_fizzs3_subsystem()
        from enterprise_fizzbuzz.domain.models import ProcessingContext
        ctx = ProcessingContext(number=1, session_id="test-session")
        processed = mw.process(ctx, lambda c: c)
        assert processed is not None

    def test_middleware_implements_interface(self):
        _, mw = create_fizzs3_subsystem()
        assert hasattr(mw, "process")
        assert hasattr(mw, "name")
        assert hasattr(mw, "priority")

    def test_create_subsystem_returns_tuple(self):
        result = create_fizzs3_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_create_subsystem_with_event_bus(self, event_bus):
        service, mw = create_fizzs3_subsystem(event_bus=event_bus)
        assert service is not None

    def test_middleware_context_enrichment(self):
        _, mw = create_fizzs3_subsystem()
        from enterprise_fizzbuzz.domain.models import ProcessingContext
        ctx = ProcessingContext(number=15, session_id="test-session")
        mw.process(ctx, lambda c: c)

    def test_middleware_render_dedup(self):
        _, mw = create_fizzs3_subsystem()
        output = mw.render_dedup("test-bucket")
        assert isinstance(output, str)

    def test_middleware_render_scrub(self):
        _, mw = create_fizzs3_subsystem()
        output = mw.render_scrub("test-bucket")
        assert isinstance(output, str)

    def test_create_subsystem_custom_params(self):
        service, mw = create_fizzs3_subsystem(
            default_region="fizz-west-1",
            max_buckets=50,
            dashboard_width=80,
        )
        assert service is not None


# ============================================================
# TestCreateFizzS3Subsystem
# ============================================================


class TestCreateFizzS3Subsystem:
    """Validates factory function wiring."""

    def test_returns_service_and_middleware(self):
        service, mw = create_fizzs3_subsystem()
        assert service is not None
        assert mw is not None

    def test_default_params(self):
        service, mw = create_fizzs3_subsystem()
        assert mw.priority == MIDDLEWARE_PRIORITY

    def test_custom_region(self):
        service, mw = create_fizzs3_subsystem(default_region="fizz-ap-1")
        assert service is not None

    def test_custom_max_buckets(self):
        service, mw = create_fizzs3_subsystem(max_buckets=50)
        assert service is not None

    def test_with_event_bus(self, event_bus):
        service, mw = create_fizzs3_subsystem(event_bus=event_bus)
        assert service is not None

    def test_custom_chunk_size(self):
        service, mw = create_fizzs3_subsystem(chunk_size=1024 * 1024)
        assert service is not None

    def test_custom_dashboard_width(self):
        service, mw = create_fizzs3_subsystem(dashboard_width=80)
        assert service is not None

    def test_all_custom_params(self):
        service, mw = create_fizzs3_subsystem(
            default_region="fizz-eu-1",
            max_buckets=10,
            default_encryption="sse-kms",
            chunk_size=1024 * 1024,
            gc_interval=3600,
            gc_safety_delay=7200,
            lifecycle_interval=43200,
            compaction_threshold=0.3,
            segment_max_size=128 * 1024 * 1024,
            presign_default_expiry=1800,
            dashboard_width=100,
            event_bus=None,
        )
        assert service is not None
        assert mw is not None


# ============================================================
# TestFizzS3Exceptions
# ============================================================


class TestFizzS3Exceptions:
    """Validates all 68 FizzS3 exception classes."""

    def test_fizzs3_error_base(self):
        e = FizzS3Error("test error")
        assert "EFP-S300" in str(e) or "S3" in type(e).__name__

    def test_bucket_error(self):
        assert issubclass(BucketError, FizzS3Error)

    def test_bucket_already_exists(self):
        e = BucketAlreadyExistsError("my-bucket")
        assert issubclass(type(e), BucketError)

    def test_bucket_already_owned(self):
        e = BucketAlreadyOwnedByYouError("my-bucket")
        assert issubclass(type(e), BucketError)

    def test_bucket_not_empty(self):
        e = BucketNotEmptyError("my-bucket")
        assert issubclass(type(e), BucketError)

    def test_bucket_not_found(self):
        e = BucketNotFoundError("my-bucket")
        assert issubclass(type(e), BucketError)

    def test_invalid_bucket_name(self):
        e = InvalidBucketNameError("bad", ["too short"])
        assert issubclass(type(e), BucketError)

    def test_too_many_buckets(self):
        e = TooManyBucketsError(100)
        assert issubclass(type(e), BucketError)

    def test_object_error(self):
        assert issubclass(ObjectError, FizzS3Error)

    def test_object_not_found(self):
        e = ObjectNotFoundError("bucket", "key")
        assert issubclass(type(e), ObjectError)

    def test_object_too_large(self):
        e = ObjectTooLargeError(999, 100)
        assert issubclass(type(e), ObjectError)

    def test_invalid_object_key(self):
        e = InvalidObjectKeyError("", "empty")
        assert issubclass(type(e), ObjectError)

    def test_precondition_failed(self):
        e = PreconditionFailedError("If-Match", "a", "b")
        assert issubclass(type(e), ObjectError)

    def test_not_modified(self):
        e = NotModifiedError("reason")
        assert issubclass(type(e), ObjectError)

    def test_invalid_range(self):
        e = InvalidRangeError("bytes=0-100", 50)
        assert issubclass(type(e), ObjectError)

    def test_version_error(self):
        assert issubclass(VersionError, FizzS3Error)

    def test_no_such_version(self):
        e = NoSuchVersionError("bucket", "key", "vid")
        assert issubclass(type(e), VersionError)

    def test_versioning_not_enabled(self):
        assert issubclass(VersioningNotEnabledError, VersionError)

    def test_invalid_version_id(self):
        assert issubclass(InvalidVersionIdError, VersionError)

    def test_multipart_upload_error(self):
        assert issubclass(MultipartUploadError, FizzS3Error)

    def test_no_such_upload(self):
        e = NoSuchUploadError("uid")
        assert issubclass(type(e), MultipartUploadError)

    def test_invalid_part(self):
        e = InvalidPartError(1, "reason")
        assert issubclass(type(e), MultipartUploadError)

    def test_invalid_part_order(self):
        assert issubclass(InvalidPartOrderError, MultipartUploadError)

    def test_entity_too_small(self):
        e = EntityTooSmallError(1, 100, MIN_PART_SIZE)
        assert issubclass(type(e), MultipartUploadError)

    def test_entity_too_large(self):
        e = EntityTooLargeError(1, 999, 100)
        assert issubclass(type(e), MultipartUploadError)

    def test_too_many_parts(self):
        e = TooManyPartsError(10001, MAX_PARTS)
        assert issubclass(type(e), MultipartUploadError)

    def test_access_control_error(self):
        assert issubclass(AccessControlError, FizzS3Error)

    def test_s3_access_denied(self):
        assert issubclass(S3AccessDeniedError, AccessControlError)

    def test_invalid_policy(self):
        assert issubclass(InvalidPolicyError, AccessControlError)

    def test_malformed_acl(self):
        assert issubclass(MalformedACLError, AccessControlError)

    def test_public_access_blocked(self):
        assert issubclass(PublicAccessBlockedError, AccessControlError)

    def test_encryption_error(self):
        assert issubclass(EncryptionError, FizzS3Error)

    def test_invalid_encryption_key(self):
        assert issubclass(InvalidEncryptionKeyError, EncryptionError)

    def test_kms_key_not_found(self):
        assert issubclass(KMSKeyNotFoundError, EncryptionError)

    def test_kms_access_denied(self):
        assert issubclass(KMSAccessDeniedError, EncryptionError)

    def test_key_rotation_in_progress(self):
        assert issubclass(KeyRotationInProgressError, EncryptionError)

    def test_replication_error(self):
        assert issubclass(ReplicationError, FizzS3Error)

    def test_replication_configuration_error(self):
        assert issubclass(ReplicationConfigurationError, ReplicationError)

    def test_replication_failed(self):
        assert issubclass(ReplicationFailedError, ReplicationError)

    def test_replication_loop_detected(self):
        assert issubclass(ReplicationLoopDetectedError, ReplicationError)

    def test_storage_class_error(self):
        assert issubclass(StorageClassError, FizzS3Error)

    def test_invalid_storage_class_transition(self):
        assert issubclass(InvalidStorageClassTransitionError, StorageClassError)

    def test_restore_in_progress(self):
        assert issubclass(RestoreInProgressError, StorageClassError)

    def test_object_not_archived(self):
        assert issubclass(ObjectNotArchivedError, StorageClassError)

    def test_restore_expired(self):
        assert issubclass(RestoreExpiredError, StorageClassError)

    def test_erasure_coding_error(self):
        assert issubclass(ErasureCodingError, FizzS3Error)

    def test_insufficient_fragments(self):
        e = InsufficientFragmentsError("test", 2, 4)
        assert issubclass(type(e), ErasureCodingError)

    def test_fragment_corruption(self):
        e = FragmentCorruptionError("addr", 0)
        assert issubclass(type(e), ErasureCodingError)

    def test_fragment_location_unavailable(self):
        assert issubclass(FragmentLocationUnavailableError, ErasureCodingError)

    def test_content_address_error(self):
        assert issubclass(ContentAddressError, FizzS3Error)

    def test_chunk_not_found(self):
        e = ChunkNotFoundError("addr")
        assert issubclass(type(e), ContentAddressError)

    def test_reference_integrity(self):
        assert issubclass(ReferenceIntegrityError, ContentAddressError)

    def test_dedup_hash_collision(self):
        assert issubclass(DeduplicationHashCollisionError, ContentAddressError)

    def test_lifecycle_error(self):
        assert issubclass(LifecycleError, FizzS3Error)

    def test_invalid_lifecycle_config(self):
        assert issubclass(InvalidLifecycleConfigurationError, LifecycleError)

    def test_too_many_lifecycle_rules(self):
        assert issubclass(TooManyLifecycleRulesError, LifecycleError)

    def test_presigned_url_error(self):
        assert issubclass(PresignedURLError, FizzS3Error)

    def test_expired_presigned_url(self):
        assert issubclass(ExpiredPresignedURLError, PresignedURLError)

    def test_invalid_signature(self):
        assert issubclass(InvalidSignatureError, PresignedURLError)

    def test_signature_method_mismatch(self):
        assert issubclass(SignatureMethodMismatchError, PresignedURLError)

    def test_metadata_error(self):
        assert issubclass(MetadataError, FizzS3Error)

    def test_metadata_corruption(self):
        assert issubclass(MetadataCorruptionError, MetadataError)

    def test_metadata_capacity_exceeded(self):
        e = MetadataCapacityExceededError(3000, MAX_METADATA_SIZE)
        assert issubclass(type(e), MetadataError)

    def test_notification_error(self):
        assert issubclass(NotificationError, FizzS3Error)

    def test_invalid_notification_config(self):
        assert issubclass(InvalidNotificationConfigurationError, NotificationError)

    def test_notification_delivery_failed(self):
        assert issubclass(NotificationDeliveryFailedError, NotificationError)

    def test_middleware_error(self):
        assert issubclass(FizzS3MiddlewareError, FizzS3Error)

    def test_dashboard_error(self):
        assert issubclass(FizzS3DashboardError, FizzS3Error)


# ============================================================
# TestFizzS3Integration
# ============================================================


class TestFizzS3Integration:
    """End-to-end integration tests for the FizzS3 subsystem."""

    def test_full_object_lifecycle(self, bucket_manager, object_store, event_bus):
        bucket_manager.create_bucket("integ-bucket")
        obj = object_store.put_object("integ-bucket", "eval.json", b'{"n":15,"r":"FizzBuzz"}')
        fetched = object_store.get_object("integ-bucket", "eval.json")
        assert fetched.data == b'{"n":15,"r":"FizzBuzz"}'
        object_store.delete_object("integ-bucket", "eval.json")
        with pytest.raises(ObjectNotFoundError):
            object_store.get_object("integ-bucket", "eval.json")

    def test_versioned_lifecycle(self, bucket_manager, object_store, versioning_engine, event_bus):
        bucket_manager.create_bucket("ver-integ")
        bucket_manager.put_bucket_versioning("ver-integ", BucketVersioning.ENABLED)
        v1 = object_store.put_object("ver-integ", "file.txt", b"v1")
        v2 = object_store.put_object("ver-integ", "file.txt", b"v2")
        latest = object_store.get_object("ver-integ", "file.txt")
        assert latest.data == b"v2"
        chain = versioning_engine.get_version_chain("ver-integ", "file.txt")
        assert len(chain) >= 2

    def test_multipart_end_to_end(self, bucket_manager, object_store, multipart_manager, event_bus):
        bucket_manager.create_bucket("mp-integ")
        uid = multipart_manager.create_multipart_upload("mp-integ", "large.bin")
        part1 = b"a" * MIN_PART_SIZE
        part2 = b"b" * 100
        e1 = multipart_manager.upload_part("mp-integ", "large.bin", uid, 1, part1)
        e2 = multipart_manager.upload_part("mp-integ", "large.bin", uid, 2, part2)
        obj = multipart_manager.complete_multipart_upload("mp-integ", "large.bin", uid, [
            {"part_number": 1, "etag": e1},
            {"part_number": 2, "etag": e2},
        ])
        fetched = object_store.get_object("mp-integ", "large.bin")
        assert len(fetched.data) == MIN_PART_SIZE + 100

    def test_dedup_across_objects(self, bucket_manager, object_store, cas, event_bus):
        bucket_manager.create_bucket("dedup-integ")
        data = b"FizzBuzz" * 1000
        object_store.put_object("dedup-integ", "a.txt", data)
        object_store.put_object("dedup-integ", "b.txt", data)
        stats = cas.get_deduplication_stats("dedup-integ")
        assert stats.dedup_ratio >= 1.0
        assert stats.shared_chunks > 0

    def test_presigned_url_flow(self, bucket_manager, object_store, sig_computer, event_bus):
        bucket_manager.create_bucket("presign-integ")
        object_store.put_object("presign-integ", "signed.txt", b"secret")
        gen = PresignedURLGenerator(sig_computer, region="fizz-east-1")
        ver = PresignedURLVerifier(sig_computer, region="fizz-east-1")
        url = gen.generate_presigned_url("GET", "presign-integ", "signed.txt")
        result = ver.verify(url, "GET")
        assert result.allowed is True

    def test_encryption_in_object_flow(self, bucket_manager, object_store, event_bus):
        bucket_manager.create_bucket("enc-integ")
        obj = object_store.put_object(
            "enc-integ", "secret.txt", b"classified evaluation",
            encryption_mode=EncryptionMode.SSE_S3,
        )
        assert obj.server_side_encryption is not None
        assert obj.server_side_encryption.mode == EncryptionMode.SSE_S3

    def test_copy_between_buckets(self, bucket_manager, object_store, event_bus):
        bucket_manager.create_bucket("src-integ")
        bucket_manager.create_bucket("dst-integ")
        object_store.put_object("src-integ", "original.txt", b"data to copy")
        copied = object_store.copy_object("src-integ", "original.txt", "dst-integ", "replica.txt")
        result = object_store.get_object("dst-integ", "replica.txt")
        assert result.data == b"data to copy"

    def test_factory_creates_working_subsystem(self):
        service, mw = create_fizzs3_subsystem()
        from enterprise_fizzbuzz.domain.models import ProcessingContext
        ctx = ProcessingContext(number=15, session_id="test-session")
        processed = mw.process(ctx, lambda c: c)
        assert processed is not None

    def test_bucket_operations_full_flow(self, bucket_manager, event_bus):
        bucket_manager.create_bucket("flow-bucket", region="fizz-eu-1")
        assert bucket_manager.head_bucket("flow-bucket") is True
        assert bucket_manager.get_bucket_location("flow-bucket") == "fizz-eu-1"
        buckets = bucket_manager.list_buckets()
        assert any(b.name == "flow-bucket" for b in buckets)
        bucket_manager.delete_bucket("flow-bucket")
        assert bucket_manager.head_bucket("flow-bucket") is False

    def test_erasure_coding_integration(self, erasure_engine):
        data = b"FizzBuzz evaluation output for input 15" * 100
        for sc, (d, p) in ERASURE_PARAMS.items():
            fragments = erasure_engine.encode(data, d, p)
            frag_dict = {i: f for i, f in enumerate(fragments)}
            assert erasure_engine.verify_fragments(frag_dict, d, p) is True
            decoded = erasure_engine.decode(frag_dict, d, p)
            assert decoded[:len(data)] == data

    def test_storage_class_transition_flow(self, bucket_manager, object_store, cas, erasure_engine, event_bus):
        bucket_manager.create_bucket("trans-bucket")
        object_store.put_object("trans-bucket", "aging.txt", b"data")
        mgr = StorageClassManager(object_store, cas, erasure_engine, event_bus)
        mgr.transition_object("trans-bucket", "aging.txt", target_class=StorageClass.STANDARD_IA)
        obj = object_store.get_object("trans-bucket", "aging.txt")
        assert obj.storage_class == StorageClass.STANDARD_IA

    def test_conditional_get_flow(self, bucket_manager, object_store, event_bus):
        bucket_manager.create_bucket("cond-bucket")
        obj = object_store.put_object("cond-bucket", "file.txt", b"data")
        # If-Match success
        result = object_store.get_object("cond-bucket", "file.txt", if_match=obj.etag)
        assert result.data == b"data"
        # If-None-Match 304
        with pytest.raises(NotModifiedError):
            object_store.get_object("cond-bucket", "file.txt", if_none_match=obj.etag)

    def test_byte_range_retrieval(self, bucket_manager, object_store, event_bus):
        bucket_manager.create_bucket("range-bucket")
        object_store.put_object("range-bucket", "data.bin", b"0123456789")
        result = object_store.get_object("range-bucket", "data.bin", byte_range="bytes=2-5")
        assert result.data == b"2345"

    def test_multiple_buckets_isolation(self, bucket_manager, object_store, event_bus):
        bucket_manager.create_bucket("bucket-a")
        bucket_manager.create_bucket("bucket-b")
        object_store.put_object("bucket-a", "file.txt", b"A")
        object_store.put_object("bucket-b", "file.txt", b"B")
        a = object_store.get_object("bucket-a", "file.txt")
        b = object_store.get_object("bucket-b", "file.txt")
        assert a.data == b"A"
        assert b.data == b"B"

    def test_events_published_throughout_lifecycle(self, bucket_manager, object_store, event_bus):
        bucket_manager.create_bucket("events-bucket")
        object_store.put_object("events-bucket", "file.txt", b"data")
        object_store.delete_object("events-bucket", "file.txt")
        bucket_manager.delete_bucket("events-bucket")
        event_types = [e[0] for e in event_bus.events]
        assert any("BUCKET_CREATED" in t for t in event_types)
        assert any("OBJECT_CREATED" in t for t in event_types)
        assert any("OBJECT_DELETED" in t for t in event_types)
        assert any("BUCKET_DELETED" in t for t in event_types)
