# Implementation Plan: FizzS3 -- S3-Compatible Object Storage

**Date:** 2026-03-24
**Module:** `enterprise_fizzbuzz/infrastructure/fizzs3.py`
**Target:** ~3,500 lines + ~500 tests
**Middleware Priority:** 118
**Error Code Prefix:** EFP-S3
**Reference Architecture:** Amazon S3, MinIO, Ceph RADOS Gateway

---

## 1. Module Docstring

```python
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
```

---

## 2. Imports

```python
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
```

---

## 3. Constants (~30)

| Constant | Value | Description |
|----------|-------|-------------|
| `FIZZS3_VERSION` | `"1.0.0"` | FizzS3 subsystem version |
| `S3_API_VERSION` | `"2006-03-01"` | S3 REST API version compatibility |
| `DEFAULT_REGION` | `"fizz-east-1"` | Default bucket region |
| `SUPPORTED_REGIONS` | `["fizz-east-1", "fizz-west-1", "fizz-eu-1", "fizz-ap-1"]` | Available regions |
| `MAX_BUCKET_NAME_LENGTH` | `63` | Maximum bucket name length |
| `MIN_BUCKET_NAME_LENGTH` | `3` | Minimum bucket name length |
| `MAX_BUCKETS_PER_OWNER` | `100` | Maximum buckets per owner |
| `MAX_OBJECT_KEY_LENGTH` | `1024` | Maximum object key length in bytes |
| `MAX_SINGLE_PUT_SIZE` | `5 * 1024**3` | Maximum single PUT size (5 GiB) |
| `MAX_OBJECT_SIZE` | `5 * 1024**4` | Maximum object size (5 TiB) |
| `MAX_METADATA_SIZE` | `2048` | Maximum user metadata size in bytes |
| `MAX_TAGS_PER_BUCKET` | `50` | Maximum tags per bucket |
| `MIN_PART_SIZE` | `5 * 1024**2` | Minimum multipart part size (5 MB) |
| `MAX_PART_SIZE` | `5 * 1024**3` | Maximum multipart part size (5 GiB) |
| `MAX_PARTS` | `10000` | Maximum parts per multipart upload |
| `MAX_LIST_KEYS` | `1000` | Maximum keys per list response |
| `MAX_DELETE_OBJECTS` | `1000` | Maximum objects per batch delete |
| `MAX_LIFECYCLE_RULES` | `1000` | Maximum lifecycle rules per bucket |
| `MAX_REPLICATION_RULES` | `1000` | Maximum replication rules per bucket |
| `MAX_PRESIGN_EXPIRY` | `604800` | Maximum presigned URL validity (7 days) |
| `CLOCK_SKEW_TOLERANCE` | `900` | Maximum request clock skew (15 minutes) |
| `DEFAULT_CHUNK_SIZE` | `4 * 1024**2` | Default content-addressable chunk size (4 MB) |
| `DEFAULT_SEGMENT_MAX_SIZE` | `256 * 1024**2` | Maximum segment size (256 MB) |
| `DEFAULT_COMPACTION_THRESHOLD` | `0.5` | Segment fragmentation compaction trigger |
| `DEFAULT_GC_INTERVAL` | `21600.0` | Garbage collection interval (6 hours) |
| `DEFAULT_GC_SAFETY_DELAY` | `86400.0` | GC safety delay (24 hours) |
| `DEFAULT_CHECKPOINT_INTERVAL` | `60.0` | Metadata checkpoint interval (60 seconds) |
| `DEFAULT_LIFECYCLE_INTERVAL` | `86400.0` | Lifecycle evaluation interval (24 hours) |
| `DEFAULT_REPLICATION_RETRY_MAX` | `24` | Maximum replication retries |
| `DEFAULT_DASHBOARD_WIDTH` | `72` | ASCII dashboard width |
| `MIDDLEWARE_PRIORITY` | `118` | Middleware pipeline priority |

---

## 4. Enums (~12)

### 4.1 `BucketVersioning(Enum)`

Bucket versioning states.  Once enabled, versioning cannot return to DISABLED -- only SUSPENDED.

| Member | Value | Description |
|--------|-------|-------------|
| `DISABLED` | `"disabled"` | Versioning has never been enabled (initial state) |
| `ENABLED` | `"enabled"` | Every PUT creates a new version with a UUID version ID |
| `SUSPENDED` | `"suspended"` | New PUTs receive null version ID; existing versions preserved |

### 4.2 `StorageClass(Enum)`

Storage tier with distinct erasure coding parameters, access latency, and cost characteristics.

| Member | Value | Data:Parity | Min Duration | Description |
|--------|-------|-------------|--------------|-------------|
| `STANDARD` | `"STANDARD"` | 10:4 | -- | Millisecond access, 99.99% availability |
| `STANDARD_IA` | `"STANDARD_IA"` | 6:4 | 30 days | Infrequent access, retrieval fee, 128 KB min billing |
| `ARCHIVE` | `"ARCHIVE"` | 4:4 | 90 days | Restore required (1 min - 12 hr), retrieval fee |
| `DEEP_ARCHIVE` | `"DEEP_ARCHIVE"` | 2:4 | 180 days | Restore required (12 - 48 hr), lowest cost |

### 4.3 `RestoreTier(Enum)`

Archive restore speed tiers.

| Member | Value | Description |
|--------|-------|-------------|
| `EXPEDITED` | `"expedited"` | 1-5 minutes (ARCHIVE) |
| `STANDARD` | `"standard"` | 3-5 hours (ARCHIVE), 12 hours (DEEP_ARCHIVE) |
| `BULK` | `"bulk"` | 5-12 hours (ARCHIVE), 48 hours (DEEP_ARCHIVE) |

### 4.4 `EncryptionMode(Enum)`

Server-side encryption modes.

| Member | Value | Description |
|--------|-------|-------------|
| `SSE_S3` | `"sse-s3"` | FizzS3-managed key, automatic rotation |
| `SSE_KMS` | `"sse-kms"` | FizzVault-managed key, auditable usage |
| `SSE_C` | `"sse-c"` | Client-provided key, never stored |

### 4.5 `EncryptionAlgorithm(Enum)`

Encryption algorithm identifier.

| Member | Value | Description |
|--------|-------|-------------|
| `AES_256` | `"AES256"` | AES-256-GCM authenticated encryption |

### 4.6 `PolicyEffect(Enum)`

IAM policy statement effect.

| Member | Value | Description |
|--------|-------|-------------|
| `ALLOW` | `"Allow"` | Grants access |
| `DENY` | `"Deny"` | Explicitly denies access |

### 4.7 `ACLPermission(Enum)`

Access control list permission levels.

| Member | Value | Description |
|--------|-------|-------------|
| `FULL_CONTROL` | `"FULL_CONTROL"` | All permissions |
| `READ` | `"READ"` | Read objects or list bucket |
| `WRITE` | `"WRITE"` | Write objects to bucket |
| `READ_ACP` | `"READ_ACP"` | Read the ACL |
| `WRITE_ACP` | `"WRITE_ACP"` | Modify the ACL |

### 4.8 `CannedACL(Enum)`

Predefined ACL configurations.

| Member | Value | Description |
|--------|-------|-------------|
| `PRIVATE` | `"private"` | Owner gets FULL_CONTROL, no other grants |
| `PUBLIC_READ` | `"public-read"` | Owner FULL_CONTROL, AllUsers READ |
| `PUBLIC_READ_WRITE` | `"public-read-write"` | Owner FULL_CONTROL, AllUsers READ + WRITE |
| `AUTHENTICATED_READ` | `"authenticated-read"` | Owner FULL_CONTROL, AuthenticatedUsers READ |
| `BUCKET_OWNER_READ` | `"bucket-owner-read"` | Object owner FULL_CONTROL, bucket owner READ |
| `BUCKET_OWNER_FULL_CONTROL` | `"bucket-owner-full-control"` | Both owners FULL_CONTROL |

### 4.9 `S3EventType(Enum)`

Object lifecycle event types for notification configuration.

| Member | Value | Description |
|--------|-------|-------------|
| `OBJECT_CREATED_ALL` | `"s3:ObjectCreated:*"` | Any object creation |
| `OBJECT_CREATED_PUT` | `"s3:ObjectCreated:Put"` | Object created via PUT |
| `OBJECT_CREATED_POST` | `"s3:ObjectCreated:Post"` | Object created via presigned POST |
| `OBJECT_CREATED_COPY` | `"s3:ObjectCreated:Copy"` | Object created via COPY |
| `OBJECT_CREATED_MPU` | `"s3:ObjectCreated:CompleteMultipartUpload"` | Object created via multipart completion |
| `OBJECT_REMOVED_ALL` | `"s3:ObjectRemoved:*"` | Any object removal |
| `OBJECT_REMOVED_DELETE` | `"s3:ObjectRemoved:Delete"` | Object permanently deleted |
| `OBJECT_REMOVED_DELETE_MARKER` | `"s3:ObjectRemoved:DeleteMarkerCreated"` | Delete marker created |
| `OBJECT_RESTORE_POST` | `"s3:ObjectRestore:Post"` | Restore initiated |
| `OBJECT_RESTORE_COMPLETED` | `"s3:ObjectRestore:Completed"` | Restore completed |
| `OBJECT_TRANSITION` | `"s3:ObjectTransition"` | Storage class transition |
| `REPLICATION_ALL` | `"s3:Replication:*"` | Any replication event |
| `REPLICATION_COMPLETED` | `"s3:Replication:OperationCompleted"` | Successful replication |
| `REPLICATION_FAILED` | `"s3:Replication:OperationFailed"` | Replication failed |
| `LIFECYCLE_EXPIRATION_DELETE` | `"s3:LifecycleExpiration:Delete"` | Lifecycle expiration |
| `LIFECYCLE_EXPIRATION_MARKER` | `"s3:LifecycleExpiration:DeleteMarkerCreated"` | Lifecycle delete marker |

