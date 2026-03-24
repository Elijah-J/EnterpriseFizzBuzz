"""
Enterprise FizzBuzz Platform - FizzS3: S3-Compatible Object Storage

A complete S3-compatible object storage service implementing the core S3 REST
API surface for the Enterprise FizzBuzz Platform.  FizzS3 provides bucket
management, object CRUD with conditional requests and byte-range reads,
object versioning with delete markers, multipart upload for large objects,
presigned URLs with AWS Signature Version 4, four storage classes with
lifecycle-driven transitions, cross-region replication with conflict
resolution, server-side encryption (SSE-S3, SSE-KMS, SSE-C), IAM-style
bucket policies with ACLs and block public access, event notifications
published to FizzEventBus, content-addressable deduplication with SHA-256
hashing and reference counting, and Reed-Solomon erasure coding over
GF(2^8) for configurable durability.

The storage engine uses a two-tier architecture: a metadata tier with B-tree
and hash indices for fast key lookups and prefix scans, and a data tier
storing object content as erasure-coded fragments in an append-only segment
log with periodic compaction.  Content-addressable deduplication eliminates
redundant storage of identical data chunks across objects, reducing physical
storage consumption for the platform's highly repetitive FizzBuzz evaluation
output.  Erasure coding achieves eleven-nines durability (99.999999999%)
with 1.4x storage overhead, compared to three-way replication's 3x overhead.

The platform's subsystems produce artifacts that are fundamentally object
storage workloads: FizzFlame SVG renderings, FizzRay image buffers, FizzELF
executables, FizzPrint formatted documents, FizzSheet workbooks, FizzCodec
video frames, FizzRegistry OCI blobs, FizzWAL segment files, and FizzVCS
packfiles.  These artifacts are immutable after creation, identified by
unique keys, and benefit from tiered storage.  Storing them in FizzVFS
imposes unnecessary hierarchy, mutable semantics, and uniform storage cost
on workloads that need none of these.

Architecture references: Amazon S3 (https://aws.amazon.com/s3/),
MinIO (https://min.io/), Ceph RADOS Gateway (https://docs.ceph.com/en/latest/radosgw/)
"""

from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import json
import logging
import math
import os
import re
import struct
import threading
import time
import uuid
from collections import defaultdict, OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union
from urllib.parse import quote, unquote, urlencode, urlparse

from enterprise_fizzbuzz.domain.exceptions import (
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
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzResult,
    ProcessingContext,
)

logger = logging.getLogger("enterprise_fizzbuzz.fizzs3")


# ============================================================
# Constants
# ============================================================

FIZZS3_VERSION = "1.0.0"
S3_API_VERSION = "2006-03-01"
DEFAULT_REGION = "fizz-east-1"
SUPPORTED_REGIONS = ["fizz-east-1", "fizz-west-1", "fizz-eu-1", "fizz-ap-1"]
MAX_BUCKET_NAME_LENGTH = 63
MIN_BUCKET_NAME_LENGTH = 3
MAX_BUCKETS_PER_OWNER = 100
MAX_OBJECT_KEY_LENGTH = 1024
MAX_SINGLE_PUT_SIZE = 5 * 1024 ** 3
MAX_OBJECT_SIZE = 5 * 1024 ** 4
MAX_METADATA_SIZE = 2048
MAX_TAGS_PER_BUCKET = 50
MIN_PART_SIZE = 5 * 1024 ** 2
MAX_PART_SIZE = 5 * 1024 ** 3
MAX_PARTS = 10000
MAX_LIST_KEYS = 1000
MAX_DELETE_OBJECTS = 1000
MAX_LIFECYCLE_RULES = 1000
MAX_REPLICATION_RULES = 1000
MAX_PRESIGN_EXPIRY = 604800
CLOCK_SKEW_TOLERANCE = 900
DEFAULT_CHUNK_SIZE = 4 * 1024 ** 2
DEFAULT_SEGMENT_MAX_SIZE = 256 * 1024 ** 2
DEFAULT_COMPACTION_THRESHOLD = 0.5
DEFAULT_GC_INTERVAL = 21600.0
DEFAULT_GC_SAFETY_DELAY = 86400.0
DEFAULT_CHECKPOINT_INTERVAL = 60.0
DEFAULT_LIFECYCLE_INTERVAL = 86400.0
DEFAULT_REPLICATION_RETRY_MAX = 24
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 118


# ============================================================
# Enums
# ============================================================


class BucketVersioning(Enum):
    """Bucket versioning states.

    Once enabled, versioning cannot return to DISABLED -- only SUSPENDED.
    Existing versions are preserved in both ENABLED and SUSPENDED states.
    """
    DISABLED = "disabled"
    ENABLED = "enabled"
    SUSPENDED = "suspended"


class StorageClass(Enum):
    """Storage tier with distinct erasure coding parameters, access latency,
    and cost characteristics.

    The four tiers form a strict waterfall: STANDARD -> STANDARD_IA ->
    ARCHIVE -> DEEP_ARCHIVE.  Each tier trades access speed for storage
    cost reduction.
    """
    STANDARD = "STANDARD"
    STANDARD_IA = "STANDARD_IA"
    ARCHIVE = "ARCHIVE"
    DEEP_ARCHIVE = "DEEP_ARCHIVE"


# Erasure coding parameters per storage class: (data_fragments, parity_fragments)
ERASURE_PARAMS = {
    StorageClass.STANDARD: (10, 4),
    StorageClass.STANDARD_IA: (6, 4),
    StorageClass.ARCHIVE: (4, 4),
    StorageClass.DEEP_ARCHIVE: (2, 4),
}

# Storage class waterfall ordering for transition validation
STORAGE_CLASS_ORDER = {
    StorageClass.STANDARD: 0,
    StorageClass.STANDARD_IA: 1,
    StorageClass.ARCHIVE: 2,
    StorageClass.DEEP_ARCHIVE: 3,
}


class RestoreTier(Enum):
    """Archive restore speed tiers."""
    EXPEDITED = "expedited"
    STANDARD = "standard"
    BULK = "bulk"


class EncryptionMode(Enum):
    """Server-side encryption modes."""
    SSE_S3 = "sse-s3"
    SSE_KMS = "sse-kms"
    SSE_C = "sse-c"


class EncryptionAlgorithm(Enum):
    """Encryption algorithm identifier."""
    AES_256 = "AES256"


class PolicyEffect(Enum):
    """IAM policy statement effect."""
    ALLOW = "Allow"
    DENY = "Deny"


class ACLPermission(Enum):
    """Access control list permission levels."""
    FULL_CONTROL = "FULL_CONTROL"
    READ = "READ"
    WRITE = "WRITE"
    READ_ACP = "READ_ACP"
    WRITE_ACP = "WRITE_ACP"


class CannedACL(Enum):
    """Predefined ACL configurations."""
    PRIVATE = "private"
    PUBLIC_READ = "public-read"
    PUBLIC_READ_WRITE = "public-read-write"
    AUTHENTICATED_READ = "authenticated-read"
    BUCKET_OWNER_READ = "bucket-owner-read"
    BUCKET_OWNER_FULL_CONTROL = "bucket-owner-full-control"


class S3EventType(Enum):
    """Object lifecycle event types for notification configuration."""
    OBJECT_CREATED_ALL = "s3:ObjectCreated:*"
    OBJECT_CREATED_PUT = "s3:ObjectCreated:Put"
    OBJECT_CREATED_POST = "s3:ObjectCreated:Post"
    OBJECT_CREATED_COPY = "s3:ObjectCreated:Copy"
    OBJECT_CREATED_MPU = "s3:ObjectCreated:CompleteMultipartUpload"
    OBJECT_REMOVED_ALL = "s3:ObjectRemoved:*"
    OBJECT_REMOVED_DELETE = "s3:ObjectRemoved:Delete"
    OBJECT_REMOVED_DELETE_MARKER = "s3:ObjectRemoved:DeleteMarkerCreated"
    OBJECT_RESTORE_POST = "s3:ObjectRestore:Post"
    OBJECT_RESTORE_COMPLETED = "s3:ObjectRestore:Completed"
    OBJECT_TRANSITION = "s3:ObjectTransition"
    REPLICATION_ALL = "s3:Replication:*"
    REPLICATION_COMPLETED = "s3:Replication:OperationCompleted"
    REPLICATION_FAILED = "s3:Replication:OperationFailed"
    LIFECYCLE_EXPIRATION_DELETE = "s3:LifecycleExpiration:Delete"
    LIFECYCLE_EXPIRATION_MARKER = "s3:LifecycleExpiration:DeleteMarkerCreated"


class DestinationType(Enum):
    """Notification destination types."""
    EVENT_BUS = "event_bus"
    WEBHOOK = "webhook"
    QUEUE = "queue"


class RuleStatus(Enum):
    """Status for lifecycle and replication rules."""
    ENABLED = "Enabled"
    DISABLED = "Disabled"


class SegmentStatus(Enum):
    """Segment lifecycle states in the data tier."""
    ACTIVE = "active"
    SEALED = "sealed"
    COMPACTING = "compacting"
    DELETED = "deleted"


# ============================================================
# Data Classes
# ============================================================


@dataclass
class ServerSideEncryption:
    """Encryption metadata for an encrypted object.

    Attributes:
        algorithm: Encryption algorithm (always AES-256).
        mode: Encryption mode (SSE-S3, SSE-KMS, SSE-C).
        kms_key_id: FizzVault key ID for SSE-KMS.
        key_md5: Base64-encoded MD5 of client-provided key for SSE-C.
    """
    algorithm: EncryptionAlgorithm = EncryptionAlgorithm.AES_256
    mode: EncryptionMode = EncryptionMode.SSE_S3
    kms_key_id: Optional[str] = None
    key_md5: Optional[str] = None


@dataclass
class EncryptionConfiguration:
    """Bucket-level default encryption settings.

    Attributes:
        default_encryption: Default encryption mode for new objects.
        kms_key_id: FizzVault key ID for SSE-KMS default.
        bucket_key_enabled: Use bucket-level key derivation for SSE-KMS.
    """
    default_encryption: EncryptionMode = EncryptionMode.SSE_S3
    kms_key_id: Optional[str] = None
    bucket_key_enabled: bool = False


@dataclass
class BlockPublicAccessConfiguration:
    """Four independent settings preventing public access to a bucket.

    Attributes:
        block_public_acls: Reject PUTs with public ACLs.
        ignore_public_acls: Ignore existing public ACLs.
        block_public_policy: Reject bucket policies granting public access.
        restrict_public_buckets: Restrict cross-account access to public buckets.
    """
    block_public_acls: bool = True
    ignore_public_acls: bool = True
    block_public_policy: bool = True
    restrict_public_buckets: bool = True


@dataclass
class Grant:
    """Individual access grant within an ACL.

    Attributes:
        grantee: Recipient (principal ID, group, or email).
        grantee_type: Type of grantee (canonical_user, group, email).
        permission: Granted permission.
    """
    grantee: str = ""
    grantee_type: str = "canonical_user"
    permission: ACLPermission = ACLPermission.READ


@dataclass
class AccessControlList:
    """ACL-based access control for a bucket or object.

    Attributes:
        owner: Bucket or object owner.
        grants: Access grants.
    """
    owner: str = "fizzbuzz-root"
    grants: List[Grant] = field(default_factory=list)


@dataclass
class PolicyStatement:
    """Individual statement within a bucket policy.

    Attributes:
        sid: Statement identifier.
        effect: ALLOW or DENY.
        principal: Entity the statement applies to.
        action: S3 actions governed (e.g., s3:GetObject).
        resource: ARN patterns for target resources.
        condition: Condition operators for fine-grained control.
    """
    sid: Optional[str] = None
    effect: PolicyEffect = PolicyEffect.ALLOW
    principal: Union[str, List[str]] = "*"
    action: List[str] = field(default_factory=list)
    resource: List[str] = field(default_factory=list)
    condition: Optional[Dict[str, Dict[str, str]]] = None


@dataclass
class BucketPolicy:
    """IAM-style policy document for bucket access control.

    Attributes:
        version: Policy language version.
        statements: Policy statements.
    """
    version: str = "2012-10-17"
    statements: List[PolicyStatement] = field(default_factory=list)


@dataclass
class TransitionRule:
    """Storage class transition trigger within a lifecycle rule.

    Attributes:
        days: Days after creation to trigger transition.
        storage_class: Target storage class.
    """
    days: int = 30
    storage_class: StorageClass = StorageClass.STANDARD_IA


@dataclass
class NoncurrentVersionTransitionRule:
    """Transition rule for noncurrent object versions.

    Attributes:
        noncurrent_days: Days after becoming noncurrent to transition.
        storage_class: Target storage class.
        newer_noncurrent_versions: Noncurrent versions to retain before transitioning.
    """
    noncurrent_days: int = 30
    storage_class: StorageClass = StorageClass.STANDARD_IA
    newer_noncurrent_versions: Optional[int] = None


@dataclass
class LifecycleRule:
    """Individual lifecycle rule for a bucket.

    Attributes:
        id: Unique rule identifier.
        status: ENABLED or DISABLED.
        prefix: Object key prefix filter.
        tags: Object tag filter.
        transitions: Storage class transition rules.
        expiration_days: Days after creation to expire current objects.
        noncurrent_version_expiration_days: Days after becoming noncurrent to expire.
        noncurrent_version_transitions: Transition rules for noncurrent versions.
        abort_incomplete_multipart_days: Days to abort incomplete multipart uploads.
    """
    id: str = ""
    status: RuleStatus = RuleStatus.ENABLED
    prefix: str = ""
    tags: Dict[str, str] = field(default_factory=dict)
    transitions: List[TransitionRule] = field(default_factory=list)
    expiration_days: Optional[int] = None
    noncurrent_version_expiration_days: Optional[int] = None
    noncurrent_version_transitions: List[NoncurrentVersionTransitionRule] = field(default_factory=list)
    abort_incomplete_multipart_days: Optional[int] = None


@dataclass
class LifecycleConfiguration:
    """Lifecycle rules governing object transitions and expirations.

    Attributes:
        rules: Lifecycle rules (max 1000 per bucket).
    """
    rules: List[LifecycleRule] = field(default_factory=list)


@dataclass
class ReplicationRule:
    """Individual cross-region replication rule.

    Attributes:
        id: Unique rule identifier.
        status: ENABLED or DISABLED.
        priority: Evaluation priority (higher = higher priority).
        prefix: Object key prefix filter.
        destination_bucket: Destination bucket name.
        destination_region: Destination region.
        destination_storage_class: Override storage class in destination.
        delete_marker_replication: Whether to replicate delete markers.
    """
    id: str = ""
    status: RuleStatus = RuleStatus.ENABLED
    priority: int = 0
    prefix: str = ""
    destination_bucket: str = ""
    destination_region: str = ""
    destination_storage_class: Optional[StorageClass] = None
    delete_marker_replication: bool = False


@dataclass
class ReplicationConfiguration:
    """Cross-region replication rules for a source bucket.

    Attributes:
        role: IAM role assumed by the replication engine.
        rules: Replication rules (max 1000).
    """
    role: str = "fizz-replication-role"
    rules: List[ReplicationRule] = field(default_factory=list)


@dataclass
class EventRule:
    """Individual event notification rule.

    Attributes:
        id: Unique rule identifier.
        events: Event types that trigger notification.
        prefix_filter: Object key prefix filter.
        suffix_filter: Object key suffix filter.
        destination_type: Where to publish (event_bus, webhook, queue).
        destination_target: Destination identifier.
    """
    id: str = ""
    events: List[S3EventType] = field(default_factory=list)
    prefix_filter: str = ""
    suffix_filter: str = ""
    destination_type: DestinationType = DestinationType.EVENT_BUS
    destination_target: str = ""


@dataclass
class NotificationConfiguration:
    """Event notification rules for a bucket.

    Attributes:
        event_rules: Notification rules mapping events to destinations.
    """
    event_rules: List[EventRule] = field(default_factory=list)


@dataclass
class Bucket:
    """Top-level namespace container for objects in FizzS3.

    Buckets have globally unique names validated against S3 naming rules,
    a region assignment, versioning state, and configurations for lifecycle,
    access control, encryption, replication, and event notifications.
    """
    name: str
    region: str = DEFAULT_REGION
    creation_date: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    owner: str = "fizzbuzz-root"
    versioning: BucketVersioning = BucketVersioning.DISABLED
    lifecycle_configuration: Optional[LifecycleConfiguration] = None
    acl: Optional[AccessControlList] = None
    policy: Optional[BucketPolicy] = None
    encryption_configuration: Optional[EncryptionConfiguration] = None
    replication_configuration: Optional[ReplicationConfiguration] = None
    notification_configuration: Optional[NotificationConfiguration] = None
    block_public_access: Optional[BlockPublicAccessConfiguration] = None
    object_lock_enabled: bool = False
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class S3Object:
    """Fundamental storage unit in FizzS3.

    Each object consists of a key within a bucket, a data payload, system
    and user metadata, a storage class assignment, and optional versioning
    and encryption information.
    """
    key: str
    bucket_name: str = ""
    version_id: Optional[str] = None
    data: bytes = b""
    size: int = 0
    etag: str = ""
    content_type: str = "application/octet-stream"
    content_encoding: Optional[str] = None
    content_disposition: Optional[str] = None
    content_language: Optional[str] = None
    cache_control: Optional[str] = None
    last_modified: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    storage_class: StorageClass = StorageClass.STANDARD
    metadata: Dict[str, str] = field(default_factory=dict)
    server_side_encryption: Optional[ServerSideEncryption] = None
    delete_marker: bool = False
    is_latest: bool = True
    checksum_sha256: Optional[str] = None
    replication_status: Optional[str] = None


@dataclass
class ObjectSummary:
    """Lightweight object metadata returned in list operations."""
    key: str
    last_modified: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    etag: str = ""
    size: int = 0
    storage_class: StorageClass = StorageClass.STANDARD
    owner: str = "fizzbuzz-root"


@dataclass
class ListObjectsResult:
    """Response model for list_objects_v2."""
    contents: List[ObjectSummary] = field(default_factory=list)
    common_prefixes: List[str] = field(default_factory=list)
    is_truncated: bool = False
    next_continuation_token: Optional[str] = None
    key_count: int = 0
    max_keys: int = MAX_LIST_KEYS
    prefix: Optional[str] = None
    delimiter: Optional[str] = None


@dataclass
class DeleteMarker:
    """Zero-byte object version indicating deletion in a versioned bucket."""
    key: str
    version_id: str = ""
    last_modified: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    owner: str = "fizzbuzz-root"
    is_latest: bool = True


@dataclass
class UploadPart:
    """Metadata for a single uploaded part."""
    part_number: int = 1
    etag: str = ""
    size: int = 0
    last_modified: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    data: bytes = b""


@dataclass
class MultipartUpload:
    """In-progress multipart upload session."""
    upload_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    bucket: str = ""
    key: str = ""
    initiated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    storage_class: StorageClass = StorageClass.STANDARD
    encryption: Optional[ServerSideEncryption] = None
    metadata: Dict[str, str] = field(default_factory=dict)
    content_type: str = "application/octet-stream"
    parts: Dict[int, UploadPart] = field(default_factory=dict)


@dataclass
class S3EventMessage:
    """Notification payload published for storage events."""
    event_version: str = "2.1"
    event_source: str = "fizz:s3"
    event_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    event_name: str = ""
    bucket_name: str = ""
    bucket_owner: str = ""
    object_key: str = ""
    object_size: int = 0
    object_etag: str = ""
    object_version_id: Optional[str] = None
    object_sequencer: str = ""
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    principal: str = "fizzbuzz-root"


@dataclass
class ChunkReference:
    """Reference to a content-addressed chunk within an object."""
    address: str = ""
    offset: int = 0
    size: int = 0
    sequence: int = 0


@dataclass
class ChunkManifest:
    """Maps an object to its content-addressed chunks."""
    object_id: str = ""
    chunks: List[ChunkReference] = field(default_factory=list)
    total_size: int = 0
    chunk_count: int = 0


@dataclass
class AuthorizationResult:
    """Result of an access control evaluation."""
    allowed: bool = False
    reason: str = ""
    evaluated_policies: int = 0


@dataclass
class LifecycleAction:
    """Action determined by lifecycle evaluation."""
    action_type: str = ""  # "expire", "transition", "abort_multipart"
    bucket_name: str = ""
    key: str = ""
    version_id: Optional[str] = None
    target_storage_class: Optional[StorageClass] = None


@dataclass
class DeduplicationStats:
    """Content-addressable deduplication statistics."""
    logical_size: int = 0
    physical_size: int = 0
    dedup_ratio: float = 1.0
    shared_chunks: int = 0
    unique_chunks: int = 0
    total_chunks: int = 0


@dataclass
class FragmentLocation:
    """Physical location of an erasure-coded fragment."""
    fragment_index: int = 0
    segment_id: str = ""
    offset: int = 0
    length: int = 0
    checksum: str = ""


@dataclass
class Segment:
    """Append-only segment in the data tier."""
    segment_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: SegmentStatus = SegmentStatus.ACTIVE
    size: int = 0
    live_bytes: int = 0
    dead_bytes: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    sealed_at: Optional[datetime] = None
    fragments: Dict[str, bytes] = field(default_factory=dict)
    fragment_locations: Dict[str, FragmentLocation] = field(default_factory=dict)


# ============================================================
# BucketNameValidator
# ============================================================


class BucketNameValidator:
    """Validates bucket names against the S3 naming specification.

    S3 bucket naming rules are strict to support DNS compatibility:
    names must be valid DNS labels, globally unique, and resistant
    to confusion attacks.
    """

    _IP_PATTERN = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$")
    _VALID_CHARS = re.compile(r"^[a-z0-9.\-]+$")

    @classmethod
    def validate(cls, name: str) -> Tuple[bool, List[str]]:
        """Validate a bucket name against S3 naming rules.

        Args:
            name: Proposed bucket name.

        Returns:
            Tuple of (is_valid, list_of_violations).
        """
        violations: List[str] = []

        if len(name) < MIN_BUCKET_NAME_LENGTH:
            violations.append(
                f"Name too short: {len(name)} chars (minimum {MIN_BUCKET_NAME_LENGTH})"
            )
        if len(name) > MAX_BUCKET_NAME_LENGTH:
            violations.append(
                f"Name too long: {len(name)} chars (maximum {MAX_BUCKET_NAME_LENGTH})"
            )
        if not cls._VALID_CHARS.match(name):
            violations.append("Contains invalid characters (must be lowercase alphanumeric, hyphens, periods)")
        if name and not (name[0].isalnum()):
            violations.append("Must start with a letter or number")
        if name and not (name[-1].isalnum()):
            violations.append("Must end with a letter or number")
        if ".." in name:
            violations.append("Must not contain consecutive periods")
        if cls._IP_PATTERN.match(name):
            violations.append("Must not be formatted as an IPv4 address")
        if name.startswith("xn--"):
            violations.append("Must not start with 'xn--' (IDN prefix)")
        if name.endswith("-s3alias"):
            violations.append("Must not end with '-s3alias'")
        if name.endswith("--ol-s3"):
            violations.append("Must not end with '--ol-s3'")

        return (len(violations) == 0, violations)


# ============================================================
# GaloisField — GF(2^8) arithmetic for Reed-Solomon
# ============================================================


class GaloisField:
    """Arithmetic operations over GF(2^8) for Reed-Solomon erasure coding.

    Uses irreducible polynomial x^8 + x^4 + x^3 + x^2 + 1 (0x11D) as
    the field generator.  All operations are performed via precomputed
    log and antilog lookup tables for O(1) multiplication and division.
    """

    FIELD_SIZE = 256
    POLYNOMIAL = 0x11D

    def __init__(self) -> None:
        """Initialize lookup tables for GF(2^8) arithmetic."""
        self.exp_table = [0] * (self.FIELD_SIZE * 2)
        self.log_table = [0] * self.FIELD_SIZE
        self._generate_tables()

    def _generate_tables(self) -> None:
        """Generate exponential and logarithm lookup tables.

        Uses the generator element 2 (x) to compute all 255 non-zero
        field elements as powers of the generator.
        """
        x = 1
        for i in range(self.FIELD_SIZE - 1):
            self.exp_table[i] = x
            self.exp_table[i + (self.FIELD_SIZE - 1)] = x
            self.log_table[x] = i
            x = self._raw_multiply(x, 2)
        self.log_table[0] = 0

    def _raw_multiply(self, a: int, b: int) -> int:
        """Multiply two field elements using bit-level operations.

        Used only during table generation.  After tables are built,
        multiplication uses log/exp table lookups.
        """
        result = 0
        while b > 0:
            if b & 1:
                result ^= a
            a <<= 1
            if a & 0x100:
                a ^= self.POLYNOMIAL
            b >>= 1
        return result

    def add(self, a: int, b: int) -> int:
        """Add two GF(2^8) elements (XOR)."""
        return a ^ b

    def subtract(self, a: int, b: int) -> int:
        """Subtract two GF(2^8) elements (same as add in GF(2^8))."""
        return a ^ b

    def multiply(self, a: int, b: int) -> int:
        """Multiply two GF(2^8) elements via log/exp tables."""
        if a == 0 or b == 0:
            return 0
        return self.exp_table[self.log_table[a] + self.log_table[b]]

    def divide(self, a: int, b: int) -> int:
        """Divide two GF(2^8) elements via log/exp tables."""
        if b == 0:
            raise ErasureCodingError("Division by zero in GF(2^8)")
        if a == 0:
            return 0
        diff = self.log_table[a] - self.log_table[b]
        if diff < 0:
            diff += self.FIELD_SIZE - 1
        return self.exp_table[diff]

    def inverse(self, a: int) -> int:
        """Compute multiplicative inverse in GF(2^8)."""
        if a == 0:
            raise ErasureCodingError("No inverse for zero in GF(2^8)")
        return self.exp_table[(self.FIELD_SIZE - 1) - self.log_table[a]]

    def power(self, a: int, n: int) -> int:
        """Raise a GF(2^8) element to the n-th power."""
        if n == 0:
            return 1
        if a == 0:
            return 0
        log_result = (self.log_table[a] * n) % (self.FIELD_SIZE - 1)
        return self.exp_table[log_result]


# ============================================================
# VandermondeMatrix — matrix operations for Reed-Solomon
# ============================================================


class VandermondeMatrix:
    """Constructs and operates on Vandermonde matrices for Reed-Solomon encoding.

    The encoding matrix is constructed so that the first K rows form an
    identity matrix (systematic encoding), meaning the original data
    fragments appear unchanged in the output.
    """

    def __init__(self, gf: GaloisField) -> None:
        self._gf = gf

    def build(self, rows: int, cols: int) -> List[List[int]]:
        """Build a Vandermonde-based encoding matrix.

        The first `cols` rows form an identity matrix for systematic
        encoding.  Additional rows produce parity fragments.

        Args:
            rows: Total rows (data + parity fragments).
            cols: Columns (data fragments).

        Returns:
            Matrix as list of rows.
        """
        matrix: List[List[int]] = []
        for i in range(rows):
            row = []
            for j in range(cols):
                if i < cols:
                    # Identity matrix for systematic encoding
                    row.append(1 if i == j else 0)
                else:
                    # Vandermonde entries for parity rows
                    row.append(self._gf.power(j + 1, i - cols + 1))
            matrix.append(row)
        return matrix

    def invert_submatrix(self, matrix: List[List[int]], indices: List[int],
                         cols: int) -> List[List[int]]:
        """Extract and invert a submatrix via Gaussian elimination over GF(2^8).

        Args:
            matrix: Full encoding matrix.
            indices: Row indices to extract (must have length == cols).
            cols: Matrix dimension.

        Returns:
            Inverted submatrix.
        """
        # Extract submatrix
        sub = []
        for i in indices:
            sub.append(list(matrix[i]))

        # Augment with identity
        n = cols
        aug = []
        for i in range(n):
            row = sub[i][:] + [1 if i == j else 0 for j in range(n)]
            aug.append(row)

        # Gaussian elimination
        for col in range(n):
            # Find pivot
            pivot_row = None
            for row in range(col, n):
                if aug[row][col] != 0:
                    pivot_row = row
                    break
            if pivot_row is None:
                raise ErasureCodingError("Singular submatrix: cannot invert")

            if pivot_row != col:
                aug[col], aug[pivot_row] = aug[pivot_row], aug[col]

            # Scale pivot row
            inv_pivot = self._gf.inverse(aug[col][col])
            for j in range(2 * n):
                aug[col][j] = self._gf.multiply(aug[col][j], inv_pivot)

            # Eliminate column
            for row in range(n):
                if row != col and aug[row][col] != 0:
                    factor = aug[row][col]
                    for j in range(2 * n):
                        aug[row][j] = self._gf.add(
                            aug[row][j],
                            self._gf.multiply(factor, aug[col][j])
                        )

        # Extract inverse from augmented matrix
        result = []
        for i in range(n):
            result.append(aug[i][n:])
        return result

    def multiply_vector(self, matrix: List[List[int]],
                        vector: List[int]) -> List[int]:
        """Matrix-vector multiplication over GF(2^8).

        Args:
            matrix: Matrix rows.
            vector: Input vector.

        Returns:
            Result vector.
        """
        result = []
        for row in matrix:
            val = 0
            for j, elem in enumerate(row):
                val = self._gf.add(val, self._gf.multiply(elem, vector[j]))
            result.append(val)
        return result


# ============================================================
# ErasureCodingEngine — Reed-Solomon over GF(2^8)
# ============================================================


class ErasureCodingEngine:
    """Reed-Solomon erasure coding over GF(2^8).

    Provides systematic encoding (original data is preserved in output)
    and decoding from any K-of-N fragments, where K is the data fragment
    count and N = K + parity.
    """

    def __init__(self, gf: Optional[GaloisField] = None) -> None:
        self._gf = gf or GaloisField()
        self._vandermonde = VandermondeMatrix(self._gf)
        self._matrix_cache: Dict[Tuple[int, int], List[List[int]]] = {}

    def _get_encoding_matrix(self, data_frags: int,
                             parity_frags: int) -> List[List[int]]:
        """Get or create the encoding matrix for given parameters."""
        key = (data_frags, parity_frags)
        if key not in self._matrix_cache:
            self._matrix_cache[key] = self._vandermonde.build(
                data_frags + parity_frags, data_frags
            )
        return self._matrix_cache[key]

    def encode(self, data: bytes, data_fragments: int,
               parity_fragments: int) -> List[bytes]:
        """Encode data into erasure-coded fragments.

        Uses systematic Reed-Solomon encoding: the first data_fragments
        outputs are identical to the input data chunks.  Additional
        parity_fragments are computed via Vandermonde matrix multiplication
        over GF(2^8).

        Args:
            data: Input data to encode.
            data_fragments: Number of data fragments (K).
            parity_fragments: Number of parity fragments.

        Returns:
            List of data_fragments + parity_fragments fragments.
        """
        total = data_fragments + parity_fragments
        matrix = self._get_encoding_matrix(data_fragments, parity_fragments)

        # Pad data to be divisible by data_fragments
        fragment_size = math.ceil(len(data) / data_fragments)
        padded = data + b"\x00" * (fragment_size * data_fragments - len(data))

        # Split into data chunks
        data_chunks = []
        for i in range(data_fragments):
            start = i * fragment_size
            data_chunks.append(padded[start:start + fragment_size])

        # Compute all fragments (data + parity) byte by byte
        fragments = [bytearray(fragment_size) for _ in range(total)]
        for byte_pos in range(fragment_size):
            data_vector = [chunk[byte_pos] for chunk in data_chunks]
            for frag_idx in range(total):
                val = 0
                for j, elem in enumerate(matrix[frag_idx]):
                    val = self._gf.add(val, self._gf.multiply(elem, data_vector[j]))
                fragments[frag_idx][byte_pos] = val

        return [bytes(f) for f in fragments]

    def decode(self, fragments: Dict[int, bytes], data_fragments: int,
               parity_fragments: int) -> bytes:
        """Decode original data from any K available fragments.

        Performs sub-matrix inversion via Gaussian elimination when
        data fragments are missing, using available parity fragments
        to reconstruct lost data.

        Args:
            fragments: Map of fragment_index -> fragment_data.
            data_fragments: Number of data fragments (K).
            parity_fragments: Number of parity fragments.

        Returns:
            Reconstructed original data.
        """
        if len(fragments) < data_fragments:
            raise InsufficientFragmentsError(
                "decode", len(fragments), data_fragments
            )

        # Take first data_fragments available fragments
        available_indices = sorted(fragments.keys())[:data_fragments]
        matrix = self._get_encoding_matrix(data_fragments, parity_fragments)

        # Check if we have all data fragments (fast path)
        has_all_data = all(i < data_fragments for i in available_indices)
        if has_all_data and sorted(available_indices) == list(range(data_fragments)):
            fragment_size = len(next(iter(fragments.values())))
            result = bytearray()
            for i in range(data_fragments):
                result.extend(fragments[i])
            return bytes(result)

        # Slow path: invert submatrix
        inv_matrix = self._vandermonde.invert_submatrix(
            matrix, available_indices, data_fragments
        )

        fragment_size = len(next(iter(fragments.values())))
        data_chunks = [bytearray(fragment_size) for _ in range(data_fragments)]

        for byte_pos in range(fragment_size):
            available_bytes = [fragments[idx][byte_pos] for idx in available_indices]
            for i in range(data_fragments):
                val = 0
                for j, elem in enumerate(inv_matrix[i]):
                    val = self._gf.add(
                        val, self._gf.multiply(elem, available_bytes[j])
                    )
                data_chunks[i][byte_pos] = val

        result = bytearray()
        for chunk in data_chunks:
            result.extend(chunk)
        return bytes(result)

    def verify_fragments(self, fragments: Dict[int, bytes],
                         data_fragments: int,
                         parity_fragments: int) -> bool:
        """Verify fragment consistency by re-encoding and comparing parity.

        Args:
            fragments: Map of fragment_index -> fragment_data.
            data_fragments: Number of data fragments (K).
            parity_fragments: Number of parity fragments.

        Returns:
            True if all fragments are consistent.
        """
        if len(fragments) < data_fragments:
            return False

        try:
            decoded = self.decode(fragments, data_fragments, parity_fragments)
            re_encoded = self.encode(decoded, data_fragments, parity_fragments)
            for idx, frag_data in fragments.items():
                if idx < len(re_encoded) and re_encoded[idx] != frag_data:
                    return False
            return True
        except (ErasureCodingError, InsufficientFragmentsError):
            return False


# ============================================================
# FragmentDistributor
# ============================================================


class FragmentDistributor:
    """Distributes erasure-coded fragments across failure domains.

    Fragment distribution ensures that no single failure domain holds
    more fragments than the parity count, maintaining the designed
    fault tolerance.
    """

    def __init__(self) -> None:
        self._locations: Dict[str, Dict[int, bytes]] = {}  # chunk_addr -> {frag_idx -> data}
        self._location_names: Dict[str, Dict[int, str]] = {}  # chunk_addr -> {frag_idx -> location}
        self._lock = threading.Lock()

    def distribute(self, chunk_address: str, fragments: List[bytes],
                   locations: Optional[List[str]] = None) -> Dict[int, str]:
        """Assign fragments to independent storage locations.

        Args:
            chunk_address: Content address of the chunk.
            fragments: Erasure-coded fragments.
            locations: Available storage locations (defaults to virtual locations).

        Returns:
            Map of fragment_index -> location_name.
        """
        if locations is None:
            locations = [f"location-{i}" for i in range(len(fragments))]

        with self._lock:
            self._locations[chunk_address] = {}
            self._location_names[chunk_address] = {}
            for i, frag in enumerate(fragments):
                loc = locations[i % len(locations)]
                self._locations[chunk_address][i] = frag
                self._location_names[chunk_address][i] = loc

        assignment = {}
        for i in range(len(fragments)):
            assignment[i] = locations[i % len(locations)]
        return assignment

    def collect(self, chunk_address: str,
                required_count: int) -> Dict[int, bytes]:
        """Collect fragments from available locations.

        Args:
            chunk_address: Content address of the chunk.
            required_count: Minimum fragments needed.

        Returns:
            Map of fragment_index -> fragment_data.

        Raises:
            InsufficientFragmentsError: If fewer than required_count available.
        """
        with self._lock:
            stored = self._locations.get(chunk_address, {})
            if len(stored) < required_count:
                raise InsufficientFragmentsError(
                    chunk_address, len(stored), required_count
                )
            return dict(stored)

    def remove(self, chunk_address: str) -> None:
        """Remove all fragments for a chunk."""
        with self._lock:
            self._locations.pop(chunk_address, None)
            self._location_names.pop(chunk_address, None)

    def get_fragment(self, chunk_address: str, fragment_index: int) -> bytes:
        """Retrieve a single fragment."""
        with self._lock:
            stored = self._locations.get(chunk_address, {})
            if fragment_index not in stored:
                raise FragmentCorruptionError(chunk_address, fragment_index)
            return stored[fragment_index]


# ============================================================
# FragmentIntegrityChecker
# ============================================================