### 4.10 `DestinationType(Enum)`

Notification destination types.

| Member | Value | Description |
|--------|-------|-------------|
| `EVENT_BUS` | `"event_bus"` | Publish to FizzEventBus topic |
| `WEBHOOK` | `"webhook"` | POST to FizzWebhook URL |
| `QUEUE` | `"queue"` | Enqueue to internal polling queue |

### 4.11 `RuleStatus(Enum)`

Status for lifecycle and replication rules.

| Member | Value | Description |
|--------|-------|-------------|
| `ENABLED` | `"Enabled"` | Rule is active and evaluated |
| `DISABLED` | `"Disabled"` | Rule is retained but not evaluated |

### 4.12 `SegmentStatus(Enum)`

Segment lifecycle states in the data tier.

| Member | Value | Description |
|--------|-------|-------------|
| `ACTIVE` | `"active"` | Currently accepting writes |
| `SEALED` | `"sealed"` | Immutable, read-only |
| `COMPACTING` | `"compacting"` | Being compacted |
| `DELETED` | `"deleted"` | Marked for removal |

---

## 5. Data Classes (~25)

### 5.1 `Bucket`

```python
@dataclass
class Bucket:
    """Top-level namespace container for objects in FizzS3.

    Buckets have globally unique names validated against S3 naming rules,
    a region assignment, versioning state, and configurations for lifecycle,
    access control, encryption, replication, and event notifications.

    Attributes:
        name: Globally unique bucket identifier (3-63 chars, lowercase).
        region: Region where bucket data is stored.
        creation_date: UTC timestamp of bucket creation.
        owner: Principal ID of the bucket owner.
        versioning: Versioning state (DISABLED, ENABLED, SUSPENDED).
        lifecycle_configuration: Lifecycle rules for object management.
        acl: Access control list.
        policy: IAM-style bucket policy document.
        encryption_configuration: Default server-side encryption settings.
        replication_configuration: Cross-region replication rules.
        notification_configuration: Event notification rules.
        block_public_access: Public access prevention settings.
        object_lock_enabled: Whether S3 Object Lock is enabled.
        tags: Bucket-level tags for cost allocation (max 50).
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
```

### 5.2 `S3Object`

```python
@dataclass
class S3Object:
    """Fundamental storage unit in FizzS3.

    Each object consists of a key within a bucket, a data payload, system
    and user metadata, a storage class assignment, and optional versioning
    and encryption information.

    Attributes:
        key: Object key within its bucket (max 1024 bytes UTF-8).
        bucket_name: Name of the containing bucket.
        version_id: Version identifier (UUID for versioned, None for unversioned).
        data: Object content payload.
        size: Size of the data payload in bytes.
        etag: Entity tag (MD5 hex digest or composite for multipart).
        content_type: MIME type of the object content.
        content_encoding: Encoding applied to content (gzip, deflate).
        content_disposition: Presentation information.
        content_language: Language of content (e.g., en-US, tlh for Klingon).
        cache_control: Caching directives.
        last_modified: UTC timestamp of last modification.
        storage_class: Storage class assignment.
        metadata: User-defined metadata key-value pairs.
        server_side_encryption: Encryption algorithm and key info.
        delete_marker: Whether this version is a delete marker.
        is_latest: Whether this is the current version.
        checksum_sha256: Optional SHA-256 integrity checksum.
        replication_status: Replication state (PENDING, COMPLETED, FAILED, REPLICA).
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
```

### 5.3 `ObjectSummary`

```python
@dataclass
class ObjectSummary:
    """Lightweight object metadata returned in list operations.

    Attributes:
        key: Object key.
        last_modified: Last modification timestamp.
        etag: Entity tag.
        size: Object size in bytes.
        storage_class: Storage class.
        owner: Owner principal ID.
    """
    key: str
    last_modified: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    etag: str = ""
    size: int = 0
    storage_class: StorageClass = StorageClass.STANDARD
    owner: str = "fizzbuzz-root"
```

### 5.4 `ListObjectsResult`

```python
@dataclass
class ListObjectsResult:
    """Response model for list_objects_v2.

    Attributes:
        contents: Objects matching the query.
        common_prefixes: Key prefixes rolled up by delimiter.
        is_truncated: Whether results were truncated.
        next_continuation_token: Pagination token for next page.
        key_count: Keys returned in this response.
        max_keys: Maximum keys requested.
        prefix: Prefix filter applied.
        delimiter: Delimiter used for hierarchy simulation.
    """
    contents: List[ObjectSummary] = field(default_factory=list)
    common_prefixes: List[str] = field(default_factory=list)
    is_truncated: bool = False
    next_continuation_token: Optional[str] = None
    key_count: int = 0
    max_keys: int = MAX_LIST_KEYS
    prefix: Optional[str] = None
    delimiter: Optional[str] = None
```

### 5.5 `DeleteMarker`

```python
@dataclass
class DeleteMarker:
    """Zero-byte object version indicating deletion in a versioned bucket.

    Attributes:
        key: Object key.
        version_id: Version ID of the delete marker.
        last_modified: When the delete was issued.
        owner: Principal who issued the delete.
        is_latest: Whether this is the current version.
    """
    key: str
    version_id: str = ""
    last_modified: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    owner: str = "fizzbuzz-root"
    is_latest: bool = True
```

### 5.6 `MultipartUpload`

```python
@dataclass
class MultipartUpload:
    """In-progress multipart upload session.

    Attributes:
        upload_id: Unique upload session identifier.
        bucket: Target bucket name.
        key: Target object key.
        initiated: When the upload was initiated.
        storage_class: Storage class for the completed object.
        encryption: Encryption configuration.
        metadata: User-defined metadata for the completed object.
        content_type: MIME type for the completed object.
        parts: Map of part number to uploaded part metadata.
    """
    upload_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    bucket: str = ""
    key: str = ""
    initiated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    storage_class: StorageClass = StorageClass.STANDARD
    encryption: Optional[ServerSideEncryption] = None
    metadata: Dict[str, str] = field(default_factory=dict)
    content_type: str = "application/octet-stream"
    parts: Dict[int, UploadPart] = field(default_factory=dict)
```

### 5.7 `UploadPart`

```python
@dataclass
class UploadPart:
    """Metadata for a single uploaded part.

    Attributes:
        part_number: Sequence number (1-10000).
        etag: MD5 hex digest of part data.
        size: Part size in bytes.
        last_modified: When the part was uploaded.
        data: Part content (held until completion).
    """
    part_number: int = 1
    etag: str = ""
    size: int = 0
    last_modified: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    data: bytes = b""
```

### 5.8 `ServerSideEncryption`

```python
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
```

### 5.9 `EncryptionConfiguration`

```python
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
```

### 5.10 `BlockPublicAccessConfiguration`

```python
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
```

### 5.11 `AccessControlList`

```python
@dataclass
class AccessControlList:
    """ACL-based access control for a bucket or object.

    Attributes:
        owner: Bucket or object owner.
        grants: Access grants.
    """
    owner: str = "fizzbuzz-root"
    grants: List[Grant] = field(default_factory=list)
```

### 5.12 `Grant`

```python
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
```

### 5.13 `BucketPolicy`

```python
@dataclass
class BucketPolicy:
    """IAM-style policy document for bucket access control.

    Attributes:
        version: Policy language version.
        statements: Policy statements.
    """
    version: str = "2012-10-17"
    statements: List[PolicyStatement] = field(default_factory=list)
```

### 5.14 `PolicyStatement`

```python
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
```

### 5.15 `LifecycleConfiguration`

```python
@dataclass
class LifecycleConfiguration:
    """Lifecycle rules governing object transitions and expirations.

    Attributes:
        rules: Lifecycle rules (max 1000 per bucket).
    """
    rules: List[LifecycleRule] = field(default_factory=list)
```

### 5.16 `LifecycleRule`

```python
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
```

### 5.17 `TransitionRule`

```python
@dataclass
class TransitionRule:
    """Storage class transition trigger within a lifecycle rule.

    Attributes:
        days: Days after creation to trigger transition.
        storage_class: Target storage class.
    """
    days: int = 30
    storage_class: StorageClass = StorageClass.STANDARD_IA
```

### 5.18 `NoncurrentVersionTransitionRule`

```python
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
```

### 5.19 `ReplicationConfiguration`

```python
@dataclass
class ReplicationConfiguration:
    """Cross-region replication rules for a source bucket.

    Attributes:
        role: IAM role assumed by the replication engine.
        rules: Replication rules (max 1000).
    """
    role: str = "fizz-replication-role"
    rules: List[ReplicationRule] = field(default_factory=list)
```

### 5.20 `ReplicationRule`

```python
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
```

### 5.21 `NotificationConfiguration`

```python
@dataclass
class NotificationConfiguration:
    """Event notification rules for a bucket.

    Attributes:
        event_rules: Notification rules mapping events to destinations.
    """
    event_rules: List[EventRule] = field(default_factory=list)
```

### 5.22 `EventRule`

```python
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
```

### 5.23 `S3EventMessage`

```python
@dataclass
class S3EventMessage:
    """Notification payload published for storage events.

    Attributes:
        event_version: Message format version.
        event_source: Always "fizz:s3".
        event_time: When the event occurred.
        event_name: Event type string.
        bucket_name: Bucket where the event occurred.
        bucket_owner: Bucket owner principal.
        object_key: Object key.
        object_size: Object size in bytes.
        object_etag: Object entity tag.
        object_version_id: Object version ID.
        object_sequencer: Monotonically increasing per-key sequence number.
        request_id: Request identifier.
        principal: Requesting principal.
    """
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
```

### 5.24 `ChunkManifest`

```python
@dataclass
class ChunkManifest:
    """Maps an object to its content-addressed chunks.

    Attributes:
        object_id: Composite identifier (bucket/key/version_id).
        chunks: Ordered list of chunk references.
        total_size: Total object size.
        chunk_count: Number of chunks.
    """
    object_id: str = ""
    chunks: List[ChunkReference] = field(default_factory=list)
    total_size: int = 0
    chunk_count: int = 0
```

### 5.25 `ChunkReference`

```python
@dataclass
class ChunkReference:
    """Reference to a content-addressed chunk within an object.

    Attributes:
        address: SHA-256 content address.
        offset: Byte offset within the original object.
        size: Chunk size in bytes.
        sequence: Chunk sequence number (0-indexed).
    """
    address: str = ""
    offset: int = 0
    size: int = 0
    sequence: int = 0
```

---

## 6. Classes (~20)

### 6.1 `BucketNameValidator`

Validates bucket names against the S3 naming specification.

- **`validate(name: str) -> Tuple[bool, List[str]]`**: Checks length (3-63), lowercase alphanumeric/hyphens/periods, starts/ends with letter or number, no consecutive periods, not an IPv4 address, does not start with `xn--`, does not end with `-s3alias` or `--ol-s3`.  Returns `(is_valid, violations)`.

~40 lines.

### 6.2 `BucketManager`

Manages bucket lifecycle.

- **`create_bucket(name, region, owner, acl, object_lock)`**: Validates name, checks global uniqueness, checks max bucket count, initializes bucket with defaults, stores in metadata index, emits `S3_BUCKET_CREATED` event.  Returns `Bucket`.
- **`delete_bucket(name)`**: Validates bucket is empty (no objects, no multipart uploads), removes from metadata index, emits `S3_BUCKET_DELETED` event.
- **`head_bucket(name, principal)`**: Returns bucket existence and access check.
- **`list_buckets(owner)`**: Returns all buckets for owner, sorted alphabetically.
- **`get_bucket_location(name)`**: Returns region string.
- **`get_bucket_versioning(name)`**: Returns versioning state.
- **`put_bucket_versioning(name, status)`**: Validates state machine (DISABLED->ENABLED, ENABLED->SUSPENDED, SUSPENDED->ENABLED).

~200 lines.

### 6.3 `ObjectStore`

Core object storage operations.

- **`put_object(bucket, key, data, metadata, content_type, storage_class, encryption, checksum_algorithm)`**: Validates bucket exists, key length, data size, metadata size.  Computes ETag.  Assigns version ID if versioning enabled.  Encrypts if configured.  Chunks data, deduplicates, erasure-codes, stores fragments.  Writes metadata record.  Publishes `s3:ObjectCreated:Put` event.  Returns `S3Object`.
- **`get_object(bucket, key, version_id, byte_range, if_match, if_none_match, if_modified_since, if_unmodified_since)`**: Conditional GET with ETag/timestamp comparison.  Delete marker returns 404 with marker header.  Byte-range returns partial content.  Reassembles from content-addressed chunks, decodes erasure-coded fragments, decrypts.  Returns `S3Object`.
- **`head_object(bucket, key, version_id)`**: Returns metadata without data payload.
- **`delete_object(bucket, key, version_id)`**: Unversioned: permanent delete.  Versioned without version_id: insert delete marker.  Versioned with version_id: permanent version delete.  Publishes appropriate event.
- **`delete_objects(bucket, objects)`**: Batch delete up to 1000 objects.  Returns success/error lists.
- **`copy_object(source_bucket, source_key, dest_bucket, dest_key, source_version_id, metadata_directive, storage_class)`**: Copies metadata; for same-region content-addressed storage, copy is metadata-only (no data transfer).
- **`list_objects_v2(bucket, prefix, delimiter, start_after, continuation_token, max_keys)`**: Prefix filtering, delimiter hierarchy simulation, pagination.  Returns `ListObjectsResult`.

~350 lines.

### 6.4 `VersioningEngine`

Manages version chains for objects in versioned buckets.

- **`assign_version_id()`**: Generates UUID-based version ID with timestamp prefix for chronological sorting.
- **`get_version_chain(bucket, key)`**: Returns complete version history, newest first.
- **`get_specific_version(bucket, key, version_id)`**: Retrieves specific version regardless of current version state.
- **`delete_specific_version(bucket, key, version_id)`**: Permanently removes a version.  If current version deleted, previous becomes current.
- **`list_object_versions(bucket, prefix, key_marker, version_id_marker, max_keys)`**: Lists all versions including delete markers with pagination.
- Handles version suspension: null version IDs, overwriting previous null version.

~200 lines.

### 6.5 `MultipartUploadManager`

Orchestrates multipart upload lifecycle.

- **`create_multipart_upload(bucket, key, metadata, content_type, storage_class, encryption)`**: Initiates session, generates upload_id, records metadata.  Returns upload_id.
- **`upload_part(bucket, key, upload_id, part_number, data)`**: Validates part number (1-10000), part size (min 5 MB except last).  Computes ETag.  Stores part.  Returns ETag.
- **`upload_part_copy(bucket, key, upload_id, part_number, source_bucket, source_key, source_version_id, byte_range)`**: Server-side copy of byte range.
- **`complete_multipart_upload(bucket, key, upload_id, parts)`**: Validates parts list matches uploads.  Concatenates parts.  Computes composite ETag.  Creates object.  Cleans up.  Publishes event.
- **`abort_multipart_upload(bucket, key, upload_id)`**: Deletes parts, removes session.
- **`list_multipart_uploads(bucket, prefix, max_uploads)`**: Lists in-progress uploads.
- **`list_parts(bucket, key, upload_id, max_parts)`**: Lists parts for an upload.

~250 lines.

### 6.6 `IncompleteUploadReaper`

Background cleanup of stale multipart uploads.

- **`reap()`**: Scans for uploads older than threshold (default 7 days).  Aborts stale uploads.  Respects per-bucket lifecycle thresholds.
- Configurable interval (default 24 hours).

~50 lines.

### 6.7 `PresignedURLGenerator`

Generates presigned URLs for object operations.

- **`generate_presigned_url(method, bucket, key, version_id, expiration, headers, query_params)`**: Constructs URL with `X-Amz-Algorithm`, `X-Amz-Credential`, `X-Amz-Date`, `X-Amz-Expires`, `X-Amz-SignedHeaders`, `X-Amz-Signature`.
- **`generate_presigned_post(bucket, key, conditions, expiration)`**: Generates POST parameters for browser-based uploads with Base64-encoded policy document.

~80 lines.

### 6.8 `PresignedURLVerifier`

Validates presigned URLs on incoming requests.

- **`verify_presigned_url(url, method, headers)`**: Extracts signing parameters, recomputes signature, validates expiration and method match.  Returns `VerificationResult`.

~60 lines.

### 6.9 `SignatureV4Computer`

Implements AWS Signature Version 4 request signing.

- **`compute_signing_key(secret_key, date, region, service)`**: Derives key via HMAC chain: `HMAC(HMAC(HMAC(HMAC("AWS4" + secret, date), region), service), "aws4_request")`.
- **`compute_canonical_request(method, path, query_params, headers, signed_headers, payload_hash)`**: Normalizes and constructs canonical request string.
- **`compute_string_to_sign(algorithm, datetime_str, scope, canonical_request_hash)`**: Combines algorithm, timestamp, scope, hash.
- **`compute_signature(signing_key, string_to_sign)`**: Final HMAC-SHA256 signature.

~100 lines.

### 6.10 `StorageClassManager`

Manages storage class transitions and archive restore operations.