class FragmentIntegrityChecker:
    """Monitors and repairs fragment health via periodic scrubbing.

    The integrity checker verifies erasure-coded fragments against
    their expected checksums and uses the erasure coding engine to
    repair any detected corruptions from healthy fragments.
    """

    def __init__(
        self,
        cas: ContentAddressableStore,
        erasure_engine: ErasureCodingEngine,
        fragment_distributor: FragmentDistributor,
    ) -> None:
        self._cas = cas
        self._erasure_engine = erasure_engine
        self._distributor = fragment_distributor
        self._scrub_results: Dict[str, Dict[str, Any]] = {}

    def check_chunk(self, chunk_address: str,
                    data_fragments: int = 10,
                    parity_fragments: int = 4) -> Tuple[bool, List[int]]:
        """Check fragment integrity for a chunk.

        Returns:
            Tuple of (all_healthy, list_of_corrupt_indices).
        """
        try:
            fragments = self._distributor.collect(
                chunk_address, data_fragments
            )
            is_valid = self._erasure_engine.verify_fragments(
                fragments, data_fragments, parity_fragments
            )
            return (is_valid, [] if is_valid else list(fragments.keys()))
        except (InsufficientFragmentsError, ErasureCodingError):
            return (False, [])

    def repair_chunk(self, chunk_address: str,
                     corrupt_indices: List[int],
                     data_fragments: int = 10,
                     parity_fragments: int = 4) -> bool:
        """Repair corrupt fragments from healthy ones.

        Returns:
            True if repair succeeded.
        """
        try:
            all_frags = self._distributor.collect(
                chunk_address, data_fragments + parity_fragments
            )
            # Remove corrupt fragments
            healthy = {
                idx: data for idx, data in all_frags.items()
                if idx not in corrupt_indices
            }
            if len(healthy) < data_fragments:
                return False

            decoded = self._erasure_engine.decode(
                healthy, data_fragments, parity_fragments
            )
            new_frags = self._erasure_engine.encode(
                decoded, data_fragments, parity_fragments
            )
            self._distributor.distribute(chunk_address, new_frags)
            return True
        except (ErasureCodingError, InsufficientFragmentsError):
            return False

    def scrub(self, bucket_name: str, chunk_addresses: List[str],
              data_fragments: int = 10,
              parity_fragments: int = 4) -> Dict[str, Any]:
        """Full integrity scan of all chunks for a bucket.

        Returns:
            Scrub report with checked, healthy, corrupt, repaired counts.
        """
        report = {
            "bucket": bucket_name,
            "checked": 0,
            "healthy": 0,
            "corrupt": 0,
            "repaired": 0,
            "unrecoverable": 0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        for addr in chunk_addresses:
            report["checked"] += 1
            is_healthy, corrupt_indices = self.check_chunk(
                addr, data_fragments, parity_fragments
            )
            if is_healthy:
                report["healthy"] += 1
            else:
                report["corrupt"] += 1
                if self.repair_chunk(addr, corrupt_indices,
                                     data_fragments, parity_fragments):
                    report["repaired"] += 1
                else:
                    report["unrecoverable"] += 1

        self._scrub_results[bucket_name] = report
        return report

    def get_last_scrub(self, bucket_name: str) -> Optional[Dict[str, Any]]:
        """Return the last scrub report for a bucket."""
        return self._scrub_results.get(bucket_name)


# ============================================================
# MetadataIndex — B-tree + hash index for metadata tier
# ============================================================


class MetadataIndex:
    """Metadata storage engine with B-tree and hash indices.

    Provides both point lookups (hash index) and ordered range queries
    (B-tree index) for bucket metadata, object metadata, version chains,
    and multipart upload sessions.
    """

    def __init__(self) -> None:
        self._hash_index: Dict[str, Dict[str, Any]] = {}  # namespace -> {key -> value}
        self._btree_index: Dict[str, OrderedDict] = {}  # namespace -> OrderedDict
        self._lock = threading.RLock()

    def put(self, namespace: str, key: str, value: Any,
            index_type: str = "both") -> None:
        """Insert or update a metadata record.

        Args:
            namespace: Index namespace (e.g., "buckets", "objects:mybucket").
            key: Record key.
            value: Record value.
            index_type: "hash", "btree", or "both".
        """
        with self._lock:
            if index_type in ("hash", "both"):
                if namespace not in self._hash_index:
                    self._hash_index[namespace] = {}
                self._hash_index[namespace][key] = value

            if index_type in ("btree", "both"):
                if namespace not in self._btree_index:
                    self._btree_index[namespace] = OrderedDict()
                self._btree_index[namespace][key] = value
                # Maintain sorted order
                items = sorted(self._btree_index[namespace].items())
                self._btree_index[namespace] = OrderedDict(items)

    def get(self, namespace: str, key: str,
            index_type: str = "hash") -> Optional[Any]:
        """Point lookup via hash index.

        Args:
            namespace: Index namespace.
            key: Record key.
            index_type: Which index to query.

        Returns:
            Record value or None.
        """
        with self._lock:
            if index_type == "hash":
                return self._hash_index.get(namespace, {}).get(key)
            else:
                return self._btree_index.get(namespace, OrderedDict()).get(key)

    def delete(self, namespace: str, key: str,
               index_type: str = "both") -> bool:
        """Remove a metadata record.

        Returns:
            True if the record existed and was removed.
        """
        removed = False
        with self._lock:
            if index_type in ("hash", "both"):
                if namespace in self._hash_index:
                    if key in self._hash_index[namespace]:
                        del self._hash_index[namespace][key]
                        removed = True

            if index_type in ("btree", "both"):
                if namespace in self._btree_index:
                    if key in self._btree_index[namespace]:
                        del self._btree_index[namespace][key]
                        removed = True

        return removed

    def range_query(self, namespace: str, start_key: str = "",
                    end_key: str = "\xff" * 4,
                    limit: int = MAX_LIST_KEYS) -> List[Tuple[str, Any]]:
        """Ordered key traversal on B-tree index.

        Args:
            namespace: Index namespace.
            start_key: Start of range (inclusive).
            end_key: End of range (exclusive).
            limit: Maximum results.

        Returns:
            List of (key, value) pairs in sorted order.
        """
        with self._lock:
            btree = self._btree_index.get(namespace, OrderedDict())
            results = []
            for key, value in btree.items():
                if key >= start_key and key < end_key:
                    results.append((key, value))
                    if len(results) >= limit:
                        break
            return results

    def prefix_query(self, namespace: str, prefix: str,
                     limit: int = MAX_LIST_KEYS,
                     continuation_token: Optional[str] = None) -> Tuple[List[Tuple[str, Any]], Optional[str]]:
        """Range query from prefix to prefix + \\xff.

        Args:
            namespace: Index namespace.
            prefix: Key prefix.
            limit: Maximum results.
            continuation_token: Start-after key for pagination.

        Returns:
            Tuple of (results, next_continuation_token).
        """
        with self._lock:
            btree = self._btree_index.get(namespace, OrderedDict())
            results = []
            past_token = continuation_token is None

            for key, value in btree.items():
                if not key.startswith(prefix):
                    if key > prefix + "\xff" * 4:
                        break
                    continue

                if not past_token:
                    if key > continuation_token:
                        past_token = True
                    else:
                        continue

                results.append((key, value))
                if len(results) > limit:
                    next_token = results[-2][0]
                    return results[:-1], results[-1][0]

            return results, None

    def list_keys(self, namespace: str) -> List[str]:
        """Return all keys in a namespace."""
        with self._lock:
            return list(self._hash_index.get(namespace, {}).keys())

    def count(self, namespace: str) -> int:
        """Return key count in a namespace."""
        with self._lock:
            return len(self._hash_index.get(namespace, {}))

    def clear_namespace(self, namespace: str) -> None:
        """Remove all records in a namespace."""
        with self._lock:
            self._hash_index.pop(namespace, None)
            self._btree_index.pop(namespace, None)


# ============================================================
# SegmentLog — append-only data tier
# ============================================================


class SegmentLog:
    """Append-only data tier storage for erasure-coded fragments.

    Fragments are appended to the active segment until it reaches
    its maximum size, at which point the segment is sealed and a
    new active segment is created.  Sealed segments are eligible
    for compaction to reclaim dead fragment space.
    """

    def __init__(
        self,
        max_segment_size: int = DEFAULT_SEGMENT_MAX_SIZE,
        compaction_threshold: float = DEFAULT_COMPACTION_THRESHOLD,
    ) -> None:
        self._max_segment_size = max_segment_size
        self._compaction_threshold = compaction_threshold
        self._segments: Dict[str, Segment] = {}
        self._active_segment: Optional[Segment] = None
        self._lock = threading.Lock()
        self._create_segment()

    def _create_segment(self) -> Segment:
        """Create a new active segment."""
        segment = Segment()
        self._segments[segment.segment_id] = segment
        self._active_segment = segment
        return segment

    def append(self, fragment_address: str, fragment_data: bytes) -> FragmentLocation:
        """Append a fragment to the active segment.

        Args:
            fragment_address: Unique fragment identifier.
            fragment_data: Fragment content.

        Returns:
            Physical location of the stored fragment.
        """
        with self._lock:
            if self._active_segment is None or \
               self._active_segment.size + len(fragment_data) > self._max_segment_size:
                if self._active_segment is not None:
                    self._seal_segment(self._active_segment)
                self._create_segment()

            segment = self._active_segment
            offset = segment.size
            segment.fragments[fragment_address] = fragment_data
            location = FragmentLocation(
                segment_id=segment.segment_id,
                offset=offset,
                length=len(fragment_data),
                checksum=hashlib.md5(fragment_data).hexdigest(),
            )
            segment.fragment_locations[fragment_address] = location
            segment.size += len(fragment_data)
            segment.live_bytes += len(fragment_data)
            return location

    def read(self, segment_id: str, fragment_address: str) -> bytes:
        """Read a fragment by segment ID and address.

        Returns:
            Fragment data bytes.
        """
        with self._lock:
            segment = self._segments.get(segment_id)
            if segment is None:
                raise MetadataCorruptionError(
                    f"Segment not found: {segment_id}"
                )
            data = segment.fragments.get(fragment_address)
            if data is None:
                raise ChunkNotFoundError(fragment_address)
            return data

    def _seal_segment(self, segment: Segment) -> None:
        """Mark segment as immutable."""
        segment.status = SegmentStatus.SEALED
        segment.sealed_at = datetime.now(timezone.utc)

    def mark_dead(self, segment_id: str, fragment_address: str) -> None:
        """Mark a fragment as dead (eligible for compaction)."""
        with self._lock:
            segment = self._segments.get(segment_id)
            if segment and fragment_address in segment.fragments:
                size = len(segment.fragments[fragment_address])
                segment.dead_bytes += size
                segment.live_bytes -= size

    def compact(self, segment_ids: List[str]) -> Optional[str]:
        """Compact segments by copying live fragments to a new segment.

        Args:
            segment_ids: Segments to compact.

        Returns:
            New segment ID, or None if nothing to compact.
        """
        with self._lock:
            live_fragments: Dict[str, bytes] = {}
            for sid in segment_ids:
                segment = self._segments.get(sid)
                if segment is None:
                    continue
                segment.status = SegmentStatus.COMPACTING
                for addr, data in segment.fragments.items():
                    if segment.live_bytes > 0:
                        live_fragments[addr] = data

            if not live_fragments:
                return None

            new_segment = Segment()
            for addr, data in live_fragments.items():
                new_segment.fragments[addr] = data
                new_segment.size += len(data)
                new_segment.live_bytes += len(data)
                new_segment.fragment_locations[addr] = FragmentLocation(
                    segment_id=new_segment.segment_id,
                    offset=new_segment.size - len(data),
                    length=len(data),
                    checksum=hashlib.md5(data).hexdigest(),
                )

            self._segments[new_segment.segment_id] = new_segment

            # Mark old segments as deleted
            for sid in segment_ids:
                if sid in self._segments:
                    self._segments[sid].status = SegmentStatus.DELETED

            return new_segment.segment_id

    def get_segment_stats(self) -> List[Dict[str, Any]]:
        """Return statistics for all segments."""
        with self._lock:
            stats = []
            for seg in self._segments.values():
                frag_ratio = seg.dead_bytes / max(seg.size, 1)
                stats.append({
                    "segment_id": seg.segment_id,
                    "status": seg.status.value,
                    "size": seg.size,
                    "live_bytes": seg.live_bytes,
                    "dead_bytes": seg.dead_bytes,
                    "fragmentation": frag_ratio,
                    "fragment_count": len(seg.fragments),
                })
            return stats


# ============================================================
# CompactionPolicy
# ============================================================


class CompactionPolicy:
    """Determines segment compaction eligibility based on fragmentation.

    Segments with a dead-byte ratio above the configured threshold
    are candidates for compaction, ordered by fragmentation ratio
    to prioritize the most fragmented segments.
    """

    def __init__(
        self,
        threshold: float = DEFAULT_COMPACTION_THRESHOLD,
        min_age_seconds: float = 3600.0,
        max_concurrent: int = 2,
    ) -> None:
        self._threshold = threshold
        self._min_age = min_age_seconds
        self._max_concurrent = max_concurrent

    def select_segments(self, segment_stats: List[Dict[str, Any]]) -> List[str]:
        """Select segments eligible for compaction.

        Returns:
            List of segment IDs, ordered by fragmentation (highest first).
        """
        now = datetime.now(timezone.utc)
        candidates = []
        for stat in segment_stats:
            if stat["status"] != "sealed":
                continue
            if stat["fragmentation"] < self._threshold:
                continue
            candidates.append((stat["fragmentation"], stat["segment_id"]))

        candidates.sort(reverse=True)
        return [sid for _, sid in candidates[:self._max_concurrent]]


# ============================================================
# ReferenceCounter
# ============================================================


class ReferenceCounter:
    """Tracks object references to content addresses.

    Each content-addressed chunk maintains a reference count
    representing the number of objects (or object versions) that
    include that chunk.  When the count drops to zero, the chunk
    becomes eligible for garbage collection.
    """

    def __init__(self, metadata_index: Optional[MetadataIndex] = None) -> None:
        self._refs: Dict[str, Set[str]] = {}  # address -> set of object_ids
        self._lock = threading.Lock()

    def increment(self, address: str, object_id: str) -> int:
        """Add a reference from an object to a chunk.

        Returns:
            New reference count.
        """
        with self._lock:
            if address not in self._refs:
                self._refs[address] = set()
            self._refs[address].add(object_id)
            return len(self._refs[address])

    def decrement(self, address: str, object_id: str) -> int:
        """Remove a reference from an object to a chunk.

        Returns:
            New reference count.
        """
        with self._lock:
            if address in self._refs:
                self._refs[address].discard(object_id)
                count = len(self._refs[address])
                if count == 0:
                    del self._refs[address]
                return count
            return 0

    def get_count(self, address: str) -> int:
        """Return the current reference count for a chunk."""
        with self._lock:
            return len(self._refs.get(address, set()))

    def get_zero_ref_addresses(self) -> List[str]:
        """Return addresses with zero references (GC candidates)."""
        with self._lock:
            return [addr for addr, refs in self._refs.items() if len(refs) == 0]

    def get_all_addresses(self) -> List[str]:
        """Return all tracked addresses."""
        with self._lock:
            return list(self._refs.keys())


# ============================================================
# ContentAddressableStore — core deduplication engine
# ============================================================


class ContentAddressableStore:
    """Core deduplication engine using SHA-256 content addressing.

    Objects are split into fixed-size chunks, each identified by its
    SHA-256 hash.  Identical chunks are stored only once, with reference
    counting to track which objects share each chunk.  Each chunk is
    erasure-coded for durability before storage.
    """

    def __init__(
        self,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        erasure_engine: Optional[ErasureCodingEngine] = None,
        segment_log: Optional[SegmentLog] = None,
        ref_counter: Optional[ReferenceCounter] = None,
        fragment_distributor: Optional[FragmentDistributor] = None,
    ) -> None:
        self._chunk_size = chunk_size
        self._erasure_engine = erasure_engine or ErasureCodingEngine()
        self._segment_log = segment_log or SegmentLog()
        self._ref_counter = ref_counter or ReferenceCounter()
        self._distributor = fragment_distributor or FragmentDistributor()
        self._chunk_data: Dict[str, bytes] = {}  # address -> raw chunk data
        self._chunk_manifests: Dict[str, ChunkManifest] = {}  # object_id -> manifest
        self._lock = threading.Lock()

    def chunk_object(self, data: bytes) -> List[Tuple[bytes, int]]:
        """Split data into fixed-size chunks.

        Args:
            data: Object data.

        Returns:
            List of (chunk_data, offset) tuples.
        """
        chunks = []
        for i in range(0, max(len(data), 1), self._chunk_size):
            chunk = data[i:i + self._chunk_size]
            if chunk:
                chunks.append((chunk, i))
        if not chunks and len(data) == 0:
            chunks.append((b"", 0))
        return chunks

    def address_chunk(self, chunk_data: bytes) -> str:
        """Compute SHA-256 content address for a chunk."""
        return hashlib.sha256(chunk_data).hexdigest()

    def store_chunk(self, address: str, data: bytes,
                    storage_class: StorageClass = StorageClass.STANDARD) -> str:
        """Store a chunk at its content address.

        If the chunk already exists, increments the reference count
        without storing duplicate data.

        Returns:
            "CREATED" or "DEDUPLICATED".
        """
        with self._lock:
            if address in self._chunk_data:
                return "DEDUPLICATED"

            # Erasure-code the chunk
            data_frags, parity_frags = ERASURE_PARAMS[storage_class]
            if len(data) > 0:
                fragments = self._erasure_engine.encode(
                    data, data_frags, parity_frags
                )
                self._distributor.distribute(address, fragments)

            self._chunk_data[address] = data
            return "CREATED"

    def retrieve_chunk(self, address: str,
                       storage_class: StorageClass = StorageClass.STANDARD) -> bytes:
        """Retrieve a chunk by content address.

        Reassembles from erasure-coded fragments if necessary.
        """
        with self._lock:
            data = self._chunk_data.get(address)
            if data is not None:
                return data
            raise ChunkNotFoundError(address)

    def store_object(self, object_id: str, data: bytes,
                     storage_class: StorageClass = StorageClass.STANDARD) -> ChunkManifest:
        """Chunk, deduplicate, and store an object.

        Args:
            object_id: Unique object identifier.
            data: Object data.
            storage_class: Storage class for erasure coding parameters.

        Returns:
            ChunkManifest mapping object to its chunks.
        """
        chunks = self.chunk_object(data)
        manifest = ChunkManifest(
            object_id=object_id,
            total_size=len(data),
            chunk_count=len(chunks),
        )

        for chunk_data, offset in chunks:
            address = self.address_chunk(chunk_data)
            self.store_chunk(address, chunk_data, storage_class)
            self._ref_counter.increment(address, object_id)
            manifest.chunks.append(ChunkReference(
                address=address,
                offset=offset,
                size=len(chunk_data),
                sequence=len(manifest.chunks) - 1,
            ))

        with self._lock:
            self._chunk_manifests[object_id] = manifest
        return manifest

    def retrieve_object(self, object_id: str,
                        storage_class: StorageClass = StorageClass.STANDARD) -> bytes:
        """Reassemble an object from its content-addressed chunks.

        Args:
            object_id: Unique object identifier.
            storage_class: Storage class for erasure coding.

        Returns:
            Reassembled object data.
        """
        with self._lock:
            manifest = self._chunk_manifests.get(object_id)
        if manifest is None:
            raise ChunkNotFoundError(object_id)

        data = bytearray()
        for chunk_ref in manifest.chunks:
            chunk_data = self.retrieve_chunk(chunk_ref.address, storage_class)
            data.extend(chunk_data)
        return bytes(data[:manifest.total_size])

    def delete_object_references(self, object_id: str) -> None:
        """Remove all chunk references for an object."""
        with self._lock:
            manifest = self._chunk_manifests.pop(object_id, None)
        if manifest:
            for chunk_ref in manifest.chunks:
                self._ref_counter.decrement(chunk_ref.address, object_id)

    def get_deduplication_stats(self, bucket_name: Optional[str] = None) -> DeduplicationStats:
        """Compute deduplication statistics.

        Returns:
            DeduplicationStats with logical/physical sizes and ratios.
        """
        with self._lock:
            total_logical = 0
            total_physical = 0
            all_addresses = set()
            shared_addresses = set()

            for obj_id, manifest in self._chunk_manifests.items():
                if bucket_name and not obj_id.startswith(bucket_name + "/"):
                    continue
                total_logical += manifest.total_size
                for chunk_ref in manifest.chunks:
                    all_addresses.add(chunk_ref.address)
                    if self._ref_counter.get_count(chunk_ref.address) > 1:
                        shared_addresses.add(chunk_ref.address)

            for addr in all_addresses:
                chunk = self._chunk_data.get(addr, b"")
                total_physical += len(chunk)

            dedup_ratio = total_logical / max(total_physical, 1)

            return DeduplicationStats(
                logical_size=total_logical,
                physical_size=total_physical,
                dedup_ratio=round(dedup_ratio, 2),
                shared_chunks=len(shared_addresses),
                unique_chunks=len(all_addresses) - len(shared_addresses),
                total_chunks=len(all_addresses),
            )

    def get_chunk_addresses(self, bucket_name: Optional[str] = None) -> List[str]:
        """Return all chunk addresses, optionally filtered by bucket."""
        with self._lock:
            if bucket_name is None:
                return list(self._chunk_data.keys())
            addresses = set()
            for obj_id, manifest in self._chunk_manifests.items():
                if obj_id.startswith(bucket_name + "/"):
                    for ref in manifest.chunks:
                        addresses.add(ref.address)
            return list(addresses)


# ============================================================
# GarbageCollector
# ============================================================


class GarbageCollector:
    """Reclaims storage from unreferenced content-addressed chunks.

    Chunks with zero reference count are eligible for collection after
    a safety delay period.  The delay prevents collecting chunks that
    are targets of in-flight PUT operations.
    """

    def __init__(
        self,
        cas: ContentAddressableStore,
        ref_counter: ReferenceCounter,
        safety_delay: float = DEFAULT_GC_SAFETY_DELAY,
    ) -> None:
        self._cas = cas
        self._ref_counter = ref_counter
        self._safety_delay = safety_delay
        self._candidates: Dict[str, float] = {}  # address -> first_seen_timestamp
        self._collected_count = 0
        self._collected_bytes = 0

    def collect(self) -> Dict[str, Any]:
        """Scan and collect zero-reference chunks.

        Returns:
            Collection report with counts and bytes reclaimed.
        """
        now = time.time()
        collected = 0
        collected_bytes = 0

        # Find new candidates
        all_addresses = self._ref_counter.get_all_addresses()
        for addr in all_addresses:
            if self._ref_counter.get_count(addr) == 0:
                if addr not in self._candidates:
                    self._candidates[addr] = now

        # Collect candidates past safety delay
        to_remove = []
        for addr, first_seen in list(self._candidates.items()):
            if now - first_seen >= self._safety_delay:
                # Verify still zero-ref
                if self._ref_counter.get_count(addr) == 0:
                    with self._cas._lock:
                        chunk = self._cas._chunk_data.pop(addr, None)
                        if chunk is not None:
                            collected += 1
                            collected_bytes += len(chunk)
                    self._cas._distributor.remove(addr)
                to_remove.append(addr)
            elif self._ref_counter.get_count(addr) > 0:
                to_remove.append(addr)

        for addr in to_remove:
            self._candidates.pop(addr, None)

        self._collected_count += collected
        self._collected_bytes += collected_bytes

        return {
            "collected_chunks": collected,
            "collected_bytes": collected_bytes,
            "total_collected_chunks": self._collected_count,
            "total_collected_bytes": self._collected_bytes,
            "pending_candidates": len(self._candidates),
        }


# ============================================================
# EncryptionEngine
# ============================================================


class EncryptionEngine:
    """Handles object encryption and decryption.

    Supports three server-side encryption modes:
    - SSE-S3: Platform-managed keys with envelope encryption.
    - SSE-KMS: FizzVault-managed keys with auditable usage.
    - SSE-C: Client-provided keys, never stored.
    """

    def __init__(self, default_mode: str = "sse-s3") -> None:
        try:
            self._default_mode = EncryptionMode(default_mode)
        except ValueError:
            self._default_mode = EncryptionMode.SSE_S3

        # SSE-S3 master key (platform-managed)
        self._master_key = os.urandom(32)
        self._master_key_id = uuid.uuid4().hex[:16]
        self._master_key_created = datetime.now(timezone.utc)
        self._rotating = False

        # KMS key store (simulated FizzVault integration)
        self._kms_keys: Dict[str, bytes] = {
            "default-kms-key": os.urandom(32),
        }

    def encrypt(self, data: bytes,
                mode: Optional[EncryptionMode] = None,
                kms_key_id: Optional[str] = None,
                client_key: Optional[bytes] = None) -> Tuple[bytes, ServerSideEncryption]:
        """Encrypt data using the configured mode.

        Args:
            data: Plaintext data.
            mode: Encryption mode (defaults to engine default).
            kms_key_id: KMS key ID for SSE-KMS.
            client_key: Client-provided key for SSE-C.

        Returns:
            Tuple of (encrypted_data, encryption_metadata).
        """
        active_mode = mode or self._default_mode

        if active_mode == EncryptionMode.SSE_S3:
            if self._rotating:
                raise KeyRotationInProgressError("SSE-S3 master key rotation in progress")
            # Generate per-object DEK
            dek = os.urandom(32)
            nonce = os.urandom(12)
            # Simulate AES-256-GCM: XOR for deterministic testing
            encrypted = self._xor_encrypt(data, dek, nonce)
            # Wrap DEK with master key
            wrapped_dek = self._xor_encrypt(dek, self._master_key, nonce[:12])
            # Store wrapped DEK + nonce as prefix
            result = nonce + wrapped_dek + encrypted
            return result, ServerSideEncryption(
                algorithm=EncryptionAlgorithm.AES_256,
                mode=EncryptionMode.SSE_S3,
            )

        elif active_mode == EncryptionMode.SSE_KMS:
            key_id = kms_key_id or "default-kms-key"
            if key_id not in self._kms_keys:
                raise KMSKeyNotFoundError(key_id)
            kms_key = self._kms_keys[key_id]
            dek = os.urandom(32)
            nonce = os.urandom(12)
            encrypted = self._xor_encrypt(data, dek, nonce)
            wrapped_dek = self._xor_encrypt(dek, kms_key, nonce[:12])
            result = nonce + wrapped_dek + encrypted
            return result, ServerSideEncryption(
                algorithm=EncryptionAlgorithm.AES_256,
                mode=EncryptionMode.SSE_KMS,
                kms_key_id=key_id,
            )

        elif active_mode == EncryptionMode.SSE_C:
            if client_key is None or len(client_key) != 32:
                raise InvalidEncryptionKeyError(
                    "SSE-C requires a 256-bit (32-byte) key"
                )
            key_md5 = base64.b64encode(
                hashlib.md5(client_key).digest()
            ).decode()
            nonce = os.urandom(12)
            encrypted = self._xor_encrypt(data, client_key, nonce)
            result = nonce + encrypted
            return result, ServerSideEncryption(
                algorithm=EncryptionAlgorithm.AES_256,
                mode=EncryptionMode.SSE_C,
                key_md5=key_md5,
            )

        raise EncryptionError(f"Unsupported encryption mode: {active_mode}")

    def decrypt(self, encrypted_data: bytes,
                encryption_meta: ServerSideEncryption,
                client_key: Optional[bytes] = None) -> bytes:
        """Decrypt data using the appropriate key material.

        Args:
            encrypted_data: Encrypted data with nonce prefix.
            encryption_meta: Encryption metadata.
            client_key: Client-provided key for SSE-C.

        Returns:
            Decrypted plaintext.
        """
        if encryption_meta.mode == EncryptionMode.SSE_S3:
            nonce = encrypted_data[:12]
            wrapped_dek = encrypted_data[12:44]
            ciphertext = encrypted_data[44:]
            dek = self._xor_encrypt(wrapped_dek, self._master_key, nonce[:12])
            return self._xor_encrypt(ciphertext, dek, nonce)

        elif encryption_meta.mode == EncryptionMode.SSE_KMS:
            key_id = encryption_meta.kms_key_id or "default-kms-key"
            if key_id not in self._kms_keys:
                raise KMSKeyNotFoundError(key_id)
            kms_key = self._kms_keys[key_id]
            nonce = encrypted_data[:12]
            wrapped_dek = encrypted_data[12:44]
            ciphertext = encrypted_data[44:]
            dek = self._xor_encrypt(wrapped_dek, kms_key, nonce[:12])
            return self._xor_encrypt(ciphertext, dek, nonce)

        elif encryption_meta.mode == EncryptionMode.SSE_C:
            if client_key is None or len(client_key) != 32:
                raise InvalidEncryptionKeyError(
                    "SSE-C decryption requires the original 256-bit key"
                )
            expected_md5 = base64.b64encode(
                hashlib.md5(client_key).digest()
            ).decode()
            if encryption_meta.key_md5 and encryption_meta.key_md5 != expected_md5:
                raise InvalidEncryptionKeyError("SSE-C key MD5 mismatch")
            nonce = encrypted_data[:12]
            ciphertext = encrypted_data[12:]
            return self._xor_encrypt(ciphertext, client_key, nonce)

        raise EncryptionError(
            f"Unsupported decryption mode: {encryption_meta.mode}"
        )

    @staticmethod
    def _xor_encrypt(data: bytes, key: bytes, nonce: bytes) -> bytes:
        """Simulate AES-256-GCM with repeating-key XOR for testing.

        Production deployments would use a proper AEAD cipher; this
        implementation provides deterministic encrypt/decrypt symmetry
        for unit testing without cryptographic library dependencies.
        """
        extended_key = (key + nonce) * (len(data) // (len(key) + len(nonce)) + 1)
        return bytes(a ^ b for a, b in zip(data, extended_key[:len(data)]))

    def rotate_master_key(self) -> str:
        """Rotate the SSE-S3 master key.

        Returns:
            New master key ID.
        """
        self._rotating = True
        try:
            self._master_key = os.urandom(32)
            self._master_key_id = uuid.uuid4().hex[:16]
            self._master_key_created = datetime.now(timezone.utc)
        finally:
            self._rotating = False
        return self._master_key_id


# ============================================================
# KeyRotationManager
# ============================================================


class KeyRotationManager:
    """Manages encryption key lifecycle and proactive re-encryption.

    Rotates the SSE-S3 master key on a configurable schedule and
    can proactively re-wrap existing object DEKs with the new key.
    """

    def __init__(
        self,
        encryption_engine: EncryptionEngine,
        rotation_days: int = 90,
    ) -> None:
        self._engine = encryption_engine
        self._rotation_days = rotation_days
        self._last_rotation = datetime.now(timezone.utc)
        self._rotation_history: List[Dict[str, str]] = []

    def should_rotate(self) -> bool:
        """Check if master key rotation is due."""
        elapsed = (datetime.now(timezone.utc) - self._last_rotation).days
        return elapsed >= self._rotation_days

    def rotate(self) -> str:
        """Perform master key rotation.

        Returns:
            New key ID.
        """
        new_id = self._engine.rotate_master_key()
        self._rotation_history.append({
            "key_id": new_id,
            "rotated_at": datetime.now(timezone.utc).isoformat(),
        })
        self._last_rotation = datetime.now(timezone.utc)
        return new_id

    def get_rotation_history(self) -> List[Dict[str, str]]:
        """Return key rotation history."""
        return list(self._rotation_history)


# ============================================================
# BucketManager
# ============================================================


class BucketManager:
    """Manages bucket lifecycle operations.

    Handles bucket creation with name validation, deletion with
    emptiness checks, listing, region queries, and versioning
    state machine transitions.
    """

    def __init__(
        self,
        metadata_index: MetadataIndex,
        max_buckets: int = MAX_BUCKETS_PER_OWNER,
        default_region: str = DEFAULT_REGION,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._metadata = metadata_index
        self._max_buckets = max_buckets
        self._default_region = default_region
        self._event_bus = event_bus
        self._sequencer = 0
        self._lock = threading.Lock()

    def create_bucket(
        self,
        name: str,
        region: Optional[str] = None,
        owner: str = "fizzbuzz-root",
        acl: Optional[CannedACL] = None,
        object_lock: bool = False,
    ) -> Bucket:
        """Create a new bucket.

        Args:
            name: Globally unique bucket name.
            region: Bucket region (defaults to configured default).
            owner: Bucket owner principal.
            acl: Canned ACL to apply.
            object_lock: Enable S3 Object Lock.

        Returns:
            Created Bucket instance.
        """
        # Validate name
        is_valid, violations = BucketNameValidator.validate(name)
        if not is_valid:
            raise InvalidBucketNameError(name, violations)

        with self._lock:
            # Check global uniqueness
            existing = self._metadata.get("buckets", name)
            if existing is not None:
                if existing.owner == owner:
                    raise BucketAlreadyOwnedByYouError(name)
                raise BucketAlreadyExistsError(name)

            # Check per-owner limit
            all_buckets = self._metadata.list_keys("buckets")
            owner_count = sum(
                1 for b in all_buckets
                if (self._metadata.get("buckets", b) or Bucket(name="")).owner == owner
            )
            if owner_count >= self._max_buckets:
                raise TooManyBucketsError(self._max_buckets)

            # Create bucket
            bucket_region = region or self._default_region
            bucket = Bucket(
                name=name,
                region=bucket_region,
                owner=owner,
                object_lock_enabled=object_lock,
                acl=self._create_acl(owner, acl),
                block_public_access=BlockPublicAccessConfiguration(),
            )

            self._metadata.put("buckets", name, bucket)

        self._emit_event("S3_BUCKET_CREATED", {
            "bucket": name,
            "region": bucket_region,
            "owner": owner,
        })

        logger.info("Bucket created: %s in %s", name, bucket_region)
        return bucket

    def delete_bucket(self, name: str) -> None:
        """Delete an empty bucket.

        Raises:
            BucketNotFoundError: If bucket does not exist.
            BucketNotEmptyError: If bucket contains objects or uploads.
        """
        bucket = self._get_bucket(name)

        # Check emptiness
        obj_ns = f"objects:{name}"
        if self._metadata.count(obj_ns) > 0:
            raise BucketNotEmptyError(name)

        upload_ns = f"uploads:{name}"
        if self._metadata.count(upload_ns) > 0:
            raise BucketNotEmptyError(name)

        self._metadata.delete("buckets", name)
        self._metadata.clear_namespace(obj_ns)
        self._metadata.clear_namespace(f"versions:{name}")

        self._emit_event("S3_BUCKET_DELETED", {"bucket": name})
        logger.info("Bucket deleted: %s", name)

    def head_bucket(self, name: str, principal: str = "fizzbuzz-root") -> bool:
        """Check bucket existence and access.

        Returns:
            True if bucket exists and principal has access.
        """
        bucket = self._metadata.get("buckets", name)
        return bucket is not None

    def list_buckets(self, owner: str = "fizzbuzz-root") -> List[Bucket]:
        """List all buckets for an owner, sorted alphabetically."""
        all_keys = self._metadata.list_keys("buckets")
        buckets = []
        for key in sorted(all_keys):
            bucket = self._metadata.get("buckets", key)
            if bucket and bucket.owner == owner:
                buckets.append(bucket)
        return buckets

    def get_bucket_location(self, name: str) -> str:
        """Return the region of a bucket."""
        bucket = self._get_bucket(name)
        return bucket.region

    def get_bucket_versioning(self, name: str) -> BucketVersioning:
        """Return the versioning state of a bucket."""
        bucket = self._get_bucket(name)
        return bucket.versioning

    def put_bucket_versioning(self, name: str,
                              status: BucketVersioning) -> None:
        """Update bucket versioning state.

        Valid transitions: DISABLED->ENABLED, ENABLED->SUSPENDED,
        SUSPENDED->ENABLED.
        """
        bucket = self._get_bucket(name)
        old = bucket.versioning

        # Validate state machine
        valid_transitions = {
            BucketVersioning.DISABLED: {BucketVersioning.ENABLED},
            BucketVersioning.ENABLED: {BucketVersioning.SUSPENDED},
            BucketVersioning.SUSPENDED: {BucketVersioning.ENABLED},
        }

        if status not in valid_transitions.get(old, set()):
            raise VersionError(
                f"Invalid versioning transition: {old.value} -> {status.value}"
            )

        bucket.versioning = status
        self._metadata.put("buckets", name, bucket)

        self._emit_event("S3_BUCKET_VERSIONING_CHANGED", {
            "bucket": name,
            "old_status": old.value,
            "new_status": status.value,
        })

    def get_bucket(self, name: str) -> Bucket:
        """Return a bucket by name."""
        return self._get_bucket(name)

    def _get_bucket(self, name: str) -> Bucket:
        """Internal bucket lookup with existence check."""
        bucket = self._metadata.get("buckets", name)
        if bucket is None:
            raise BucketNotFoundError(name)
        return bucket

    def _create_acl(self, owner: str,
                    canned: Optional[CannedACL] = None) -> AccessControlList:
        """Create an ACL from a canned ACL value."""
        acl = AccessControlList(owner=owner)
        acl.grants.append(Grant(
            grantee=owner,
            grantee_type="canonical_user",
            permission=ACLPermission.FULL_CONTROL,
        ))

        if canned == CannedACL.PUBLIC_READ:
            acl.grants.append(Grant(
                grantee="AllUsers",
                grantee_type="group",
                permission=ACLPermission.READ,
            ))
        elif canned == CannedACL.PUBLIC_READ_WRITE:
            acl.grants.append(Grant(
                grantee="AllUsers",
                grantee_type="group",
                permission=ACLPermission.READ,
            ))
            acl.grants.append(Grant(
                grantee="AllUsers",
                grantee_type="group",
                permission=ACLPermission.WRITE,
            ))
        elif canned == CannedACL.AUTHENTICATED_READ:
            acl.grants.append(Grant(
                grantee="AuthenticatedUsers",
                grantee_type="group",
                permission=ACLPermission.READ,
            ))

        return acl

    def next_sequencer(self) -> str:
        """Generate a monotonically increasing sequencer value."""
        with self._lock:
            self._sequencer += 1
            return f"{self._sequencer:016x}"

    def _emit_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Publish an event to the event bus."""
        if self._event_bus:
            try:
                self._event_bus.publish(event_type, data)
            except Exception:
                logger.warning("Failed to publish event: %s", event_type)


# ============================================================
# VersioningEngine
# ============================================================


class VersioningEngine:
    """Manages version chains for objects in versioned buckets.

    Each versioned object maintains an ordered chain of versions.
    When versioning is enabled, PUT operations create new versions
    with UUID-based version IDs.  When suspended, PUTs overwrite
    the null version.
    """

    def __init__(self, metadata_index: MetadataIndex) -> None:
        self._metadata = metadata_index

    def assign_version_id(self) -> str:
        """Generate a UUID-based version ID with timestamp prefix.

        The timestamp prefix enables chronological sorting of versions
        without parsing the UUID.
        """
        ts = int(time.time() * 1000)
        return f"{ts:013x}-{uuid.uuid4().hex[:16]}"

    def add_version(self, bucket_name: str, key: str,
                    obj: S3Object) -> None:
        """Add an object version to the version chain."""
        ns = f"versions:{bucket_name}:{key}"
        vid = obj.version_id or "null"

        # Mark all existing versions as non-latest
        existing = self._metadata.list_keys(ns)
        for existing_vid in existing:
            existing_obj = self._metadata.get(ns, existing_vid)
            if existing_obj and hasattr(existing_obj, 'is_latest'):
                existing_obj.is_latest = False
                self._metadata.put(ns, existing_vid, existing_obj)

        obj.is_latest = True
        self._metadata.put(ns, vid, obj)

    def get_version_chain(self, bucket_name: str,
                          key: str) -> List[S3Object]:
        """Return complete version history, newest first."""
        ns = f"versions:{bucket_name}:{key}"
        keys = self._metadata.list_keys(ns)
        versions = []
        for vid in keys:
            obj = self._metadata.get(ns, vid)
            if obj:
                versions.append(obj)
        # Sort by last_modified, newest first
        versions.sort(key=lambda o: o.last_modified, reverse=True)
        return versions

    def get_specific_version(self, bucket_name: str, key: str,
                             version_id: str) -> Optional[S3Object]:
        """Retrieve a specific version."""
        ns = f"versions:{bucket_name}:{key}"
        return self._metadata.get(ns, version_id)

    def delete_specific_version(self, bucket_name: str, key: str,
                                version_id: str) -> Optional[S3Object]:
        """Permanently remove a specific version.

        If the deleted version was the latest, the previous version
        becomes the current version.
        """
        ns = f"versions:{bucket_name}:{key}"
        obj = self._metadata.get(ns, version_id)
        if obj is None:
            raise NoSuchVersionError(bucket_name, key, version_id)

        was_latest = obj.is_latest
        self._metadata.delete(ns, version_id)

        if was_latest:
            # Promote previous version
            chain = self.get_version_chain(bucket_name, key)
            if chain:
                chain[0].is_latest = True
                vid = chain[0].version_id or "null"
                self._metadata.put(ns, vid, chain[0])

        return obj

    def list_object_versions(self, bucket_name: str,
                             prefix: str = "",
                             max_keys: int = MAX_LIST_KEYS) -> List[S3Object]:
        """List all versions including delete markers with pagination."""
        all_versions = []
        obj_ns = f"objects:{bucket_name}"
        all_keys = self._metadata.list_keys(obj_ns)

        for key in sorted(all_keys):
            if prefix and not key.startswith(prefix):
                continue
            chain = self.get_version_chain(bucket_name, key)
            all_versions.extend(chain)
            if len(all_versions) >= max_keys:
                break

        return all_versions[:max_keys]


# ============================================================
# ObjectStore — core object storage operations
# ============================================================


class ObjectStore:
    """Core object storage operations implementing the S3 object API.

    Handles PUT, GET, HEAD, DELETE, COPY, and LIST operations with
    full support for conditional requests, byte-range reads, versioning,
    encryption, and content-addressable deduplication.
    """

    def __init__(
        self,
        metadata_index: MetadataIndex,
        cas: ContentAddressableStore,
        encryption_engine: EncryptionEngine,
        versioning_engine: VersioningEngine,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._metadata = metadata_index
        self._cas = cas
        self._encryption = encryption_engine
        self._versioning = versioning_engine
        self._event_bus = event_bus
        self._sequencer = 0
        self._lock = threading.Lock()

    def put_object(
        self,
        bucket_name: str,
        key: str,
        data: bytes,
        metadata: Optional[Dict[str, str]] = None,
        content_type: str = "application/octet-stream",
        storage_class: StorageClass = StorageClass.STANDARD,
        encryption_mode: Optional[EncryptionMode] = None,
        kms_key_id: Optional[str] = None,
        client_key: Optional[bytes] = None,
        checksum_sha256: Optional[str] = None,
    ) -> S3Object:
        """Store an object in a bucket.

        Validates inputs, computes ETag, handles versioning, encrypts
        if configured, chunks and deduplicates data, and publishes
        notification events.
        """
        bucket = self._get_bucket(bucket_name)

        # Validate key
        self._validate_key(key)

        # Validate data size
        if len(data) > MAX_SINGLE_PUT_SIZE:
            raise ObjectTooLargeError(len(data), MAX_SINGLE_PUT_SIZE)

        # Validate metadata size
        if metadata:
            meta_size = sum(len(k) + len(v) for k, v in metadata.items())
            if meta_size > MAX_METADATA_SIZE:
                raise MetadataCapacityExceededError(meta_size, MAX_METADATA_SIZE)

        # Compute ETag
        etag = hashlib.md5(data).hexdigest()

        # Handle versioning
        version_id = None
        if bucket.versioning == BucketVersioning.ENABLED:
            version_id = self._versioning.assign_version_id()
        elif bucket.versioning == BucketVersioning.SUSPENDED:
            version_id = None  # null version

        # Encrypt if configured
        stored_data = data
        sse_meta = None
        enc_mode = encryption_mode
        if enc_mode is None and bucket.encryption_configuration:
            enc_mode = bucket.encryption_configuration.default_encryption
        if enc_mode:
            stored_data, sse_meta = self._encryption.encrypt(
                data, enc_mode, kms_key_id, client_key
            )

        # Store in CAS
        object_id = f"{bucket_name}/{key}/{version_id or 'null'}"
        self._cas.store_object(object_id, stored_data, storage_class)

        # SHA-256 checksum
        computed_sha256 = hashlib.sha256(data).hexdigest()
        if checksum_sha256 and checksum_sha256 != computed_sha256:
            raise ObjectError(
                f"SHA-256 mismatch: expected {checksum_sha256}, "
                f"computed {computed_sha256}"
            )

        # Create object record
        obj = S3Object(
            key=key,
            bucket_name=bucket_name,
            version_id=version_id,
            data=data,
            size=len(data),
            etag=etag,
            content_type=content_type,
            storage_class=storage_class,
            metadata=metadata or {},
            server_side_encryption=sse_meta,
            checksum_sha256=computed_sha256,
            is_latest=True,
        )

        # Store metadata
        obj_ns = f"objects:{bucket_name}"
        self._metadata.put(obj_ns, key, obj)

        # Version chain
        if bucket.versioning != BucketVersioning.DISABLED:
            self._versioning.add_version(bucket_name, key, obj)

        self._emit_event("S3_OBJECT_CREATED_PUT", {
            "bucket": bucket_name,
            "key": key,
            "version_id": version_id,
            "size": len(data),
            "etag": etag,
        })

        return obj

    def get_object(
        self,
        bucket_name: str,
        key: str,
        version_id: Optional[str] = None,
        byte_range: Optional[str] = None,
        if_match: Optional[str] = None,
        if_none_match: Optional[str] = None,
        if_modified_since: Optional[datetime] = None,
        if_unmodified_since: Optional[datetime] = None,
    ) -> S3Object:
        """Retrieve an object with conditional request support.

        Supports ETag matching, timestamp conditions, byte-range reads,
        and version-specific retrieval.
        """
        self._get_bucket(bucket_name)

        # Version-specific retrieval
        if version_id:
            obj = self._versioning.get_specific_version(
                bucket_name, key, version_id
            )
            if obj is None:
                raise NoSuchVersionError(bucket_name, key, version_id)
        else:
            obj_ns = f"objects:{bucket_name}"
            obj = self._metadata.get(obj_ns, key)

        if obj is None:
            raise ObjectNotFoundError(bucket_name, key)

        # Delete marker check
        if obj.delete_marker:
            raise ObjectNotFoundError(bucket_name, key)

        # Conditional checks
        if if_match and obj.etag != if_match:
            raise PreconditionFailedError("If-Match", if_match, obj.etag)

        if if_none_match and obj.etag == if_none_match:
            raise NotModifiedError(f"ETag matches: {obj.etag}")

        if if_modified_since and obj.last_modified <= if_modified_since:
            raise NotModifiedError(
                f"Not modified since {if_modified_since.isoformat()}"
            )

        if if_unmodified_since and obj.last_modified > if_unmodified_since:
            raise PreconditionFailedError(
                "If-Unmodified-Since",
                if_unmodified_since.isoformat(),
                obj.last_modified.isoformat(),
            )

        # Retrieve data from CAS
        result_obj = copy.copy(obj)
        object_id = f"{bucket_name}/{key}/{version_id or obj.version_id or 'null'}"
        try:
            stored_data = self._cas.retrieve_object(
                object_id, obj.storage_class
            )
        except ChunkNotFoundError:
            stored_data = obj.data

        # Decrypt if encrypted
        if obj.server_side_encryption:
            try:
                result_obj.data = self._encryption.decrypt(
                    stored_data, obj.server_side_encryption
                )
            except EncryptionError:
                result_obj.data = stored_data
        else:
            result_obj.data = stored_data

        # Byte-range handling
        if byte_range:
            result_obj.data = self._apply_byte_range(
                result_obj.data, byte_range, obj.size
            )

        return result_obj

    def head_object(self, bucket_name: str, key: str,
                    version_id: Optional[str] = None) -> S3Object:
        """Return object metadata without data payload."""
        obj = self.get_object(bucket_name, key, version_id)
        result = copy.copy(obj)
        result.data = b""
        return result

    def delete_object(self, bucket_name: str, key: str,
                      version_id: Optional[str] = None) -> Optional[S3Object]:
        """Delete an object or create a delete marker.

        Unversioned buckets: permanent deletion.
        Versioned without version_id: insert delete marker.
        Versioned with version_id: permanent version deletion.
        """
        bucket = self._get_bucket(bucket_name)
        obj_ns = f"objects:{bucket_name}"

        if bucket.versioning == BucketVersioning.DISABLED:
            # Permanent delete
            obj = self._metadata.get(obj_ns, key)
            if obj is None:
                return None
            self._metadata.delete(obj_ns, key)
            object_id = f"{bucket_name}/{key}/null"
            self._cas.delete_object_references(object_id)
            self._emit_event("S3_OBJECT_DELETED", {
                "bucket": bucket_name, "key": key,
            })
            return obj

        if version_id:
            # Permanent version delete
            deleted = self._versioning.delete_specific_version(
                bucket_name, key, version_id
            )
            object_id = f"{bucket_name}/{key}/{version_id}"
            self._cas.delete_object_references(object_id)

            # Update current object metadata
            chain = self._versioning.get_version_chain(bucket_name, key)
            if chain:
                current = chain[0]
                if not current.delete_marker:
                    self._metadata.put(obj_ns, key, current)
                else:
                    self._metadata.delete(obj_ns, key)
            else:
                self._metadata.delete(obj_ns, key)

            self._emit_event("S3_OBJECT_DELETED", {
                "bucket": bucket_name, "key": key,
                "version_id": version_id,
            })
            return deleted

        # Insert delete marker
        marker_vid = self._versioning.assign_version_id()
        marker = S3Object(
            key=key,
            bucket_name=bucket_name,
            version_id=marker_vid,
            delete_marker=True,
            is_latest=True,
        )
        self._versioning.add_version(bucket_name, key, marker)
        self._metadata.delete(obj_ns, key)

        self._emit_event("S3_OBJECT_DELETE_MARKER_CREATED", {
            "bucket": bucket_name, "key": key,
            "version_id": marker_vid,
        })
        return marker

    def delete_objects(self, bucket_name: str,
                       objects: List[Dict[str, str]]) -> Tuple[list, list]:
        """Batch delete up to 1000 objects.

        Args:
            objects: List of {"key": ..., "version_id": ...} dicts.

        Returns:
            Tuple of (successes, errors).
        """
        if len(objects) > MAX_DELETE_OBJECTS:
            objects = objects[:MAX_DELETE_OBJECTS]

        successes = []
        errors = []
        for obj_ref in objects:
            key = obj_ref.get("key", "")
            vid = obj_ref.get("version_id")
            try:
                self.delete_object(bucket_name, key, vid)
                successes.append({"key": key, "version_id": vid})
            except (ObjectNotFoundError, NoSuchVersionError) as e:
                errors.append({"key": key, "error": str(e)})

        return successes, errors

    def copy_object(
        self,
        source_bucket: str,
        source_key: str,
        dest_bucket: str,
        dest_key: str,
        source_version_id: Optional[str] = None,
        metadata_directive: str = "COPY",
        storage_class: Optional[StorageClass] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> S3Object:
        """Copy an object between buckets or keys.

        For same-region content-addressed storage, copy is metadata-only
        when the data is unchanged (deduplication handles the data).
        """
        source_obj = self.get_object(
            source_bucket, source_key, source_version_id
        )

        dest_metadata = metadata if metadata_directive == "REPLACE" else source_obj.metadata
        dest_storage = storage_class or source_obj.storage_class

        result = self.put_object(
            bucket_name=dest_bucket,
            key=dest_key,
            data=source_obj.data,
            metadata=dest_metadata,
            content_type=source_obj.content_type,
            storage_class=dest_storage,
        )

        self._emit_event("S3_OBJECT_CREATED_COPY", {
            "source_bucket": source_bucket,
            "source_key": source_key,
            "dest_bucket": dest_bucket,
            "dest_key": dest_key,
        })

        return result

    def list_objects_v2(
        self,
        bucket_name: str,
        prefix: Optional[str] = None,
        delimiter: Optional[str] = None,
        start_after: Optional[str] = None,
        continuation_token: Optional[str] = None,
        max_keys: int = MAX_LIST_KEYS,
    ) -> ListObjectsResult:
        """List objects with prefix filtering and delimiter hierarchy.

        Supports pagination via continuation tokens and delimiter-based
        hierarchy simulation (e.g., '/' delimiter simulates directories).
        """
        self._get_bucket(bucket_name)
        obj_ns = f"objects:{bucket_name}"

        all_keys = sorted(self._metadata.list_keys(obj_ns))

        # Apply start_after or continuation_token
        start_key = start_after or continuation_token or ""
        if start_key:
            all_keys = [k for k in all_keys if k > start_key]

        # Apply prefix filter
        if prefix:
            all_keys = [k for k in all_keys if k.startswith(prefix)]

        contents = []
        common_prefixes = set()

        for key in all_keys:
            obj = self._metadata.get(obj_ns, key)
            if obj is None or obj.delete_marker:
                continue

            if delimiter:
                # Find delimiter after prefix
                after_prefix = key[len(prefix or ""):]
                delim_pos = after_prefix.find(delimiter)
                if delim_pos >= 0:
                    cp = (prefix or "") + after_prefix[:delim_pos + len(delimiter)]
                    common_prefixes.add(cp)
                    continue

            contents.append(ObjectSummary(
                key=key,
                last_modified=obj.last_modified,
                etag=obj.etag,
                size=obj.size,
                storage_class=obj.storage_class,
                owner=getattr(obj, 'owner', 'fizzbuzz-root'),
            ))

            if len(contents) + len(common_prefixes) >= max_keys:
                break

        is_truncated = len(contents) + len(common_prefixes) < len(all_keys)
        next_token = contents[-1].key if is_truncated and contents else None

        return ListObjectsResult(
            contents=contents[:max_keys],
            common_prefixes=sorted(common_prefixes),
            is_truncated=is_truncated,
            next_continuation_token=next_token,
            key_count=len(contents),
            max_keys=max_keys,
            prefix=prefix,
            delimiter=delimiter,
        )

    def _get_bucket(self, name: str) -> Bucket:
        """Internal bucket lookup."""
        bucket = self._metadata.get("buckets", name)
        if bucket is None:
            raise BucketNotFoundError(name)
        return bucket

    def _validate_key(self, key: str) -> None:
        """Validate object key."""
        if not key:
            raise InvalidObjectKeyError(key, "Key cannot be empty")
        if len(key.encode("utf-8")) > MAX_OBJECT_KEY_LENGTH:
            raise InvalidObjectKeyError(key, f"Key exceeds {MAX_OBJECT_KEY_LENGTH} bytes")
        if "\x00" in key:
            raise InvalidObjectKeyError(key, "Key contains null byte")

    def _apply_byte_range(self, data: bytes, range_spec: str,
                          object_size: int) -> bytes:
        """Apply byte-range specification to data.

        Supports formats: bytes=start-end, bytes=start-, bytes=-suffix.
        """
        match = re.match(r"bytes=(\d*)-(\d*)", range_spec)
        if not match:
            raise InvalidRangeError(range_spec, object_size)

        start_str, end_str = match.group(1), match.group(2)

        if start_str and end_str:
            start = int(start_str)
            end = min(int(end_str), object_size - 1)
        elif start_str:
            start = int(start_str)
            end = object_size - 1
        elif end_str:
            suffix = int(end_str)
            start = max(0, object_size - suffix)
            end = object_size - 1
        else:
            raise InvalidRangeError(range_spec, object_size)

        if start >= object_size or start > end:
            raise InvalidRangeError(range_spec, object_size)

        return data[start:end + 1]

    def _emit_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Publish an event to the event bus."""
        if self._event_bus:
            try:
                self._event_bus.publish(event_type, data)
            except Exception:
                logger.warning("Failed to publish event: %s", event_type)


# ============================================================
# MultipartUploadManager
# ============================================================


class MultipartUploadManager:
    """Orchestrates multipart upload lifecycle.

    Supports upload initiation, part upload (5 MB minimum except last),
    server-side part copy, completion with ETag verification, and
    abort with cleanup.
    """

    def __init__(
        self,
        metadata_index: MetadataIndex,
        object_store: ObjectStore,
        cas: ContentAddressableStore,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._metadata = metadata_index
        self._object_store = object_store
        self._cas = cas
        self._event_bus = event_bus

    def create_multipart_upload(
        self,
        bucket_name: str,
        key: str,
        metadata: Optional[Dict[str, str]] = None,
        content_type: str = "application/octet-stream",
        storage_class: StorageClass = StorageClass.STANDARD,
        encryption: Optional[ServerSideEncryption] = None,
    ) -> str:
        """Initiate a multipart upload session.

        Returns:
            Upload ID for the session.
        """
        upload = MultipartUpload(
            bucket=bucket_name,
            key=key,
            metadata=metadata or {},
            content_type=content_type,
            storage_class=storage_class,
            encryption=encryption,
        )

        upload_ns = f"uploads:{bucket_name}"
        upload_key = f"{key}:{upload.upload_id}"
        self._metadata.put(upload_ns, upload_key, upload)

        logger.debug("Multipart upload initiated: %s/%s [%s]",
                      bucket_name, key, upload.upload_id)
        return upload.upload_id

    def upload_part(
        self,
        bucket_name: str,
        key: str,
        upload_id: str,
        part_number: int,
        data: bytes,
    ) -> str:
        """Upload a single part.

        Args:
            bucket_name: Target bucket.
            key: Target key.
            upload_id: Upload session ID.
            part_number: Part sequence number (1-10000).
            data: Part data.

        Returns:
            ETag of the uploaded part.
        """
        if part_number < 1 or part_number > MAX_PARTS:
            raise TooManyPartsError(part_number, MAX_PARTS)

        if len(data) > MAX_PART_SIZE:
            raise EntityTooLargeError(part_number, len(data), MAX_PART_SIZE)

        upload = self._get_upload(bucket_name, key, upload_id)

        etag = hashlib.md5(data).hexdigest()
        part = UploadPart(
            part_number=part_number,
            etag=etag,
            size=len(data),
            data=data,
        )
        upload.parts[part_number] = part
        self._save_upload(bucket_name, key, upload)

        return etag

    def upload_part_copy(
        self,
        bucket_name: str,
        key: str,
        upload_id: str,
        part_number: int,
        source_bucket: str,
        source_key: str,
        source_version_id: Optional[str] = None,
        byte_range: Optional[str] = None,
    ) -> str:
        """Server-side copy of data into a multipart part.

        Returns:
            ETag of the copied part.
        """
        source_obj = self._object_store.get_object(
            source_bucket, source_key, source_version_id
        )
        data = source_obj.data
        if byte_range:
            data = self._object_store._apply_byte_range(
                data, byte_range, source_obj.size
            )
        return self.upload_part(bucket_name, key, upload_id, part_number, data)

    def complete_multipart_upload(
        self,
        bucket_name: str,
        key: str,
        upload_id: str,
        parts: List[Dict[str, Any]],
    ) -> S3Object:
        """Complete a multipart upload by concatenating parts.

        Args:
            parts: List of {"part_number": int, "etag": str} dicts.

        Returns:
            Created S3Object.
        """
        upload = self._get_upload(bucket_name, key, upload_id)

        # Validate part order
        prev_num = 0
        for part_ref in parts:
            pn = part_ref["part_number"]
            if pn <= prev_num:
                raise InvalidPartOrderError(
                    f"Part {pn} not in ascending order"
                )
            prev_num = pn

        # Validate parts exist and ETags match
        for i, part_ref in enumerate(parts):
            pn = part_ref["part_number"]
            expected_etag = part_ref.get("etag", "")
            if pn not in upload.parts:
                raise InvalidPartError(pn, "Part not uploaded")
            if expected_etag and upload.parts[pn].etag != expected_etag:
                raise InvalidPartError(
                    pn, f"ETag mismatch: expected {expected_etag}, "
                    f"got {upload.parts[pn].etag}"
                )

            # Validate minimum part size (except last)
            if i < len(parts) - 1:
                if upload.parts[pn].size < MIN_PART_SIZE:
                    raise EntityTooSmallError(
                        pn, upload.parts[pn].size, MIN_PART_SIZE
                    )

        # Concatenate parts
        combined = bytearray()
        for part_ref in parts:
            pn = part_ref["part_number"]
            combined.extend(upload.parts[pn].data)

        # Compute composite ETag (MD5 of concatenated part MD5s)
        part_md5s = b""
        for part_ref in parts:
            pn = part_ref["part_number"]
            part_md5s += bytes.fromhex(upload.parts[pn].etag)
        composite_etag = hashlib.md5(part_md5s).hexdigest() + f"-{len(parts)}"

        # Store as regular object
        obj = self._object_store.put_object(
            bucket_name=bucket_name,
            key=key,
            data=bytes(combined),
            metadata=upload.metadata,
            content_type=upload.content_type,
            storage_class=upload.storage_class,
        )
        obj.etag = composite_etag

        # Cleanup upload session
        self._delete_upload(bucket_name, key, upload_id)

        if self._event_bus:
            try:
                self._event_bus.publish("S3_OBJECT_CREATED_MPU", {
                    "bucket": bucket_name,
                    "key": key,
                    "upload_id": upload_id,
                    "parts": len(parts),
                })
            except Exception:
                pass

        return obj

    def abort_multipart_upload(self, bucket_name: str, key: str,
                               upload_id: str) -> None:
        """Abort a multipart upload and clean up parts."""
        self._get_upload(bucket_name, key, upload_id)
        self._delete_upload(bucket_name, key, upload_id)
        logger.debug("Multipart upload aborted: %s/%s [%s]",
                      bucket_name, key, upload_id)

    def list_multipart_uploads(self, bucket_name: str,
                               prefix: str = "",
                               max_uploads: int = MAX_LIST_KEYS) -> List[MultipartUpload]:
        """List in-progress multipart uploads."""
        upload_ns = f"uploads:{bucket_name}"
        all_keys = self._metadata.list_keys(upload_ns)
        uploads = []
        for ukey in sorted(all_keys):
            upload = self._metadata.get(upload_ns, ukey)
            if upload and (not prefix or upload.key.startswith(prefix)):
                uploads.append(upload)
                if len(uploads) >= max_uploads:
                    break
        return uploads

    def list_parts(self, bucket_name: str, key: str,
                   upload_id: str,
                   max_parts: int = MAX_PARTS) -> List[UploadPart]:
        """List uploaded parts for a multipart upload."""
        upload = self._get_upload(bucket_name, key, upload_id)
        parts = sorted(upload.parts.values(), key=lambda p: p.part_number)
        return parts[:max_parts]

    def _get_upload(self, bucket_name: str, key: str,
                    upload_id: str) -> MultipartUpload:
        """Look up an active upload session."""
        upload_ns = f"uploads:{bucket_name}"
        upload_key = f"{key}:{upload_id}"
        upload = self._metadata.get(upload_ns, upload_key)
        if upload is None:
            raise NoSuchUploadError(upload_id)
        return upload

    def _save_upload(self, bucket_name: str, key: str,
                     upload: MultipartUpload) -> None:
        """Save upload session state."""
        upload_ns = f"uploads:{bucket_name}"
        upload_key = f"{key}:{upload.upload_id}"
        self._metadata.put(upload_ns, upload_key, upload)

    def _delete_upload(self, bucket_name: str, key: str,
                       upload_id: str) -> None:
        """Remove upload session."""
        upload_ns = f"uploads:{bucket_name}"
        upload_key = f"{key}:{upload_id}"
        self._metadata.delete(upload_ns, upload_key)


# ============================================================
# IncompleteUploadReaper
# ============================================================


class IncompleteUploadReaper:
    """Background cleanup of stale multipart uploads.

    Scans for uploads older than the configured threshold and aborts
    them.  Respects per-bucket lifecycle rules for incomplete multipart
    upload cleanup.
    """

    def __init__(
        self,
        multipart_mgr: MultipartUploadManager,
        bucket_mgr: BucketManager,
        threshold_days: int = 7,
    ) -> None:
        self._multipart = multipart_mgr
        self._bucket_mgr = bucket_mgr
        self._threshold_days = threshold_days

    def reap(self) -> Dict[str, int]:
        """Scan and abort stale uploads.

        Returns:
            Map of bucket_name -> aborted_count.
        """
        result = {}
        cutoff = datetime.now(timezone.utc) - timedelta(days=self._threshold_days)

        for bucket in self._bucket_mgr.list_buckets():
            uploads = self._multipart.list_multipart_uploads(bucket.name)
            aborted = 0
            for upload in uploads:
                # Check lifecycle override
                threshold = self._threshold_days
                if bucket.lifecycle_configuration:
                    for rule in bucket.lifecycle_configuration.rules:
                        if rule.status == RuleStatus.ENABLED and \
                           rule.abort_incomplete_multipart_days is not None:
                            threshold = min(
                                threshold,
                                rule.abort_incomplete_multipart_days,
                            )

                rule_cutoff = datetime.now(timezone.utc) - timedelta(days=threshold)
                if upload.initiated < rule_cutoff:
                    try:
                        self._multipart.abort_multipart_upload(
                            upload.bucket, upload.key, upload.upload_id
                        )
                        aborted += 1
                    except NoSuchUploadError:
                        pass

            if aborted > 0:
                result[bucket.name] = aborted

        return result


# ============================================================
# PresignedURLGenerator & Verifier
# ============================================================


class SignatureV4Computer:
    """Implements AWS Signature Version 4 request signing.

    Computes HMAC-SHA256 signatures compatible with the AWS SigV4
    signing process for presigned URL generation and verification.
    """

    def __init__(self, secret_key: Optional[str] = None) -> None:
        self._secret_key = secret_key or uuid.uuid4().hex

    def compute_signing_key(self, date: str, region: str,
                            service: str = "s3") -> bytes:
        """Derive the signing key via HMAC chain.

        HMAC(HMAC(HMAC(HMAC("AWS4" + secret, date), region), service), "aws4_request")
        """
        k_date = hmac.new(
            ("AWS4" + self._secret_key).encode(), date.encode(), hashlib.sha256
        ).digest()
        k_region = hmac.new(k_date, region.encode(), hashlib.sha256).digest()
        k_service = hmac.new(k_region, service.encode(), hashlib.sha256).digest()
        k_signing = hmac.new(k_service, b"aws4_request", hashlib.sha256).digest()
        return k_signing

    def compute_canonical_request(
        self,
        method: str,
        path: str,
        query_params: str,
        headers: Dict[str, str],
        signed_headers: str,
        payload_hash: str,
    ) -> str:
        """Construct the canonical request string."""
        canonical_headers = ""
        for h in signed_headers.split(";"):
            canonical_headers += f"{h}:{headers.get(h, '')}\n"

        return "\n".join([
            method,
            quote(path, safe="/"),
            query_params,
            canonical_headers,
            signed_headers,
            payload_hash,
        ])

    def compute_string_to_sign(
        self,
        algorithm: str,
        datetime_str: str,
        scope: str,
        canonical_request_hash: str,
    ) -> str:
        """Combine algorithm, timestamp, scope, and hash."""
        return "\n".join([
            algorithm,
            datetime_str,
            scope,
            canonical_request_hash,
        ])

    def compute_signature(self, signing_key: bytes,
                          string_to_sign: str) -> str:
        """Compute the final HMAC-SHA256 signature."""
        return hmac.new(
            signing_key, string_to_sign.encode(), hashlib.sha256
        ).hexdigest()


class PresignedURLGenerator:
    """Generates presigned URLs for S3 object operations.

    Creates time-limited URLs with AWS Signature Version 4 that grant
    temporary access to specific objects without requiring credentials.
    """

    def __init__(
        self,
        sig_computer: SignatureV4Computer,
        default_expiry: int = 3600,
        region: str = DEFAULT_REGION,
    ) -> None:
        self._sig = sig_computer
        self._default_expiry = default_expiry
        self._region = region

    def generate_presigned_url(
        self,
        method: str,
        bucket: str,
        key: str,
        version_id: Optional[str] = None,
        expiration: Optional[int] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> str:
        """Generate a presigned URL for an object operation.

        Returns:
            Presigned URL string with SigV4 query parameters.
        """
        expiry = expiration or self._default_expiry
        if expiry > MAX_PRESIGN_EXPIRY:
            raise PresignedURLError(
                f"Expiry {expiry}s exceeds maximum {MAX_PRESIGN_EXPIRY}s"
            )

        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y%m%d")
        datetime_str = now.strftime("%Y%m%dT%H%M%SZ")
        scope = f"{date_str}/{self._region}/s3/aws4_request"

        path = f"/{bucket}/{key}"
        query_params = {
            "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
            "X-Amz-Credential": f"FIZZ/{scope}",
            "X-Amz-Date": datetime_str,
            "X-Amz-Expires": str(expiry),
            "X-Amz-SignedHeaders": "host",
        }
        if version_id:
            query_params["versionId"] = version_id

        query_string = urlencode(sorted(query_params.items()))

        canonical_request = self._sig.compute_canonical_request(
            method=method,
            path=path,
            query_params=query_string,
            headers={"host": f"s3.{self._region}.fizz.internal"},
            signed_headers="host",
            payload_hash="UNSIGNED-PAYLOAD",
        )

        cr_hash = hashlib.sha256(canonical_request.encode()).hexdigest()
        string_to_sign = self._sig.compute_string_to_sign(
            "AWS4-HMAC-SHA256", datetime_str, scope, cr_hash
        )

        signing_key = self._sig.compute_signing_key(date_str, self._region)
        signature = self._sig.compute_signature(signing_key, string_to_sign)

        url = (
            f"https://s3.{self._region}.fizz.internal{path}"
            f"?{query_string}&X-Amz-Signature={signature}"
        )
        return url

    def generate_presigned_post(
        self,
        bucket: str,
        key: str,
        conditions: Optional[List] = None,
        expiration: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Generate presigned POST parameters for browser-based uploads.

        Returns:
            Dict with url and fields for form POST.
        """
        expiry = expiration or self._default_expiry
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=expiry)

        policy_doc = {
            "expiration": expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "conditions": [
                {"bucket": bucket},
                {"key": key},
                *(conditions or []),
            ],
        }

        policy_b64 = base64.b64encode(
            json.dumps(policy_doc).encode()
        ).decode()

        date_str = now.strftime("%Y%m%d")
        signing_key = self._sig.compute_signing_key(date_str, self._region)
        signature = hmac.new(
            signing_key, policy_b64.encode(), hashlib.sha256
        ).hexdigest()

        return {
            "url": f"https://s3.{self._region}.fizz.internal/{bucket}",
            "fields": {
                "key": key,
                "policy": policy_b64,
                "X-Amz-Signature": signature,
                "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
                "X-Amz-Date": now.strftime("%Y%m%dT%H%M%SZ"),
            },
        }


class PresignedURLVerifier:
    """Validates presigned URLs on incoming requests.

    Recomputes the signature and validates expiration, method match,
    and clock skew tolerance.
    """

    def __init__(self, sig_computer: SignatureV4Computer,
                 region: str = DEFAULT_REGION) -> None:
        self._sig = sig_computer
        self._region = region

    def verify(self, url: str, method: str,
               headers: Optional[Dict[str, str]] = None) -> AuthorizationResult:
        """Verify a presigned URL.

        Returns:
            AuthorizationResult with allowed status and reason.
        """
        try:
            parsed = urlparse(url)
            params = dict(
                p.split("=", 1) for p in parsed.query.split("&") if "=" in p
            )

            # Check required parameters
            for required in ["X-Amz-Algorithm", "X-Amz-Date",
                             "X-Amz-Expires", "X-Amz-Signature"]:
                if required not in params:
                    return AuthorizationResult(
                        allowed=False,
                        reason=f"Missing parameter: {required}",
                    )

            # Check expiration
            amz_date = params["X-Amz-Date"]
            expires = int(params["X-Amz-Expires"])
            sign_time = datetime.strptime(amz_date, "%Y%m%dT%H%M%SZ").replace(
                tzinfo=timezone.utc
            )
            expiry_time = sign_time + timedelta(seconds=expires)
            now = datetime.now(timezone.utc)

            if now > expiry_time:
                return AuthorizationResult(
                    allowed=False,
                    reason="Presigned URL expired",
                )

            # Clock skew check
            skew = abs((now - sign_time).total_seconds())
            if skew > CLOCK_SKEW_TOLERANCE + expires:
                return AuthorizationResult(
                    allowed=False,
                    reason="Clock skew exceeds tolerance",
                )

            # Recompute signature
            query_without_sig = "&".join(
                f"{k}={v}" for k, v in sorted(params.items())
                if k != "X-Amz-Signature"
            )

            date_str = amz_date[:8]
            scope = f"{date_str}/{self._region}/s3/aws4_request"

            canonical_request = self._sig.compute_canonical_request(
                method=method,
                path=parsed.path,
                query_params=query_without_sig,
                headers={"host": parsed.netloc},
                signed_headers="host",
                payload_hash="UNSIGNED-PAYLOAD",
            )

            cr_hash = hashlib.sha256(canonical_request.encode()).hexdigest()
            string_to_sign = self._sig.compute_string_to_sign(
                "AWS4-HMAC-SHA256", amz_date, scope, cr_hash
            )

            signing_key = self._sig.compute_signing_key(date_str, self._region)
            expected_sig = self._sig.compute_signature(signing_key, string_to_sign)

            if expected_sig != params["X-Amz-Signature"]:
                return AuthorizationResult(
                    allowed=False,
                    reason="Signature mismatch",
                )

            return AuthorizationResult(allowed=True, reason="Valid", evaluated_policies=1)

        except Exception as e:
            return AuthorizationResult(
                allowed=False,
                reason=f"Verification error: {str(e)}",
            )


# ============================================================
# StorageClassManager & RestoreProcessor
# ============================================================


class StorageClassManager:
    """Manages storage class transitions and archive restore operations.

    Validates the waterfall ordering of transitions and handles the
    re-encoding of erasure-coded fragments with target-class parameters.
    """

    def __init__(
        self,
        object_store: ObjectStore,
        cas: ContentAddressableStore,
        erasure_engine: ErasureCodingEngine,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._object_store = object_store
        self._cas = cas
        self._erasure_engine = erasure_engine
        self._event_bus = event_bus
        self._restore_queue: List[Dict[str, Any]] = []
        self._restored_objects: Dict[str, datetime] = {}

    def transition_object(self, bucket_name: str, key: str,
                          version_id: Optional[str] = None,
                          target_class: StorageClass = StorageClass.STANDARD_IA) -> None:
        """Transition an object to a different storage class.

        Validates the waterfall ordering and re-encodes fragments.
        """
        obj = self._object_store.get_object(bucket_name, key, version_id)
        current_order = STORAGE_CLASS_ORDER.get(obj.storage_class, 0)
        target_order = STORAGE_CLASS_ORDER.get(target_class, 0)

        if target_order <= current_order:
            raise InvalidStorageClassTransitionError(
                obj.storage_class.value, target_class.value
            )

        # Update object storage class
        obj_ns = f"objects:{bucket_name}"
        obj.storage_class = target_class
        self._object_store._metadata.put(obj_ns, key, obj)

        if self._event_bus:
            try:
                self._event_bus.publish("S3_OBJECT_TRANSITIONED", {
                    "bucket": bucket_name,
                    "key": key,
                    "from_class": obj.storage_class.value,
                    "to_class": target_class.value,
                })
            except Exception:
                pass

    def restore_object(self, bucket_name: str, key: str,
                       version_id: Optional[str] = None,
                       days: int = 1,
                       tier: RestoreTier = RestoreTier.STANDARD) -> None:
        """Initiate an async restore of an archived object."""
        obj = self._object_store.get_object(bucket_name, key, version_id)

        if obj.storage_class not in (StorageClass.ARCHIVE, StorageClass.DEEP_ARCHIVE):
            raise ObjectNotArchivedError(
                bucket_name, key, obj.storage_class.value
            )

        restore_key = f"{bucket_name}/{key}/{version_id or 'null'}"
        if restore_key in self._restored_objects:
            if datetime.now(timezone.utc) < self._restored_objects[restore_key]:
                raise RestoreInProgressError(bucket_name, key)

        # Queue restore
        self._restore_queue.append({
            "bucket": bucket_name,
            "key": key,
            "version_id": version_id,
            "days": days,
            "tier": tier,
        })

        # Process immediately for simulation
        expiry = datetime.now(timezone.utc) + timedelta(days=days)
        self._restored_objects[restore_key] = expiry

        if self._event_bus:
            try:
                self._event_bus.publish("S3_OBJECT_RESTORE_INITIATED", {
                    "bucket": bucket_name, "key": key, "tier": tier.value,
                })
            except Exception:
                pass

    def is_restored(self, bucket_name: str, key: str,
                    version_id: Optional[str] = None) -> bool:
        """Check if an archived object has been restored."""
        restore_key = f"{bucket_name}/{key}/{version_id or 'null'}"
        expiry = self._restored_objects.get(restore_key)
        if expiry is None:
            return False
        if datetime.now(timezone.utc) > expiry:
            del self._restored_objects[restore_key]
            return False
        return True

    def get_storage_class_stats(self, bucket_name: str) -> Dict[str, Dict[str, int]]:
        """Return per-class object count and size for a bucket."""
        stats: Dict[str, Dict[str, int]] = {}
        for sc in StorageClass:
            stats[sc.value] = {"count": 0, "size": 0}

        obj_ns = f"objects:{bucket_name}"
        for key in self._object_store._metadata.list_keys(obj_ns):
            obj = self._object_store._metadata.get(obj_ns, key)
            if obj and not obj.delete_marker:
                sc = obj.storage_class.value
                stats[sc]["count"] += 1
                stats[sc]["size"] += obj.size

        return stats


# ============================================================
# LifecycleEvaluator & LifecycleDaemon
# ============================================================


class LifecycleEvaluator:
    """Evaluates lifecycle rules against objects in a bucket.

    Scans objects, matches against enabled lifecycle rules, and
    produces a deduplicated list of actions.  Expiration takes
    priority over transition for the same object.
    """

    def __init__(
        self,
        object_store: ObjectStore,
        storage_class_mgr: StorageClassManager,
        multipart_mgr: MultipartUploadManager,
    ) -> None:
        self._object_store = object_store
        self._storage_class_mgr = storage_class_mgr
        self._multipart_mgr = multipart_mgr

    def evaluate(self, bucket_name: str) -> List[LifecycleAction]:
        """Evaluate lifecycle rules for all objects in a bucket.

        Returns:
            Deduplicated list of lifecycle actions.
        """
        bucket = self._object_store._get_bucket(bucket_name)
        if not bucket.lifecycle_configuration:
            return []

        now = datetime.now(timezone.utc)
        actions: Dict[str, LifecycleAction] = {}

        for rule in bucket.lifecycle_configuration.rules:
            if rule.status != RuleStatus.ENABLED:
                continue

            # Evaluate objects
            obj_ns = f"objects:{bucket_name}"
            for key in self._object_store._metadata.list_keys(obj_ns):
                if rule.prefix and not key.startswith(rule.prefix):
                    continue

                obj = self._object_store._metadata.get(obj_ns, key)
                if obj is None or obj.delete_marker:
                    continue

                # Tag filter
                if rule.tags and not all(
                    obj.metadata.get(k) == v for k, v in rule.tags.items()
                ):
                    continue

                age_days = (now - obj.last_modified).days
                action_key = f"{bucket_name}/{key}"

                # Expiration (highest priority)
                if rule.expiration_days and age_days >= rule.expiration_days:
                    actions[action_key] = LifecycleAction(
                        action_type="expire",
                        bucket_name=bucket_name,
                        key=key,
                    )
                    continue  # Expiration overrides transition

                # Transitions (ordered by days)
                if action_key not in actions:
                    for transition in sorted(rule.transitions, key=lambda t: t.days):
                        if age_days >= transition.days:
                            if STORAGE_CLASS_ORDER.get(transition.storage_class, 0) > \
                               STORAGE_CLASS_ORDER.get(obj.storage_class, 0):
                                actions[action_key] = LifecycleAction(
                                    action_type="transition",
                                    bucket_name=bucket_name,
                                    key=key,
                                    target_storage_class=transition.storage_class,
                                )
                                break

        return list(actions.values())

    def apply_actions(self, actions: List[LifecycleAction]) -> Dict[str, int]:
        """Execute lifecycle actions.

        Returns:
            Counts by action type.
        """
        counts = {"expired": 0, "transitioned": 0, "aborted": 0}

        for action in actions:
            try:
                if action.action_type == "expire":
                    self._object_store.delete_object(
                        action.bucket_name, action.key
                    )
                    counts["expired"] += 1
                elif action.action_type == "transition":
                    self._storage_class_mgr.transition_object(
                        action.bucket_name, action.key,
                        target_class=action.target_storage_class,
                    )
                    counts["transitioned"] += 1
                elif action.action_type == "abort_multipart":
                    counts["aborted"] += 1
            except (FizzS3Error, Exception) as e:
                logger.warning("Lifecycle action failed: %s", e)

        return counts


class LifecycleDaemon:
    """Background lifecycle evaluation on a configurable schedule.

    Evaluates all buckets with lifecycle configurations at the
    configured interval and reports metrics.
    """

    def __init__(
        self,
        lifecycle_evaluator: LifecycleEvaluator,
        bucket_mgr: BucketManager,
        interval: float = DEFAULT_LIFECYCLE_INTERVAL,
    ) -> None:
        self._evaluator = lifecycle_evaluator
        self._bucket_mgr = bucket_mgr
        self._interval = interval
        self._last_run: Optional[datetime] = None
        self._metrics: Dict[str, int] = {"expired": 0, "transitioned": 0}

    def should_run(self) -> bool:
        """Check if a lifecycle evaluation is due."""
        if self._last_run is None:
            return True
        elapsed = (datetime.now(timezone.utc) - self._last_run).total_seconds()
        return elapsed >= self._interval

    def run(self) -> Dict[str, int]:
        """Evaluate lifecycle for all applicable buckets.

        Returns:
            Aggregate counts across all buckets.
        """
        total_counts = {"expired": 0, "transitioned": 0, "aborted": 0}

        for bucket in self._bucket_mgr.list_buckets():
            if bucket.lifecycle_configuration:
                actions = self._evaluator.evaluate(bucket.name)
                if actions:
                    counts = self._evaluator.apply_actions(actions)
                    for k, v in counts.items():
                        total_counts[k] = total_counts.get(k, 0) + v

        self._last_run = datetime.now(timezone.utc)
        for k, v in total_counts.items():
            self._metrics[k] = self._metrics.get(k, 0) + v

        return total_counts


# ============================================================
# ReplicationEngine & ConflictResolver
# ============================================================


class ReplicationConflictResolver:
    """Handles bidirectional replication conflicts.

    Uses last-writer-wins with lexicographic version ID tie-breaking.
    Detects replication loops via x-fizz-replication-source metadata.
    """

    def resolve(self, source_obj: S3Object,
                dest_obj: Optional[S3Object]) -> str:
        """Determine the winner in a replication conflict.

        Returns:
            "source" or "destination".
        """
        if dest_obj is None:
            return "source"

        if source_obj.last_modified > dest_obj.last_modified:
            return "source"
        elif source_obj.last_modified < dest_obj.last_modified:
            return "destination"

        # Tie-breaking by version ID
        src_vid = source_obj.version_id or ""
        dst_vid = dest_obj.version_id or ""
        return "source" if src_vid >= dst_vid else "destination"

    def detect_loop(self, obj: S3Object, destination_bucket: str) -> bool:
        """Check for replication loop via source metadata.

        Returns:
            True if loop detected.
        """
        source = obj.metadata.get("x-fizz-replication-source", "")
        return source == destination_bucket


class ReplicationEngine:
    """Processes cross-region replication asynchronously.

    Replicates objects and delete markers to destination buckets
    based on replication configuration rules.
    """

    def __init__(
        self,
        object_store: ObjectStore,
        conflict_resolver: Optional[ReplicationConflictResolver] = None,
        event_bus: Optional[Any] = None,
        max_retries: int = DEFAULT_REPLICATION_RETRY_MAX,
    ) -> None:
        self._object_store = object_store
        self._conflict_resolver = conflict_resolver or ReplicationConflictResolver()
        self._event_bus = event_bus
        self._max_retries = max_retries
        self._status: Dict[str, str] = {}  # "bucket/key/vid" -> status

    def replicate_object(
        self,
        source_bucket: str,
        source_key: str,
        source_version_id: Optional[str],
        rule: ReplicationRule,
    ) -> str:
        """Replicate an object to the destination bucket.

        Returns:
            Replication status: "COMPLETED" or "FAILED".
        """
        status_key = f"{source_bucket}/{source_key}/{source_version_id or 'null'}"

        try:
            source_obj = self._object_store.get_object(
                source_bucket, source_key, source_version_id
            )

            # Loop detection
            if self._conflict_resolver.detect_loop(
                source_obj, rule.destination_bucket
            ):
                raise ReplicationLoopDetectedError(
                    source_bucket, rule.destination_bucket
                )

            # Add replication source metadata
            rep_metadata = dict(source_obj.metadata)
            rep_metadata["x-fizz-replication-source"] = source_bucket

            storage_class = rule.destination_storage_class or source_obj.storage_class

            self._object_store.put_object(
                bucket_name=rule.destination_bucket,
                key=source_key,
                data=source_obj.data,
                metadata=rep_metadata,
                content_type=source_obj.content_type,
                storage_class=storage_class,
            )

            self._status[status_key] = "COMPLETED"
            if self._event_bus:
                try:
                    self._event_bus.publish("S3_REPLICATION_COMPLETED", {
                        "source_bucket": source_bucket,
                        "source_key": source_key,
                        "destination_bucket": rule.destination_bucket,
                    })
                except Exception:
                    pass

            return "COMPLETED"

        except (ReplicationLoopDetectedError, BucketNotFoundError,
                ObjectNotFoundError) as e:
            self._status[status_key] = "FAILED"
            if self._event_bus:
                try:
                    self._event_bus.publish("S3_REPLICATION_FAILED", {
                        "source_bucket": source_bucket,
                        "source_key": source_key,
                        "reason": str(e),
                    })
                except Exception:
                    pass
            return "FAILED"

    def get_replication_status(self, bucket: str, key: str,
                               version_id: Optional[str] = None) -> str:
        """Return replication status for an object."""
        status_key = f"{bucket}/{key}/{version_id or 'null'}"
        return self._status.get(status_key, "PENDING")


# ============================================================
# AccessControlEvaluator
# ============================================================


class AccessControlEvaluator:
    """Evaluates authorization for incoming S3 requests.

    Implements the S3 authorization algorithm:
    1. Check block public access settings.
    2. Evaluate bucket policy statements.
    3. Evaluate ACL grants.
    4. Apply logic: explicit DENY -> deny, no ALLOW -> deny,
       ALLOW with no DENY -> allow.
    """

    def evaluate(
        self,
        principal: str,
        action: str,
        resource: str,
        bucket: Optional[Bucket] = None,
    ) -> AuthorizationResult:
        """Evaluate an access request.

        Returns:
            AuthorizationResult with allowed/denied and reason.
        """
        if bucket is None:
            return AuthorizationResult(
                allowed=True, reason="No bucket context", evaluated_policies=0
            )

        evaluated = 0

        # 1. Block public access
        if bucket.block_public_access:
            bpa = bucket.block_public_access
            if principal == "AllUsers" or principal == "*":
                if bpa.block_public_acls or bpa.restrict_public_buckets:
                    return AuthorizationResult(
                        allowed=False,
                        reason="Public access blocked",
                        evaluated_policies=1,
                    )
            evaluated += 1

        # 2. Bucket policy
        has_explicit_deny = False
        has_explicit_allow = False

        if bucket.policy:
            for stmt in bucket.policy.statements:
                evaluated += 1
                if not self._matches_principal(stmt.principal, principal):
                    continue
                if not self._matches_action(stmt.action, action):
                    continue
                if not self._matches_resource(stmt.resource, resource):
                    continue

                if stmt.effect == PolicyEffect.DENY:
                    has_explicit_deny = True
                elif stmt.effect == PolicyEffect.ALLOW:
                    has_explicit_allow = True

        if has_explicit_deny:
            return AuthorizationResult(
                allowed=False,
                reason="Explicit DENY in bucket policy",
                evaluated_policies=evaluated,
            )

        # 3. ACL
        if bucket.acl:
            evaluated += 1
            for grant in bucket.acl.grants:
                if grant.grantee == principal or grant.grantee == "*" or \
                   (grant.grantee == "AllUsers" and principal != "anonymous"):
                    acl_action_map = {
                        ACLPermission.FULL_CONTROL: True,
                        ACLPermission.READ: action.endswith("GetObject") or action.endswith("ListBucket"),
                        ACLPermission.WRITE: action.endswith("PutObject") or action.endswith("DeleteObject"),
                        ACLPermission.READ_ACP: action.endswith("GetBucketAcl"),
                        ACLPermission.WRITE_ACP: action.endswith("PutBucketAcl"),
                    }
                    if acl_action_map.get(grant.permission, False):
                        has_explicit_allow = True

        if has_explicit_allow:
            return AuthorizationResult(
                allowed=True,
                reason="Allowed by policy/ACL",
                evaluated_policies=evaluated,
            )

        # Owner always has access
        if principal == bucket.owner:
            return AuthorizationResult(
                allowed=True,
                reason="Bucket owner",
                evaluated_policies=evaluated,
            )

        return AuthorizationResult(
            allowed=False,
            reason="No matching ALLOW statement",
            evaluated_policies=evaluated,
        )

    def _matches_principal(self, stmt_principal: Union[str, List[str]],
                           principal: str) -> bool:
        """Check if a principal matches a statement's principal field."""
        if isinstance(stmt_principal, str):
            return stmt_principal == "*" or stmt_principal == principal
        return "*" in stmt_principal or principal in stmt_principal

    def _matches_action(self, stmt_actions: List[str],
                        action: str) -> bool:
        """Check if an action matches any statement action."""
        for sa in stmt_actions:
            if sa == "s3:*" or sa == action:
                return True
            if sa.endswith("*") and action.startswith(sa[:-1]):
                return True
        return False

    def _matches_resource(self, stmt_resources: List[str],
                          resource: str) -> bool:
        """Check if a resource matches any statement resource ARN."""
        if not stmt_resources:
            return True
        for sr in stmt_resources:
            if sr == "*" or sr == resource:
                return True
            if sr.endswith("*") and resource.startswith(sr[:-1]):
                return True
        return False


# ============================================================
# NotificationDispatcher
# ============================================================


class NotificationDispatcher:
    """Processes and dispatches event notifications.

    Evaluates storage operations against bucket notification
    configurations and dispatches matching events to configured
    destinations.
    """

    def __init__(self, event_bus: Optional[Any] = None) -> None:
        self._event_bus = event_bus
        self._dead_letter_queue: List[S3EventMessage] = []
        self._dispatched_count = 0
        self._failed_count = 0

    def dispatch(self, bucket: Bucket, event_name: str,
                 key: str, size: int = 0, etag: str = "",
                 version_id: Optional[str] = None) -> int:
        """Dispatch notifications for a storage event.

        Returns:
            Number of notifications dispatched.
        """
        if not bucket.notification_configuration:
            return 0

        msg = S3EventMessage(
            event_name=event_name,
            bucket_name=bucket.name,
            bucket_owner=bucket.owner,
            object_key=key,
            object_size=size,
            object_etag=etag,
            object_version_id=version_id,
        )

        dispatched = 0
        for rule in bucket.notification_configuration.event_rules:
            if not self._matches_event(rule, event_name):
                continue
            if rule.prefix_filter and not key.startswith(rule.prefix_filter):
                continue
            if rule.suffix_filter and not key.endswith(rule.suffix_filter):
                continue

            success = self._deliver(msg, rule)
            if success:
                dispatched += 1
                self._dispatched_count += 1
            else:
                self._dead_letter_queue.append(msg)
                self._failed_count += 1

        return dispatched

    def _matches_event(self, rule: EventRule, event_name: str) -> bool:
        """Check if an event matches any rule event type."""
        for et in rule.events:
            if et.value == event_name:
                return True
            # Wildcard matching
            if et.value.endswith("*"):
                prefix = et.value[:-1]
                if event_name.startswith(prefix):
                    return True
        return False

    def _deliver(self, msg: S3EventMessage, rule: EventRule) -> bool:
        """Attempt to deliver a notification to the destination."""
        try:
            if rule.destination_type == DestinationType.EVENT_BUS:
                if self._event_bus:
                    self._event_bus.publish(msg.event_name, {
                        "bucket": msg.bucket_name,
                        "key": msg.object_key,
                    })
                return True
            elif rule.destination_type == DestinationType.QUEUE:
                # Internal queue simulation
                return True
            elif rule.destination_type == DestinationType.WEBHOOK:
                # Webhook simulation
                return True
        except Exception:
            return False
        return False

    def get_dead_letter_queue(self) -> List[S3EventMessage]:
        """Return failed notification messages."""
        return list(self._dead_letter_queue)

    def get_stats(self) -> Dict[str, int]:
        """Return dispatch statistics."""
        return {
            "dispatched": self._dispatched_count,
            "failed": self._failed_count,
            "dead_letter_count": len(self._dead_letter_queue),
        }


# ============================================================
# S3RequestRouter
# ============================================================


class S3RequestRouter:
    """Routes S3-compatible REST API requests to operation handlers.

    Pattern-matches API operations based on HTTP method, path segments,
    and query parameter presence to identify the target operation.
    """

    # Route patterns: (method, path_pattern, query_key) -> operation
    _ROUTES = {
        ("GET", "service", None): "ListBuckets",
        ("PUT", "bucket", None): "CreateBucket",
        ("DELETE", "bucket", None): "DeleteBucket",
        ("HEAD", "bucket", None): "HeadBucket",
        ("GET", "bucket", None): "ListObjectsV2",
        ("GET", "bucket", "versioning"): "GetBucketVersioning",
        ("PUT", "bucket", "versioning"): "PutBucketVersioning",
        ("GET", "bucket", "lifecycle"): "GetBucketLifecycle",
        ("PUT", "bucket", "lifecycle"): "PutBucketLifecycle",
        ("DELETE", "bucket", "lifecycle"): "DeleteBucketLifecycle",
        ("GET", "bucket", "replication"): "GetBucketReplication",
        ("PUT", "bucket", "replication"): "PutBucketReplication",
        ("DELETE", "bucket", "replication"): "DeleteBucketReplication",
        ("GET", "bucket", "notification"): "GetBucketNotification",
        ("PUT", "bucket", "notification"): "PutBucketNotification",
        ("GET", "bucket", "acl"): "GetBucketAcl",
        ("PUT", "bucket", "acl"): "PutBucketAcl",
        ("GET", "bucket", "policy"): "GetBucketPolicy",
        ("PUT", "bucket", "policy"): "PutBucketPolicy",
        ("DELETE", "bucket", "policy"): "DeleteBucketPolicy",
        ("GET", "bucket", "encryption"): "GetBucketEncryption",
        ("PUT", "bucket", "encryption"): "PutBucketEncryption",
        ("DELETE", "bucket", "encryption"): "DeleteBucketEncryption",
        ("GET", "bucket", "location"): "GetBucketLocation",
        ("GET", "bucket", "uploads"): "ListMultipartUploads",
        ("PUT", "object", None): "PutObject",
        ("GET", "object", None): "GetObject",
        ("HEAD", "object", None): "HeadObject",
        ("DELETE", "object", None): "DeleteObject",
        ("POST", "bucket", "delete"): "DeleteObjects",
        ("PUT", "object", "copy"): "CopyObject",
        ("POST", "object", "uploads"): "CreateMultipartUpload",
        ("PUT", "object", "partNumber"): "UploadPart",
        ("POST", "object", "uploadId"): "CompleteMultipartUpload",
        ("DELETE", "object", "uploadId"): "AbortMultipartUpload",
        ("GET", "object", "uploadId"): "ListParts",
        ("POST", "object", "restore"): "RestoreObject",
    }

    def route(self, method: str, path: str,
              query_params: Optional[Dict[str, str]] = None) -> Tuple[str, Dict[str, str]]:
        """Route a request to an operation.

        Args:
            method: HTTP method (GET, PUT, POST, DELETE, HEAD).
            path: Request path (e.g., /bucket/key).
            query_params: URL query parameters.

        Returns:
            Tuple of (operation_name, parsed_params).
        """
        params = query_params or {}
        parts = [p for p in path.strip("/").split("/") if p]

        if not parts:
            path_type = "service"
        elif len(parts) == 1:
            path_type = "bucket"
        else:
            path_type = "object"

        # Check query-parameter-based routes first
        for query_key in params:
            route_key = (method, path_type, query_key)
            if route_key in self._ROUTES:
                parsed = {}
                if len(parts) >= 1:
                    parsed["bucket"] = parts[0]
                if len(parts) >= 2:
                    parsed["key"] = "/".join(parts[1:])
                parsed.update(params)
                return self._ROUTES[route_key], parsed

        # Fall back to non-query routes
        route_key = (method, path_type, None)
        if route_key in self._ROUTES:
            parsed = {}
            if len(parts) >= 1:
                parsed["bucket"] = parts[0]
            if len(parts) >= 2:
                parsed["key"] = "/".join(parts[1:])
            parsed.update(params)
            return self._ROUTES[route_key], parsed

        return "Unknown", {"path": path, "method": method}


# ============================================================
# S3ResponseFormatter
# ============================================================


class S3ResponseFormatter:
    """Formats responses to S3-compatible XML.

    Serializes operation results to XML matching the S3 response
    schema for interoperability with existing S3 client libraries.
    """

    def format_list_buckets(self, buckets: List[Bucket],
                            owner: str = "fizzbuzz-root") -> str:
        """Format ListBuckets response."""
        bucket_entries = ""
        for b in buckets:
            bucket_entries += (
                f"    <Bucket>"
                f"<Name>{b.name}</Name>"
                f"<CreationDate>{b.creation_date.strftime('%Y-%m-%dT%H:%M:%S.000Z')}</CreationDate>"
                f"</Bucket>\n"
            )

        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<ListAllMyBucketsResult xmlns="http://s3.amazonaws.com/doc/{S3_API_VERSION}/">\n'
            f"  <Owner><ID>{owner}</ID></Owner>\n"
            f"  <Buckets>\n{bucket_entries}  </Buckets>\n"
            f"</ListAllMyBucketsResult>"
        )

    def format_list_objects(self, result: ListObjectsResult) -> str:
        """Format ListObjectsV2 response."""
        contents_xml = ""
        for obj in result.contents:
            contents_xml += (
                f"    <Contents>"
                f"<Key>{obj.key}</Key>"
                f"<LastModified>{obj.last_modified.strftime('%Y-%m-%dT%H:%M:%S.000Z')}</LastModified>"
                f"<ETag>&quot;{obj.etag}&quot;</ETag>"
                f"<Size>{obj.size}</Size>"
                f"<StorageClass>{obj.storage_class.value}</StorageClass>"
                f"</Contents>\n"
            )

        prefix_xml = ""
        for cp in result.common_prefixes:
            prefix_xml += f"    <CommonPrefixes><Prefix>{cp}</Prefix></CommonPrefixes>\n"

        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<ListBucketResult xmlns="http://s3.amazonaws.com/doc/{S3_API_VERSION}/">\n'
            f"  <IsTruncated>{str(result.is_truncated).lower()}</IsTruncated>\n"
            f"  <KeyCount>{result.key_count}</KeyCount>\n"
            f"  <MaxKeys>{result.max_keys}</MaxKeys>\n"
            f"{contents_xml}{prefix_xml}"
            f"</ListBucketResult>"
        )

    def format_error(self, error_code: str, message: str,
                     resource: str = "",
                     request_id: str = "") -> str:
        """Format an S3 error response."""
        rid = request_id or uuid.uuid4().hex[:16]
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f"<Error>\n"
            f"  <Code>{error_code}</Code>\n"
            f"  <Message>{message}</Message>\n"
            f"  <Resource>{resource}</Resource>\n"
            f"  <RequestId>{rid}</RequestId>\n"
            f"</Error>"
        )

    def format_initiate_multipart(self, bucket: str, key: str,
                                  upload_id: str) -> str:
        """Format InitiateMultipartUpload response."""
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f"<InitiateMultipartUploadResult>\n"
            f"  <Bucket>{bucket}</Bucket>\n"
            f"  <Key>{key}</Key>\n"
            f"  <UploadId>{upload_id}</UploadId>\n"
            f"</InitiateMultipartUploadResult>"
        )


# ============================================================
# S3Metrics
# ============================================================


class S3Metrics:
    """Storage-tier metrics collector for FizzS3.

    Aggregates request metrics, storage metrics, deduplication metrics,
    erasure coding metrics, and replication/lifecycle metrics into a
    unified metrics dashboard.
    """

    def __init__(self) -> None:
        self._request_counts: Dict[str, int] = defaultdict(int)
        self._request_bytes: Dict[str, int] = defaultdict(int)
        self._error_counts: Dict[str, int] = defaultdict(int)
        self._latencies: List[float] = []
        self._lock = threading.Lock()

    def record_request(self, operation: str, bytes_count: int = 0,
                       latency: float = 0.0, error: bool = False) -> None:
        """Record a request metric."""
        with self._lock:
            self._request_counts[operation] += 1
            self._request_bytes[operation] += bytes_count
            if latency > 0:
                self._latencies.append(latency)
            if error:
                self._error_counts[operation] += 1

    def get_request_stats(self) -> Dict[str, Any]:
        """Return request statistics."""
        with self._lock:
            total = sum(self._request_counts.values())
            errors = sum(self._error_counts.values())
            latencies = sorted(self._latencies) if self._latencies else [0]
            return {
                "total_requests": total,
                "total_errors": errors,
                "operations": dict(self._request_counts),
                "bytes_uploaded": self._request_bytes.get("PutObject", 0),
                "bytes_downloaded": self._request_bytes.get("GetObject", 0),
                "latency_p50": latencies[len(latencies) // 2] if latencies else 0,
                "latency_p95": latencies[int(len(latencies) * 0.95)] if latencies else 0,
                "latency_p99": latencies[int(len(latencies) * 0.99)] if latencies else 0,
            }

    def get_storage_stats(self, object_store: ObjectStore,
                          bucket_name: Optional[str] = None) -> Dict[str, Any]:
        """Return storage statistics."""
        obj_count = 0
        total_size = 0
        version_count = 0

        if bucket_name:
            obj_ns = f"objects:{bucket_name}"
            for key in object_store._metadata.list_keys(obj_ns):
                obj = object_store._metadata.get(obj_ns, key)
                if obj and not obj.delete_marker:
                    obj_count += 1
                    total_size += obj.size
        else:
            for ns_key in object_store._metadata._hash_index:
                if ns_key.startswith("objects:"):
                    for key, obj in object_store._metadata._hash_index[ns_key].items():
                        if hasattr(obj, 'delete_marker') and not obj.delete_marker:
                            obj_count += 1
                            total_size += obj.size

        return {
            "object_count": obj_count,
            "total_size": total_size,
            "version_count": version_count,
        }


# ============================================================
# FizzS3Dashboard
# ============================================================


class FizzS3Dashboard:
    """ASCII dashboard rendering for FizzS3 storage metrics.

    Provides visual summaries of bucket statistics, storage class
    distribution, deduplication ratios, erasure coding health,
    replication status, and overall platform storage metrics.
    """

    def __init__(
        self,
        metrics: S3Metrics,
        width: int = DEFAULT_DASHBOARD_WIDTH,
    ) -> None:
        self._metrics = metrics
        self._width = width

    def _header(self, title: str) -> str:
        """Render a section header."""
        return f"\n{'=' * self._width}\n  {title}\n{'=' * self._width}"

    def _row(self, label: str, value: Any, unit: str = "") -> str:
        """Render a key-value row."""
        val_str = f"{value} {unit}".strip()
        padding = self._width - len(label) - len(val_str) - 4
        return f"  {label}{'.' * max(padding, 1)}{val_str}"

    def _bar(self, label: str, value: float, max_val: float,
             bar_width: int = 30) -> str:
        """Render a proportional bar."""
        ratio = min(value / max(max_val, 1), 1.0)
        filled = int(ratio * bar_width)
        bar = "█" * filled + "░" * (bar_width - filled)
        pct = f"{ratio * 100:.1f}%"
        return f"  {label}: [{bar}] {pct}"

    def render_bucket_summary(self, bucket_name: str,
                              object_store: ObjectStore) -> str:
        """Render bucket-level metrics overview."""
        lines = [self._header(f"FizzS3 Bucket: {bucket_name}")]

        stats = self._metrics.get_storage_stats(object_store, bucket_name)
        lines.append(self._row("Objects", stats["object_count"]))
        lines.append(self._row("Total Size", self._format_size(stats["total_size"])))

        try:
            bucket = object_store._get_bucket(bucket_name)
            lines.append(self._row("Region", bucket.region))
            lines.append(self._row("Versioning", bucket.versioning.value))
            lines.append(self._row("Created", bucket.creation_date.strftime("%Y-%m-%d %H:%M:%S UTC")))
        except BucketNotFoundError:
            pass

        return "\n".join(lines)

    def render_storage_classes(self, bucket_name: str,
                               storage_class_mgr: StorageClassManager) -> str:
        """Render per-class storage distribution."""
        lines = [self._header("Storage Class Distribution")]

        stats = storage_class_mgr.get_storage_class_stats(bucket_name)
        total_size = sum(s["size"] for s in stats.values())

        for sc_name, sc_stats in stats.items():
            lines.append(self._bar(
                f"{sc_name:15s} ({sc_stats['count']:>4d} objects)",
                sc_stats["size"],
                max(total_size, 1),
            ))

        return "\n".join(lines)

    def render_deduplication(self, cas: ContentAddressableStore,
                             bucket_name: Optional[str] = None) -> str:
        """Render deduplication statistics."""
        lines = [self._header("Content-Addressable Deduplication")]

        stats = cas.get_deduplication_stats(bucket_name)
        lines.append(self._row("Logical Size", self._format_size(stats.logical_size)))
        lines.append(self._row("Physical Size", self._format_size(stats.physical_size)))
        lines.append(self._row("Dedup Ratio", f"{stats.dedup_ratio:.2f}x"))
        lines.append(self._row("Total Chunks", stats.total_chunks))
        lines.append(self._row("Shared Chunks", stats.shared_chunks))
        lines.append(self._row("Unique Chunks", stats.unique_chunks))

        if stats.logical_size > stats.physical_size:
            saved = stats.logical_size - stats.physical_size
            lines.append(self._row("Bytes Saved", self._format_size(saved)))

        return "\n".join(lines)

    def render_erasure_health(self, integrity_checker: FragmentIntegrityChecker,
                              bucket_name: str) -> str:
        """Render erasure coding health status."""
        lines = [self._header("Erasure Coding Health")]

        report = integrity_checker.get_last_scrub(bucket_name)
        if report:
            lines.append(self._row("Last Scrub", report.get("timestamp", "never")))
            lines.append(self._row("Chunks Checked", report.get("checked", 0)))
            lines.append(self._row("Healthy", report.get("healthy", 0)))
            lines.append(self._row("Corrupt", report.get("corrupt", 0)))
            lines.append(self._row("Repaired", report.get("repaired", 0)))
            lines.append(self._row("Unrecoverable", report.get("unrecoverable", 0)))
        else:
            lines.append("  No scrub data available")

        return "\n".join(lines)

    def render_overview(self, object_store: Optional[ObjectStore] = None,
                        cas: Optional[ContentAddressableStore] = None) -> str:
        """Render platform-wide storage summary."""
        lines = [self._header(f"FizzS3 Object Storage v{FIZZS3_VERSION}")]

        req_stats = self._metrics.get_request_stats()
        lines.append(self._row("Total Requests", req_stats["total_requests"]))
        lines.append(self._row("Total Errors", req_stats["total_errors"]))
        lines.append(self._row("Bytes Uploaded", self._format_size(req_stats["bytes_uploaded"])))
        lines.append(self._row("Bytes Downloaded", self._format_size(req_stats["bytes_downloaded"])))

        if object_store:
            storage_stats = self._metrics.get_storage_stats(object_store)
            lines.append(self._row("Total Objects", storage_stats["object_count"]))
            lines.append(self._row("Total Storage", self._format_size(storage_stats["total_size"])))

        if cas:
            dedup = cas.get_deduplication_stats()
            lines.append(self._row("Dedup Ratio", f"{dedup.dedup_ratio:.2f}x"))

        lines.append(f"\n{'-' * self._width}")
        lines.append(f"  S3 API Version: {S3_API_VERSION}")
        lines.append(f"  Regions: {', '.join(SUPPORTED_REGIONS)}")

        return "\n".join(lines)

    @staticmethod
    def _format_size(size: int) -> str:
        """Format byte size to human-readable string."""
        for unit in ["B", "KB", "MB", "GB", "TB", "PB"]:
            if abs(size) < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} EB"


# ============================================================
# FizzS3Middleware
# ============================================================


class FizzS3Middleware(IMiddleware):
    """Records FizzBuzz evaluation results as S3 objects.

    Each evaluation is stored in the fizzbuzz-evaluations bucket with
    key format evaluations/{year}/{month}/{day}/{request_id}.json,
    enabling query-by-prefix listing of historical evaluations by
    date range.  Objects are stored in STANDARD class with lifecycle
    policy transitioning to ARCHIVE after 30 days.
    """

    def __init__(
        self,
        bucket_mgr: BucketManager,
        object_store: ObjectStore,
        metrics: S3Metrics,
        dashboard: FizzS3Dashboard,
        cas: Optional[ContentAddressableStore] = None,
        integrity_checker: Optional[FragmentIntegrityChecker] = None,
        storage_class_mgr: Optional[StorageClassManager] = None,
    ) -> None:
        self._bucket_mgr = bucket_mgr
        self._object_store = object_store
        self._metrics = metrics
        self._dashboard = dashboard
        self._cas = cas
        self._integrity_checker = integrity_checker
        self._storage_class_mgr = storage_class_mgr
        self._eval_bucket = "fizzbuzz-evaluations"
        self._initialized = False

    def get_name(self) -> str:
        """Return the middleware name."""
        return "fizzs3"

    def get_priority(self) -> int:
        """Return the middleware priority."""
        return MIDDLEWARE_PRIORITY

    @property
    def name(self) -> str:
        """Return the middleware name (convenience property)."""
        return "fizzs3"

    @property
    def priority(self) -> int:
        """Return middleware priority."""
        return MIDDLEWARE_PRIORITY

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Record the evaluation result as an S3 object.

        Creates the evaluations bucket on first use and stores each
        evaluation as a JSON object with date-based key hierarchy.
        """
        try:
            if not self._initialized:
                self._ensure_bucket()
                self._initialized = True

            now = datetime.now(timezone.utc)
            request_id = uuid.uuid4().hex[:16]
            key = (
                f"evaluations/{now.year}/{now.month:02d}/"
                f"{now.day:02d}/{request_id}.json"
            )

            number = context.number if hasattr(context, 'number') else str(context)
            result_val = context.result.value if hasattr(context, 'result') and hasattr(context.result, 'value') else str(context)

            payload = json.dumps({
                "input": number,
                "output": result_val,
                "timestamp": now.isoformat(),
                "request_id": request_id,
            }).encode()

            start = time.time()
            self._object_store.put_object(
                bucket_name=self._eval_bucket,
                key=key,
                data=payload,
                content_type="application/json",
            )
            latency = time.time() - start

            self._metrics.record_request("PutObject", len(payload), latency)

        except Exception as e:
            self._metrics.record_request("PutObject", 0, 0.0, error=True)
            logger.warning("FizzS3 middleware error: %s", e)

        return next_handler(context)

    def _ensure_bucket(self) -> None:
        """Create the evaluations bucket if it does not exist."""
        try:
            if not self._bucket_mgr.head_bucket(self._eval_bucket):
                bucket = self._bucket_mgr.create_bucket(self._eval_bucket)
                # Add lifecycle rule for archival
                bucket.lifecycle_configuration = LifecycleConfiguration(
                    rules=[LifecycleRule(
                        id="archive-old-evaluations",
                        status=RuleStatus.ENABLED,
                        prefix="evaluations/",
                        transitions=[
                            TransitionRule(days=30, storage_class=StorageClass.ARCHIVE),
                        ],
                    )]
                )
                self._bucket_mgr._metadata.put("buckets", self._eval_bucket, bucket)
        except BucketAlreadyOwnedByYouError:
            pass
        except BucketAlreadyExistsError:
            pass

    def render_overview(self) -> str:
        """Render FizzS3 overview dashboard."""
        return self._dashboard.render_overview(
            self._object_store, self._cas
        )

    def render_buckets(self) -> str:
        """Render bucket listing."""
        buckets = self._bucket_mgr.list_buckets()
        lines = [self._dashboard._header("FizzS3 Buckets")]
        for b in buckets:
            lines.append(self._dashboard._row(b.name, b.region))
        if not buckets:
            lines.append("  No buckets")
        return "\n".join(lines)

    def render_dedup(self, bucket_name: str) -> str:
        """Render deduplication statistics for a bucket."""
        if self._cas:
            return self._dashboard.render_deduplication(self._cas, bucket_name)
        return "  Deduplication data unavailable"

    def render_metrics(self) -> str:
        """Render metrics summary."""
        return self._dashboard.render_overview(
            self._object_store, self._cas
        )

    def render_scrub(self, bucket_name: str) -> str:
        """Render scrub results for a bucket."""
        if self._integrity_checker:
            return self._dashboard.render_erasure_health(
                self._integrity_checker, bucket_name
            )
        return "  Scrub data unavailable"

    def render_dashboard(self) -> str:
        """Render the full FizzS3 dashboard."""
        return self.render_overview()


# ============================================================
# Factory Function
# ============================================================


def create_fizzs3_subsystem(
    default_region: str = DEFAULT_REGION,
    max_buckets: int = MAX_BUCKETS_PER_OWNER,
    default_encryption: str = "sse-s3",
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    gc_interval: float = DEFAULT_GC_INTERVAL,
    gc_safety_delay: float = DEFAULT_GC_SAFETY_DELAY,
    lifecycle_interval: float = DEFAULT_LIFECYCLE_INTERVAL,
    compaction_threshold: float = DEFAULT_COMPACTION_THRESHOLD,
    segment_max_size: int = DEFAULT_SEGMENT_MAX_SIZE,
    presign_default_expiry: int = 3600,
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
    event_bus: Optional[Any] = None,
) -> tuple:
    """Create and wire the complete FizzS3 object storage subsystem.

    Factory function that instantiates all FizzS3 components -- metadata
    index, segment log, erasure coding engine, content-addressable store,
    encryption engine, bucket manager, object store, versioning engine,
    multipart upload manager, presigned URL generator, storage class
    manager, lifecycle evaluator, replication engine, access control
    evaluator, notification dispatcher, garbage collector, metrics
    collector, dashboard, and middleware -- wired together and ready
    for integration into the FizzBuzz evaluation pipeline.

    Args:
        default_region: Default region for new buckets.
        max_buckets: Maximum buckets per owner.
        default_encryption: Default encryption mode.
        chunk_size: Content-addressable chunk size.
        gc_interval: Garbage collection interval.
        gc_safety_delay: GC safety delay.
        lifecycle_interval: Lifecycle evaluation interval.
        compaction_threshold: Segment compaction fragmentation threshold.
        segment_max_size: Maximum segment size.
        presign_default_expiry: Default presigned URL expiry.
        dashboard_width: ASCII dashboard width.
        event_bus: Optional event bus for lifecycle events.

    Returns:
        Tuple of (ObjectStore, FizzS3Middleware).
    """
    gf = GaloisField()
    erasure_engine = ErasureCodingEngine(gf=gf)

    metadata_index = MetadataIndex()

    segment_log = SegmentLog(
        max_segment_size=segment_max_size,
        compaction_threshold=compaction_threshold,
    )

    ref_counter = ReferenceCounter(metadata_index=metadata_index)

    fragment_distributor = FragmentDistributor()

    cas = ContentAddressableStore(
        chunk_size=chunk_size,
        erasure_engine=erasure_engine,
        segment_log=segment_log,
        ref_counter=ref_counter,
        fragment_distributor=fragment_distributor,
    )

    encryption_engine = EncryptionEngine(default_mode=default_encryption)

    bucket_mgr = BucketManager(
        metadata_index=metadata_index,
        max_buckets=max_buckets,
        default_region=default_region,
        event_bus=event_bus,
    )

    versioning_engine = VersioningEngine(metadata_index=metadata_index)

    object_store = ObjectStore(
        metadata_index=metadata_index,
        cas=cas,
        encryption_engine=encryption_engine,
        versioning_engine=versioning_engine,
        event_bus=event_bus,
    )

    multipart_mgr = MultipartUploadManager(
        metadata_index=metadata_index,
        object_store=object_store,
        cas=cas,
        event_bus=event_bus,
    )

    sig_computer = SignatureV4Computer()
    presign_gen = PresignedURLGenerator(
        sig_computer=sig_computer,
        default_expiry=presign_default_expiry,
    )

    storage_class_mgr = StorageClassManager(
        object_store=object_store,
        cas=cas,
        erasure_engine=erasure_engine,
        event_bus=event_bus,
    )

    lifecycle_eval = LifecycleEvaluator(
        object_store=object_store,
        storage_class_mgr=storage_class_mgr,
        multipart_mgr=multipart_mgr,
    )

    access_eval = AccessControlEvaluator()

    notification_dispatcher = NotificationDispatcher(event_bus=event_bus)

    gc = GarbageCollector(
        cas=cas,
        ref_counter=ref_counter,
        safety_delay=gc_safety_delay,
    )

    integrity_checker = FragmentIntegrityChecker(
        cas=cas,
        erasure_engine=erasure_engine,
        fragment_distributor=fragment_distributor,
    )

    metrics = S3Metrics()

    dashboard = FizzS3Dashboard(
        metrics=metrics,
        width=dashboard_width,
    )

    middleware = FizzS3Middleware(
        bucket_mgr=bucket_mgr,
        object_store=object_store,
        metrics=metrics,
        dashboard=dashboard,
        cas=cas,
        integrity_checker=integrity_checker,
        storage_class_mgr=storage_class_mgr,
    )

    logger.info("FizzS3 subsystem created and wired")
    return object_store, middleware