- **`transition_object(bucket, key, version_id, target_class)`**: Validates waterfall (STANDARD -> STANDARD_IA -> ARCHIVE -> DEEP_ARCHIVE).  Re-encodes erasure-coded fragments with target parameters.  Publishes transition event.
- **`restore_object(bucket, key, version_id, days, tier)`**: Initiates async restore of archived object.  Creates temporary STANDARD copy.
- **`get_storage_class_stats(bucket)`**: Returns per-class object count and size.

~150 lines.

### 6.11 `RestoreProcessor`

Processes restore requests asynchronously.

- Priority queue ordered by tier (Expedited > Standard > Bulk) and submission time.
- Reads archived fragments, decodes, re-encodes with STANDARD parameters, writes STANDARD fragments.
- Monitors restore expiration and cleans up expired restored copies.

~80 lines.

### 6.12 `LifecycleEvaluator`

Evaluates lifecycle rules against objects.

- **`evaluate(bucket)`**: Scans all objects, evaluates against enabled rules, returns deduplicated `LifecycleAction` list.  Expiration > transition priority.
- **`apply_actions(actions)`**: Executes transitions via `StorageClassManager`, expirations via `ObjectStore`, multipart abortions via `MultipartUploadManager`.

~120 lines.

### 6.13 `LifecycleDaemon`

Background lifecycle evaluation on configurable schedule.

- Default interval: 24 hours.
- Evaluates all buckets with lifecycle configurations.
- Reports metrics: objects transitioned, expired, multipart uploads aborted.

~50 lines.

### 6.14 `ReplicationEngine`

Processes cross-region replication asynchronously.

- **`replicate_object(source_bucket, source_key, source_version_id, rule)`**: Reads source, applies destination overrides, writes to destination.  Records status (COMPLETED, FAILED, REPLICA).
- **`replicate_delete_marker(source_bucket, source_key, source_version_id, rule)`**: Copies delete marker if enabled.
- **`get_replication_status(bucket, key, version_id)`**: Returns PENDING, COMPLETED, FAILED, or REPLICA.

~100 lines.

### 6.15 `ReplicationConflictResolver`

Handles bidirectional replication conflicts.

- **Last-writer-wins**: Compares `last_modified` timestamps; ties broken by lexicographic version ID comparison.
- **Loop detection**: Checks `x-fizz-replication-source` metadata to prevent infinite replication loops.

~60 lines.

### 6.16 `EncryptionEngine`

Handles object encryption and decryption.

- **SSE-S3**: Generates per-object DEK, encrypts with AES-256-GCM, wraps DEK with master key (envelope encryption).
- **SSE-KMS**: Requests data key from FizzVault, stores ciphertext DEK in metadata.
- **SSE-C**: Uses client-provided key, stores MD5 for verification, discards key.
- **`encrypt(data, encryption_config)`**: Encrypts data using configured mode.  Returns encrypted bytes and encryption metadata.
- **`decrypt(encrypted_data, encryption_metadata, client_key)`**: Decrypts data.  Returns plaintext bytes.

~150 lines.

### 6.17 `KeyRotationManager`

Manages encryption key lifecycle.

- **`rotate_master_key()`**: Generates new SSE-S3 master key.
- **`re_encrypt_objects(bucket, prefix)`**: Proactively re-wraps DEKs with current master key.
- Configurable rotation schedule (default 90 days).

~60 lines.

### 6.18 `AccessControlEvaluator`

Evaluates authorization for incoming S3 requests.

- **`evaluate(principal, action, resource, context)`**: Implements S3 authorization algorithm:
  1. Check block public access settings.
  2. Evaluate bucket policy statements (collect DENY/ALLOW).
  3. Evaluate ACL grants.
  4. Apply logic: explicit DENY -> deny.  No ALLOW -> deny.  ALLOW with no DENY -> allow.
  Returns `AuthorizationResult` with `allowed`, `reason`, `evaluated_policies`.

~150 lines.

### 6.19 `ContentAddressableStore`

Core deduplication engine.

- **`chunk_object(data, chunk_size)`**: Splits data into fixed-size chunks.  Returns list of `(chunk_data, offset)`.
- **`address_chunk(chunk_data)`**: Computes SHA-256 content address.
- **`store_chunk(address, data)`**: Stores at content address.  If exists, increments reference count (no-op for data).  Returns CREATED or DEDUPLICATED.
- **`retrieve_chunk(address)`**: Reads chunk, decodes erasure-coded fragments.
- **`delete_chunk_reference(address, object_id)`**: Decrements reference count.  Zero-count chunks become GC candidates.
- **`get_deduplication_stats(bucket)`**: Returns logical_size, physical_size, dedup_ratio, shared_chunks, unique_chunks.

~150 lines.

### 6.20 `ReferenceCounter`

Tracks object references to content addresses.

- **`increment(address, object_id)`**: Adds reference, initializes or increments counter.
- **`decrement(address, object_id)`**: Removes reference, decrements counter.  Returns new count.
- **`get_count(address)`**: Returns current reference count.
- WAL-protected operations.

~50 lines.

### 6.21 `GarbageCollector`

Reclaims storage from unreferenced chunks.

- **`collect()`**: Scans zero-reference candidates, verifies count still zero, deletes fragments, removes metadata.
- Safety delay (default 24 hours) prevents collection of in-flight PUT targets.
- Configurable interval (default 6 hours).

~60 lines.

### 6.22 `ErasureCodingEngine`

Implements Reed-Solomon erasure coding over GF(2^8).

- **`encode(data, data_fragments, parity_fragments)`**: Systematic Reed-Solomon encoding via Vandermonde matrix multiplication over GF(2^8).  Returns `data_fragments + parity_fragments` fragments.
- **`decode(fragments, data_fragments, parity_fragments)`**: Reconstructs original data from any `data_fragments` fragments.  Sub-matrix inversion via Gaussian elimination over GF(2^8).
- **`verify_fragments(fragments, data_fragments, parity_fragments)`**: Checks consistency by re-encoding and comparing parity.

~150 lines.

### 6.23 `GaloisField`

Arithmetic operations over GF(2^8) for Reed-Solomon coding.

- **`add(a, b)`**: XOR.
- **`multiply(a, b)`**: Via log/antilog tables, irreducible polynomial 0x11D.
- **`divide(a, b)`**: Multiplication by multiplicative inverse.
- **`inverse(a)`**: Via log/antilog tables.
- `exp_table` and `log_table`: 256-entry precomputed lookup tables generated at module load time.

~80 lines.

### 6.24 `VandermondeMatrix`

Constructs and operates on Vandermonde matrices for Reed-Solomon encoding.

- **`build(rows, cols)`**: Constructs matrix where element (i,j) = i^j in GF(2^8).  First `cols` rows form identity (systematic encoding).
- **`invert_submatrix(indices)`**: Extracts submatrix, computes inverse via Gaussian elimination.
- **`multiply_vector(matrix, vector)`**: Matrix-vector multiplication over GF(2^8).

~80 lines.

### 6.25 `FragmentDistributor`

Distributes erasure-coded fragments across failure domains.

- **`distribute(fragments, locations)`**: Assigns fragments to independent storage locations.
- **`collect(chunk_address, required_count)`**: Collects fragments from available locations.  Raises `InsufficientFragmentsError` if too few available.

~50 lines.

### 6.26 `FragmentIntegrityChecker`

Monitors and repairs fragment health.

- **`check_chunk(chunk_address)`**: Retrieves all fragments, verifies consistency.
- **`repair_chunk(chunk_address, corrupt_indices)`**: Decodes from healthy fragments, re-encodes replacements.
- **`scrub(bucket)`**: Full integrity scan, identifies and repairs corruptions.

~80 lines.

### 6.27 `MetadataIndex`

Metadata storage engine with B-tree and hash indices.

- **`BTreeNode`**: Internal B-tree node for range queries (prefix listing, version enumeration).
- **`put(key, value, index_type)`**: WAL-protected insert/update.
- **`get(key, index_type)`**: Point lookup via hash index.
- **`delete(key, index_type)`**: WAL-protected removal.
- **`range_query(start_key, end_key, limit)`**: Ordered key traversal on B-tree.
- **`prefix_query(prefix, limit, continuation_token)`**: Range from `prefix` to `prefix + \xff`.

~100 lines.

### 6.28 `SegmentLog`

Append-only data tier storage.

- **`append(fragment_address, fragment_data)`**: Appends to active segment.  Seals when max size reached.
- **`read(location)`**: Reads fragment by segment ID + offset + length.
- **`seal_segment(segment)`**: Marks immutable, finalizes index.
- **`compact(segment_ids)`**: Copies live fragments, discards dead, updates references.

~80 lines.

### 6.29 `CompactionPolicy`

Determines compaction eligibility.

- **`select_segments()`**: Returns segments with fragmentation ratio above threshold (default 0.5), ordered by fragmentation.
- Configurable min segment age (default 1 hour), max concurrency (default 2).

~30 lines.

### 6.30 `NotificationDispatcher`

Processes and dispatches event notifications.

- Evaluates object operations against bucket notification configuration.
- Matches event type and key prefix/suffix filters.
- Asynchronous, non-blocking dispatch -- notification failures do not affect storage operations.
- Exponential backoff retry (3 attempts, 1s initial, 30s max).
- Dead-letter queue for permanently failed notifications.

~100 lines.

### 6.31 `S3RequestRouter`

Routes S3-compatible requests to handlers.

- **`route(method, path, query_params)`**: Pattern-matches 36 API operations based on method, path segments, and query parameter presence.  Returns operation enum and parsed parameters.

~60 lines.

### 6.32 `S3ResponseFormatter`

Formats responses to S3-compatible XML.

- **`format_xml_response(operation, result)`**: Serializes results to XML matching S3 schema (`<ListBucketResult>`, `<InitiateMultipartUploadResult>`, etc.).
- **`format_error_response(error_code, message, resource, request_id)`**: Serializes to `<Error>` XML format with standard S3 error codes.

~60 lines.

### 6.33 `S3Metrics`

Storage-tier metrics collector.

- Request metrics: count, latency (p50/p95/p99), errors, bytes uploaded/downloaded.
- Storage metrics: object count, logical/physical size per class, version count, multipart stats.
- Deduplication metrics: ratio, chunks total/shared, bytes saved.
- Erasure coding metrics: fragments total/healthy/degraded/repaired, scrub duration.
- Replication/lifecycle metrics.

~60 lines.

### 6.34 `FizzS3Dashboard`

ASCII dashboard rendering for storage metrics.

- **`render_bucket_summary(bucket)`**: Bucket-level metrics overview.
- **`render_storage_classes(bucket)`**: Per-class storage distribution.
- **`render_deduplication(bucket)`**: Dedup ratio, savings, shared chunks.
- **`render_erasure_health(bucket)`**: Fragment health, degraded/repaired counts.
- **`render_replication(bucket)`**: Replication lag, pending, failed operations.
- **`render_overview()`**: Platform-wide storage summary across all buckets.

~150 lines.

### 6.35 `FizzS3Middleware`

Integrates FizzS3 with the FizzBuzz evaluation middleware pipeline.

```python
class FizzS3Middleware(IMiddleware):
    """Records FizzBuzz evaluation results as S3 objects.

    Each evaluation is stored in the fizzbuzz-evaluations bucket with
    key format evaluations/{year}/{month}/{day}/{request_id}.json,
    enabling query-by-prefix listing of historical evaluations by
    date range.  Objects are stored in STANDARD class with lifecycle
    policy transitioning to ARCHIVE after 30 days.
    """

    @property
    def name(self) -> str:
        return "fizzs3"

    @property
    def priority(self) -> int:
        return MIDDLEWARE_PRIORITY

    def process(self, context: ProcessingContext, result: FizzBuzzResult) -> FizzBuzzResult:
        ...
```

- Records evaluation input, output, timestamp as JSON object.
- Renders dashboard sections based on CLI flags.

~120 lines.

---

## 7. Exceptions (~62)

File: `enterprise_fizzbuzz/domain/exceptions/fizzs3.py`

Base exception: `FizzS3Error(FizzBuzzError)` with `error_code="EFP-S300"`.

All exceptions follow the established pattern:
```python
class ExceptionName(ParentError):
    """Docstring explaining the failure mode."""
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-S3xx"
        self.context = {"reason": reason}
```

| # | Class | Parent | Code | Trigger |
|---|-------|--------|------|---------|
| 00 | `FizzS3Error` | `FizzBuzzError` | EFP-S300 | Base for all FizzS3 errors |
| 01 | `BucketError` | `FizzS3Error` | EFP-S301 | Base for bucket-related errors |
| 02 | `BucketAlreadyExistsError` | `BucketError` | EFP-S302 | Bucket name already in use globally |
| 03 | `BucketAlreadyOwnedByYouError` | `BucketError` | EFP-S303 | Caller already owns this bucket |
| 04 | `BucketNotEmptyError` | `BucketError` | EFP-S304 | Delete attempt on non-empty bucket |
| 05 | `BucketNotFoundError` | `BucketError` | EFP-S305 | Specified bucket does not exist |
| 06 | `InvalidBucketNameError` | `BucketError` | EFP-S306 | Bucket name violates naming rules |
| 07 | `TooManyBucketsError` | `BucketError` | EFP-S307 | Maximum bucket count exceeded |
| 08 | `ObjectError` | `FizzS3Error` | EFP-S308 | Base for object-related errors |
| 09 | `ObjectNotFoundError` | `ObjectError` | EFP-S309 | Key does not exist or has delete marker |
| 10 | `ObjectTooLargeError` | `ObjectError` | EFP-S310 | Object exceeds single-part upload limit |
| 11 | `InvalidObjectKeyError` | `ObjectError` | EFP-S311 | Key exceeds max length or invalid chars |
| 12 | `PreconditionFailedError` | `ObjectError` | EFP-S312 | If-Match/If-Unmodified-Since not met |
| 13 | `NotModifiedError` | `ObjectError` | EFP-S313 | If-None-Match/If-Modified-Since not met |
| 14 | `InvalidRangeError` | `ObjectError` | EFP-S314 | Byte range outside object size |
| 15 | `VersionError` | `FizzS3Error` | EFP-S315 | Base for versioning errors |
| 16 | `NoSuchVersionError` | `VersionError` | EFP-S316 | Version ID does not exist |
| 17 | `VersioningNotEnabledError` | `VersionError` | EFP-S317 | Version operation on unversioned bucket |
| 18 | `InvalidVersionIdError` | `VersionError` | EFP-S318 | Malformed version ID |
| 19 | `MultipartUploadError` | `FizzS3Error` | EFP-S319 | Base for multipart upload errors |
| 20 | `NoSuchUploadError` | `MultipartUploadError` | EFP-S320 | Upload ID not found or completed/aborted |
| 21 | `InvalidPartError` | `MultipartUploadError` | EFP-S321 | Part does not exist or ETag mismatch |
| 22 | `InvalidPartOrderError` | `MultipartUploadError` | EFP-S322 | Parts not in ascending order |
| 23 | `EntityTooSmallError` | `MultipartUploadError` | EFP-S323 | Non-final part below 5 MB minimum |
| 24 | `EntityTooLargeError` | `MultipartUploadError` | EFP-S324 | Part exceeds 5 GiB maximum |
| 25 | `TooManyPartsError` | `MultipartUploadError` | EFP-S325 | Part number exceeds 10,000 |
| 26 | `AccessControlError` | `FizzS3Error` | EFP-S326 | Base for authorization errors |
| 27 | `S3AccessDeniedError` | `AccessControlError` | EFP-S327 | Caller lacks permission |
| 28 | `InvalidPolicyError` | `AccessControlError` | EFP-S328 | Malformed bucket policy |
| 29 | `MalformedACLError` | `AccessControlError` | EFP-S329 | Malformed ACL document |
| 30 | `PublicAccessBlockedError` | `AccessControlError` | EFP-S330 | Public access blocked by settings |
| 31 | `EncryptionError` | `FizzS3Error` | EFP-S331 | Base for encryption errors |
| 32 | `InvalidEncryptionKeyError` | `EncryptionError` | EFP-S332 | SSE-C key invalid or mismatch |
| 33 | `KMSKeyNotFoundError` | `EncryptionError` | EFP-S333 | FizzVault key ID not found |
| 34 | `KMSAccessDeniedError` | `EncryptionError` | EFP-S334 | No permission for KMS key |
| 35 | `KeyRotationInProgressError` | `EncryptionError` | EFP-S335 | Key rotation blocking operation |
| 36 | `ReplicationError` | `FizzS3Error` | EFP-S336 | Base for replication errors |
| 37 | `ReplicationConfigurationError` | `ReplicationError` | EFP-S337 | Invalid replication configuration |
| 38 | `ReplicationFailedError` | `ReplicationError` | EFP-S338 | Object replication failed |
| 39 | `ReplicationLoopDetectedError` | `ReplicationError` | EFP-S339 | Bidirectional replication loop |
| 40 | `StorageClassError` | `FizzS3Error` | EFP-S340 | Base for storage class errors |
| 41 | `InvalidStorageClassTransitionError` | `StorageClassError` | EFP-S341 | Transition violates waterfall |
| 42 | `RestoreInProgressError` | `StorageClassError` | EFP-S342 | Restore already in progress |
| 43 | `ObjectNotArchivedError` | `StorageClassError` | EFP-S343 | Restore on non-archived object |
| 44 | `RestoreExpiredError` | `StorageClassError` | EFP-S344 | Restored copy has expired |
| 45 | `ErasureCodingError` | `FizzS3Error` | EFP-S345 | Base for erasure coding errors |
| 46 | `InsufficientFragmentsError` | `ErasureCodingError` | EFP-S346 | Not enough fragments for reconstruction |
| 47 | `FragmentCorruptionError` | `ErasureCodingError` | EFP-S347 | Fragment data mismatch |
| 48 | `FragmentLocationUnavailableError` | `ErasureCodingError` | EFP-S348 | Storage location unreachable |
| 49 | `ContentAddressError` | `FizzS3Error` | EFP-S349 | Base for deduplication errors |
| 50 | `ChunkNotFoundError` | `ContentAddressError` | EFP-S350 | Chunk not at expected address |
| 51 | `ReferenceIntegrityError` | `ContentAddressError` | EFP-S351 | Reference count inconsistent |
| 52 | `DeduplicationHashCollisionError` | `ContentAddressError` | EFP-S352 | SHA-256 collision (theoretical) |
| 53 | `LifecycleError` | `FizzS3Error` | EFP-S353 | Base for lifecycle errors |
| 54 | `InvalidLifecycleConfigurationError` | `LifecycleError` | EFP-S354 | Malformed lifecycle config |
| 55 | `TooManyLifecycleRulesError` | `LifecycleError` | EFP-S355 | Exceeds 1000 rules |
| 56 | `PresignedURLError` | `FizzS3Error` | EFP-S356 | Base for presigned URL errors |
| 57 | `ExpiredPresignedURLError` | `PresignedURLError` | EFP-S357 | Presigned URL expired |
| 58 | `InvalidSignatureError` | `PresignedURLError` | EFP-S358 | Signature mismatch |
| 59 | `SignatureMethodMismatchError` | `PresignedURLError` | EFP-S359 | HTTP method mismatch |
| 60 | `MetadataError` | `FizzS3Error` | EFP-S360 | Base for metadata tier errors |
| 61 | `MetadataCorruptionError` | `MetadataError` | EFP-S361 | Metadata index inconsistent |
| 62 | `MetadataCapacityExceededError` | `MetadataError` | EFP-S362 | User metadata exceeds 2 KB |
| 63 | `NotificationError` | `FizzS3Error` | EFP-S363 | Base for notification errors |
| 64 | `InvalidNotificationConfigurationError` | `NotificationError` | EFP-S364 | Malformed notification config |
| 65 | `NotificationDeliveryFailedError` | `NotificationError` | EFP-S365 | Delivery failed after retries |
| 66 | `FizzS3MiddlewareError` | `FizzS3Error` | EFP-S366 | Middleware processing failure |
| 67 | `FizzS3DashboardError` | `FizzS3Error` | EFP-S367 | Dashboard rendering failure |

### Exception Docstring Style

Each exception gets a deadpan, technically earnest docstring.  Example:

```python
class InsufficientFragmentsError(ErasureCodingError):
    """Raised when too few erasure-coded fragments are available for reconstruction.

    Reed-Solomon decoding requires a minimum of K data-equivalent fragments
    to reconstruct the original data chunk, where K is the data fragment
    count for the object's storage class.  If fewer than K fragments are
    available across all storage locations, the chunk's data has been
    irreversibly lost.  This indicates a durability failure that has
    exceeded the erasure coding's designed fault tolerance -- for STANDARD
    class with a 10:4 configuration, five simultaneous storage location
    failures would be required.

    Recovery options: restore from cross-region replica if replication was
    configured, or escalate to the platform's disaster recovery subsystem.
    """

    def __init__(self, chunk_address: str, available: int, required: int) -> None:
        super().__init__(
            f"Insufficient fragments for chunk {chunk_address[:16]}...: "
            f"{available} available, {required} required"
        )
        self.error_code = "EFP-S346"
        self.context = {
            "chunk_address": chunk_address,
            "available_fragments": available,
            "required_fragments": required,
        }
```

---

## 8. EventType Entries (~22)

Register in `enterprise_fizzbuzz/domain/events/_fizzs3.py`:

```python
"""FizzS3 object storage events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

# Bucket lifecycle
EventType.register("S3_BUCKET_CREATED")
EventType.register("S3_BUCKET_DELETED")
EventType.register("S3_BUCKET_VERSIONING_CHANGED")

# Object lifecycle
EventType.register("S3_OBJECT_CREATED_PUT")
EventType.register("S3_OBJECT_CREATED_COPY")
EventType.register("S3_OBJECT_CREATED_MPU")
EventType.register("S3_OBJECT_DELETED")
EventType.register("S3_OBJECT_DELETE_MARKER_CREATED")

# Storage class transitions
EventType.register("S3_OBJECT_TRANSITIONED")
EventType.register("S3_OBJECT_RESTORE_INITIATED")
EventType.register("S3_OBJECT_RESTORE_COMPLETED")
EventType.register("S3_OBJECT_RESTORE_EXPIRED")

# Replication
EventType.register("S3_REPLICATION_COMPLETED")
EventType.register("S3_REPLICATION_FAILED")

# Lifecycle
EventType.register("S3_LIFECYCLE_EXPIRATION")
EventType.register("S3_LIFECYCLE_TRANSITION")

# Maintenance
EventType.register("S3_GC_COMPLETED")
EventType.register("S3_SCRUB_COMPLETED")
EventType.register("S3_COMPACTION_COMPLETED")
EventType.register("S3_KEY_ROTATION_COMPLETED")

# Middleware
EventType.register("S3_EVALUATION_STORED")
EventType.register("S3_DASHBOARD_RENDERED")
```

---

## 9. Config Mixin Properties (~14)

File: `enterprise_fizzbuzz/infrastructure/config/mixins/fizzs3.py`

```python
"""FizzS3 configuration properties."""

from __future__ import annotations

from typing import Any


class FizzS3ConfigMixin:
    """Configuration properties for the FizzS3 object storage subsystem."""

    @property
    def fizzs3_enabled(self) -> bool:
        """Whether the FizzS3 object storage subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzs3", {}).get("enabled", False)

    @property
    def fizzs3_default_region(self) -> str:
        """Default region for new buckets."""
        self._ensure_loaded()
        return self._raw_config.get("fizzs3", {}).get("default_region", "fizz-east-1")

    @property
    def fizzs3_max_buckets(self) -> int:
        """Maximum buckets per owner."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzs3", {}).get("max_buckets", 100))

    @property
    def fizzs3_default_encryption(self) -> str:
        """Default server-side encryption mode."""
        self._ensure_loaded()
        return self._raw_config.get("fizzs3", {}).get("default_encryption", "sse-s3")

    @property
    def fizzs3_chunk_size(self) -> int:
        """Content-addressable chunk size in bytes."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzs3", {}).get("chunk_size", 4 * 1024 * 1024))

    @property
    def fizzs3_gc_interval(self) -> float:
        """Garbage collection interval in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzs3", {}).get("gc_interval", 21600.0))

    @property
    def fizzs3_gc_safety_delay(self) -> float:
        """GC safety delay in seconds before collecting unreferenced chunks."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzs3", {}).get("gc_safety_delay", 86400.0))

    @property
    def fizzs3_lifecycle_interval(self) -> float:
        """Lifecycle evaluation interval in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzs3", {}).get("lifecycle_interval", 86400.0))

    @property
    def fizzs3_compaction_threshold(self) -> float:
        """Segment fragmentation ratio that triggers compaction."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzs3", {}).get("compaction_threshold", 0.5))

    @property
    def fizzs3_segment_max_size(self) -> int:
        """Maximum segment size in bytes."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzs3", {}).get("segment_max_size", 256 * 1024 * 1024))

    @property
    def fizzs3_replication_retry_max(self) -> int:
        """Maximum replication retry attempts."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzs3", {}).get("replication_retry_max", 24))

    @property
    def fizzs3_presign_default_expiry(self) -> int:
        """Default presigned URL expiry in seconds."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzs3", {}).get("presign_default_expiry", 3600))

    @property
    def fizzs3_key_rotation_days(self) -> int:
        """SSE-S3 master key rotation interval in days."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzs3", {}).get("key_rotation_days", 90))

    @property
    def fizzs3_dashboard_width(self) -> int:
        """Width of the FizzS3 ASCII dashboard."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzs3", {}).get("dashboard", {}).get("width", 72))
```

---

## 10. YAML Config Section

File: `config.d/fizzs3.yaml`

```yaml
fizzs3:
  enabled: false                              # Master switch — opt-in via --fizzs3
  default_region: fizz-east-1                 # Default region for new buckets
  max_buckets: 100                            # Maximum buckets per owner
  default_encryption: sse-s3                  # Default encryption mode (sse-s3, sse-kms, sse-c)
  chunk_size: 4194304                         # Content-addressable chunk size (4 MB)
  gc_interval: 21600.0                        # Garbage collection interval (6 hours)
  gc_safety_delay: 86400.0                    # GC safety delay before collecting (24 hours)
  lifecycle_interval: 86400.0                 # Lifecycle evaluation interval (24 hours)
  compaction_threshold: 0.5                   # Segment fragmentation compaction trigger
  segment_max_size: 268435456                 # Maximum segment size (256 MB)
  replication_retry_max: 24                   # Maximum replication retry attempts
  presign_default_expiry: 3600               # Default presigned URL expiry (1 hour)
  key_rotation_days: 90                       # SSE-S3 master key rotation interval
  erasure_coding:
    standard:
      data_fragments: 10                      # STANDARD class data fragments
      parity_fragments: 4                     # STANDARD class parity fragments
    standard_ia:
      data_fragments: 6                       # STANDARD_IA data fragments
      parity_fragments: 4                     # STANDARD_IA parity fragments
    archive:
      data_fragments: 4                       # ARCHIVE data fragments
      parity_fragments: 4                     # ARCHIVE parity fragments
    deep_archive:
      data_fragments: 2                       # DEEP_ARCHIVE data fragments
      parity_fragments: 4                     # DEEP_ARCHIVE parity fragments
  dashboard:
    width: 72                                 # ASCII dashboard width
```

---

## 11. Feature Descriptor

File: `enterprise_fizzbuzz/infrastructure/features/fizzs3_feature.py`

```python
"""Feature descriptor for the FizzS3 object storage subsystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzS3Feature(FeatureDescriptor):
    name = "fizzs3"
    description = "S3-compatible object storage with erasure coding, deduplication, versioning, and lifecycle management"
    middleware_priority = 118
    cli_flags = [
        ("--fizzs3", {"action": "store_true",
                      "help": "Enable FizzS3: S3-compatible object storage with erasure coding and deduplication"}),
        ("--fizzs3-list-buckets", {"action": "store_true",
                                    "help": "List all FizzS3 buckets"}),
        ("--fizzs3-create-bucket", {"type": str, "default": None, "metavar": "NAME",
                                     "help": "Create a new bucket"}),
        ("--fizzs3-delete-bucket", {"type": str, "default": None, "metavar": "NAME",
                                     "help": "Delete an empty bucket"}),
        ("--fizzs3-put", {"nargs": 3, "default": None, "metavar": ("BUCKET", "KEY", "FILE"),
                           "help": "Upload a file as an object"}),
        ("--fizzs3-get", {"nargs": 2, "default": None, "metavar": ("BUCKET", "KEY"),
                           "help": "Retrieve an object"}),
        ("--fizzs3-head", {"nargs": 2, "default": None, "metavar": ("BUCKET", "KEY"),
                            "help": "Retrieve object metadata"}),
        ("--fizzs3-delete", {"nargs": 2, "default": None, "metavar": ("BUCKET", "KEY"),
                              "help": "Delete an object"}),
        ("--fizzs3-list", {"type": str, "default": None, "metavar": "BUCKET",
                            "help": "List objects in a bucket"}),
        ("--fizzs3-list-versions", {"nargs": 2, "default": None, "metavar": ("BUCKET", "KEY"),
                                     "help": "List all versions of an object"}),
        ("--fizzs3-presign", {"nargs": 2, "default": None, "metavar": ("BUCKET", "KEY"),
                               "help": "Generate a presigned URL"}),
        ("--fizzs3-presign-expires", {"type": int, "default": 3600, "metavar": "SECONDS",
                                       "help": "Presigned URL validity duration (default: 3600)"}),
        ("--fizzs3-multipart-create", {"nargs": 2, "default": None, "metavar": ("BUCKET", "KEY"),
                                        "help": "Initiate a multipart upload"}),
        ("--fizzs3-multipart-complete", {"nargs": 3, "default": None, "metavar": ("BUCKET", "KEY", "UPLOAD_ID"),
                                          "help": "Complete a multipart upload"}),
        ("--fizzs3-multipart-abort", {"nargs": 3, "default": None, "metavar": ("BUCKET", "KEY", "UPLOAD_ID"),
                                       "help": "Abort a multipart upload"}),
        ("--fizzs3-multipart-list", {"type": str, "default": None, "metavar": "BUCKET",
                                      "help": "List in-progress multipart uploads"}),
        ("--fizzs3-storage-class", {"type": str, "default": "STANDARD",
                                     "choices": ["STANDARD", "STANDARD_IA", "ARCHIVE", "DEEP_ARCHIVE"],
                                     "help": "Storage class for PUT operations"}),
        ("--fizzs3-versioning", {"nargs": 2, "default": None, "metavar": ("BUCKET", "ACTION"),
                                  "help": "Enable or suspend versioning (enable|suspend)"}),
        ("--fizzs3-encryption", {"nargs": 2, "default": None, "metavar": ("BUCKET", "MODE"),
                                  "help": "Set default encryption (sse-s3, sse-kms, sse-c)"}),
        ("--fizzs3-dedup-stats", {"type": str, "default": None, "metavar": "BUCKET",
                                   "help": "Show deduplication statistics"}),
        ("--fizzs3-scrub", {"type": str, "default": None, "metavar": "BUCKET",
                             "help": "Run erasure coding integrity scrub"}),
        ("--fizzs3-metrics", {"action": "store_true",
                               "help": "Show storage metrics summary"}),
        ("--fizzs3-prefix", {"type": str, "default": None, "metavar": "PREFIX",
                              "help": "Prefix filter for list operations"}),
        ("--fizzs3-delimiter", {"type": str, "default": None, "metavar": "DELIMITER",
                                 "help": "Delimiter for hierarchy simulation (default: /)"}),
        ("--fizzs3-region", {"type": str, "default": None, "metavar": "REGION",
                              "help": "Region for bucket operations (default: fizz-east-1)"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzs3", False),
            getattr(args, "fizzs3_list_buckets", False),
            getattr(args, "fizzs3_create_bucket", None) is not None,
            getattr(args, "fizzs3_delete_bucket", None) is not None,
            getattr(args, "fizzs3_put", None) is not None,
            getattr(args, "fizzs3_get", None) is not None,
            getattr(args, "fizzs3_head", None) is not None,
            getattr(args, "fizzs3_delete", None) is not None,
            getattr(args, "fizzs3_list", None) is not None,
            getattr(args, "fizzs3_list_versions", None) is not None,
            getattr(args, "fizzs3_presign", None) is not None,
            getattr(args, "fizzs3_dedup_stats", None) is not None,
            getattr(args, "fizzs3_scrub", None) is not None,
            getattr(args, "fizzs3_metrics", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzs3 import (
            FizzS3Middleware,
            create_fizzs3_subsystem,
        )

        service, middleware = create_fizzs3_subsystem(
            default_region=config.fizzs3_default_region,
            max_buckets=config.fizzs3_max_buckets,
            default_encryption=config.fizzs3_default_encryption,
            chunk_size=config.fizzs3_chunk_size,
            gc_interval=config.fizzs3_gc_interval,
            gc_safety_delay=config.fizzs3_gc_safety_delay,
            lifecycle_interval=config.fizzs3_lifecycle_interval,
            compaction_threshold=config.fizzs3_compaction_threshold,
            segment_max_size=config.fizzs3_segment_max_size,
            presign_default_expiry=config.fizzs3_presign_default_expiry,
            dashboard_width=config.fizzs3_dashboard_width,
            event_bus=event_bus,
        )

        return service, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        parts = []
        if getattr(args, "fizzs3_list_buckets", False):
            parts.append(middleware.render_buckets())
        if getattr(args, "fizzs3_dedup_stats", None):
            parts.append(middleware.render_dedup(args.fizzs3_dedup_stats))
        if getattr(args, "fizzs3_metrics", False):
            parts.append(middleware.render_metrics())
        if getattr(args, "fizzs3_scrub", None):
            parts.append(middleware.render_scrub(args.fizzs3_scrub))
        if getattr(args, "fizzs3", False) and not parts:
            parts.append(middleware.render_overview())
        return "\n".join(parts) if parts else None
```

---

## 12. Factory Function

```python
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
        Tuple of (FizzS3Service, FizzS3Middleware).
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
    )

    logger.info("FizzS3 subsystem created and wired")
    return object_store, middleware
```

---

## 13. Re-export Stub

File: `fizzs3.py` at repository root:

```python
"""Backward-compatible re-export stub for fizzs3."""
from enterprise_fizzbuzz.infrastructure.fizzs3 import *  # noqa: F401,F403
```

---

## 14. Test Plan

### Test file: `tests/test_fizzs3.py` (~500 tests)

### Test Classes and Counts

| Test Class | Count | Scope |
|------------|-------|-------|
| `TestBucketNameValidator` | 20 | Valid names, length bounds, IP address format, xn-- prefix, -s3alias suffix, consecutive periods, special characters |
| `TestBucket` | 8 | Bucket dataclass construction, defaults, tag limits |
| `TestBucketManager` | 25 | Create/delete/head/list/location/versioning, global uniqueness, max bucket limit, empty check |
| `TestS3Object` | 10 | Object dataclass construction, defaults, metadata |
| `TestObjectStore` | 40 | Put/get/head/delete/copy/list, conditional GET (If-Match, If-None-Match, If-Modified-Since, If-Unmodified-Since), byte-range, delete marker handling, metadata validation |
| `TestListObjectsV2` | 15 | Prefix filtering, delimiter hierarchy, pagination, continuation tokens, max_keys, common prefixes |
| `TestVersioningEngine` | 25 | Version ID generation, version chain ordering, specific version get/delete, delete markers, version suspension (null IDs), re-enable after suspend |
| `TestDeleteMarker` | 8 | Delete marker creation, version chain with markers, undelete via marker removal |
| `TestMultipartUploadManager` | 30 | Create/upload/complete/abort/list uploads/list parts, part number validation, min part size, ETag computation, part replacement, upload_part_copy |
| `TestIncompleteUploadReaper` | 6 | Stale upload detection, threshold configuration, lifecycle rule respect |
| `TestPresignedURLGenerator` | 12 | GET/PUT/HEAD/DELETE presigned URLs, expiry validation, POST parameters |
| `TestPresignedURLVerifier` | 10 | Valid signature, expired URL, method mismatch, tampered URL, clock skew |
| `TestSignatureV4Computer` | 12 | Signing key derivation, canonical request, string to sign, signature computation |
| `TestStorageClass` | 4 | Enum values and erasure coding parameters |
| `TestStorageClassManager` | 15 | Valid transitions (waterfall), invalid reverse transitions, restore lifecycle (expedited/standard/bulk), restore expiration |
| `TestRestoreProcessor` | 8 | Priority ordering, fragment re-encoding, expiration monitoring |
| `TestLifecycleRule` | 10 | Rule construction, prefix/tag/size filters, transition/expiration/multipart abort rules |
| `TestLifecycleEvaluator` | 18 | Rule evaluation, action deduplication, priority (expire > transition), noncurrent version rules, disabled rule skip |
| `TestLifecycleDaemon` | 6 | Schedule, multi-bucket evaluation, metric reporting |
| `TestReplicationConfiguration` | 8 | Rule construction, priority ordering, prefix filtering |
| `TestReplicationEngine` | 15 | Object replication, delete marker replication, status tracking, retry with backoff |
| `TestReplicationConflictResolver` | 8 | Last-writer-wins, tie breaking, loop detection via source metadata |
| `TestEncryptionEngine` | 18 | SSE-S3 (DEK generation, envelope encryption, master key wrap), SSE-KMS (data key from vault), SSE-C (client key, MD5 verification, key discard) |
| `TestKeyRotationManager` | 6 | Master key rotation, proactive re-encryption, rotation schedule |
| `TestBucketPolicy` | 10 | Policy statement construction, ALLOW/DENY, principal matching, resource ARN matching, condition operators |
| `TestAccessControlList` | 10 | Canned ACLs (all 6 types), grant construction, grantee types |
| `TestBlockPublicAccess` | 8 | Four independent flags, public ACL blocking, public policy blocking |
| `TestAccessControlEvaluator` | 15 | Multi-layer evaluation (policy + ACL + block public access), explicit DENY override, no ALLOW default deny |
| `TestNotificationConfiguration` | 8 | Event rule construction, event type matching, prefix/suffix key filters |
| `TestNotificationDispatcher` | 10 | Event dispatch, filter matching, retry on failure, dead letter queue |
| `TestS3EventMessage` | 6 | Message construction, serialization, event fields |
| `TestContentAddressableStore` | 15 | Chunk splitting, SHA-256 addressing, store new chunk, deduplicate existing, retrieve, reference counting |
| `TestReferenceCounter` | 8 | Increment, decrement, zero-count GC eligibility, WAL protection |
| `TestGarbageCollector` | 8 | Collect zero-ref chunks, safety delay respect, race condition guard |
| `TestGaloisField` | 12 | Addition (XOR), multiplication, division, inverse, table generation, edge cases (zero, one, 255) |
| `TestVandermondeMatrix` | 8 | Matrix construction, systematic property, submatrix inversion |
| `TestErasureCodingEngine` | 18 | Encode/decode with all four storage class parameters, decode from minimum fragments, decode from mixed data/parity, verify clean, verify corrupt detection |
| `TestFragmentDistributor` | 6 | Distribution across locations, collection with failures, InsufficientFragmentsError |
| `TestFragmentIntegrityChecker` | 8 | Chunk check (healthy/corrupt), repair, full scrub |
| `TestMetadataIndex` | 12 | Put/get/delete (hash index), range query (B-tree), prefix query with pagination |
| `TestSegmentLog` | 10 | Append, read, seal, segment size limit, compaction (live/dead fragments) |
| `TestCompactionPolicy` | 6 | Fragmentation threshold, min age, segment selection ordering |
| `TestS3RequestRouter` | 20 | All 36 API routes: bucket CRUD, object CRUD, versioning, lifecycle, replication, notifications, ACL, policy, encryption, multipart, restore |
| `TestS3ResponseFormatter` | 10 | XML serialization for list/error responses, element names match S3 schema |
| `TestS3Metrics` | 8 | Request metrics, storage metrics, dedup metrics, erasure metrics |
| `TestFizzS3Dashboard` | 12 | Bucket summary, storage classes, dedup stats, erasure health, replication, overview |
| `TestFizzS3Middleware` | 15 | Middleware name, priority, process flow, evaluation storage, context enrichment, error handling |
| `TestCreateFizzS3Subsystem` | 8 | Factory wiring, component types, defaults |
| `TestFizzS3Exceptions` | 68 | All 68 exception classes: error codes, context, inheritance chain |
| `TestFizzS3Integration` | 15 | End-to-end: create bucket -> put object -> get object -> version chain -> presign -> lifecycle transition -> dedup stats |

**Total: ~500 tests**

### Test Fixtures

```python
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
```

---

## 15. Implementation Order

1. `GaloisField` (GF(2^8) arithmetic, log/antilog tables)
2. `VandermondeMatrix` (matrix construction and inversion)
3. `ErasureCodingEngine` (encode/decode/verify)
4. `MetadataIndex` (B-tree + hash index)
5. `SegmentLog` + `CompactionPolicy` (append-only data tier)
6. `ReferenceCounter` (content address reference tracking)
7. `FragmentDistributor` (failure domain distribution)
8. `ContentAddressableStore` (chunking, addressing, dedup)
9. `GarbageCollector` (unreferenced chunk reclamation)
10. `FragmentIntegrityChecker` (scrub and repair)
11. Constants and enums
12. Data classes (all 25)
13. `BucketNameValidator`
14. `EncryptionEngine` + `KeyRotationManager`
15. `BucketManager`
16. `VersioningEngine`
17. `ObjectStore`
18. `MultipartUploadManager` + `IncompleteUploadReaper`
19. `SignatureV4Computer`
20. `PresignedURLGenerator` + `PresignedURLVerifier`
21. `StorageClassManager` + `RestoreProcessor`
22. `LifecycleEvaluator` + `LifecycleDaemon`
23. `ReplicationEngine` + `ReplicationConflictResolver`
24. `AccessControlEvaluator`
25. `NotificationDispatcher`
26. `S3RequestRouter` + `S3ResponseFormatter`
27. `S3Metrics`
28. `FizzS3Dashboard`
29. `FizzS3Middleware`
30. `create_fizzs3_subsystem` factory function

---

## 16. Line Budget Estimate

| Section | Lines |
|---------|-------|
| Module docstring + imports | 80 |
| Constants | 60 |
| Enums (12) | 180 |
| Data classes (25) | 400 |
| BucketNameValidator | 40 |
| BucketManager | 200 |
| ObjectStore | 350 |
| VersioningEngine | 200 |
| MultipartUploadManager + Reaper | 300 |
| PresignedURLGenerator + Verifier | 140 |
| SignatureV4Computer | 100 |
| StorageClassManager + RestoreProcessor | 230 |
| LifecycleEvaluator + Daemon | 170 |
| ReplicationEngine + ConflictResolver | 160 |
| EncryptionEngine + KeyRotationManager | 210 |
| AccessControlEvaluator | 150 |
| ContentAddressableStore + ReferenceCounter | 200 |
| GarbageCollector | 60 |
| ErasureCodingEngine | 150 |
| GaloisField | 80 |
| VandermondeMatrix | 80 |
| FragmentDistributor + IntegrityChecker | 130 |
| MetadataIndex | 100 |
| SegmentLog + CompactionPolicy | 110 |
| NotificationDispatcher | 100 |
| S3RequestRouter + ResponseFormatter | 120 |
| S3Metrics | 60 |
| FizzS3Dashboard | 150 |
| FizzS3Middleware | 120 |
| Factory function | 80 |
| **Total** | **~3,500** |

---

## 17. Cross-Subsystem Integration Points

| Subsystem | Integration |
|-----------|-------------|
| **FizzVFS** | FizzS3 replaces FizzVFS for immutable artifact storage; FizzVFS remains for mutable POSIX workloads |
| **FizzVault** | SSE-KMS mode requests data keys from FizzVault for envelope encryption |
| **FizzCap** | Capability-based access control for bucket and object operations |
| **FizzOTel** | Distributed tracing spans for storage requests and internal operations |
| **FizzSLI** | Storage-tier service level indicators (availability, latency, durability) |
| **FizzBill** | Per-bucket storage metering and API call billing |
| **FizzWAL** | Crash-consistent metadata updates via write-ahead log |
| **FizzEventBus** | Object lifecycle event notifications |
| **FizzRegistry** | Optional backend: store OCI blobs in FizzS3 instead of containerd content store |
| **FizzFlame** | Store flame graph SVG renderings as S3 objects |
| **FizzRay** | Store ray-traced image buffers as S3 objects |
| **FizzELF** | Store ELF binary artifacts as S3 objects |
| **FizzCodec** | Store compressed video frames as S3 objects |
| **FizzContainerd** | Content store migration path to FizzS3-backed blob storage |
| **Event Bus** | All lifecycle events published to the platform event bus |
