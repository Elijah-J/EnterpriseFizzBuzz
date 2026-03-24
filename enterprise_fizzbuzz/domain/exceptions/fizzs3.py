"""
Enterprise FizzBuzz Platform - FizzS3: S3-Compatible Object Storage Exceptions

Exception hierarchy for the FizzS3 object storage subsystem.  Each exception
maps to a specific S3-compatible error condition with an EFP-S3xx error code,
enabling categorical error handling in the middleware pipeline and precise
diagnostics for storage operations.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class FizzS3Error(FizzBuzzError):
    """Base exception for all FizzS3 object storage errors.

    FizzS3 provides S3-compatible object storage with erasure coding,
    content-addressable deduplication, versioning, lifecycle management,
    and cross-region replication.  All storage-specific failures inherit
    from this class to enable categorical error handling in the
    middleware pipeline.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzS3 error: {reason}",
            error_code="EFP-S300",
            context={"reason": reason},
        )


# -- Bucket errors (S301-S307) -----------------------------------------------


class BucketError(FizzS3Error):
    """Base exception for bucket-related errors.

    Bucket operations include creation, deletion, listing, and
    configuration changes.  All bucket-specific failures inherit
    from this class.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-S301"
        self.context = {"reason": reason}


class BucketAlreadyExistsError(BucketError):
    """Raised when a bucket name is already in use globally.

    Bucket names are globally unique across all owners and regions.
    Attempting to create a bucket with a name that is already in use
    by another owner triggers this exception.
    """

    def __init__(self, bucket_name: str) -> None:
        super().__init__(f"Bucket already exists: {bucket_name}")
        self.error_code = "EFP-S302"
        self.context = {"bucket_name": bucket_name}


class BucketAlreadyOwnedByYouError(BucketError):
    """Raised when the caller already owns the requested bucket.

    Creating a bucket with a name that the caller already owns is
    idempotent in some configurations but raises this exception when
    the region or configuration differs from the existing bucket.
    """

    def __init__(self, bucket_name: str) -> None:
        super().__init__(f"Bucket already owned by you: {bucket_name}")
        self.error_code = "EFP-S303"
        self.context = {"bucket_name": bucket_name}


class BucketNotEmptyError(BucketError):
    """Raised when attempting to delete a bucket that contains objects.

    Buckets must be empty before deletion.  The caller must delete all
    objects, all object versions, and all in-progress multipart uploads
    before the bucket can be removed.
    """

    def __init__(self, bucket_name: str) -> None:
        super().__init__(f"Bucket not empty: {bucket_name}")
        self.error_code = "EFP-S304"
        self.context = {"bucket_name": bucket_name}


class BucketNotFoundError(BucketError):
    """Raised when the specified bucket does not exist.

    The bucket name does not match any bucket in the metadata index.
    The caller should verify the bucket name and region.
    """

    def __init__(self, bucket_name: str) -> None:
        super().__init__(f"Bucket not found: {bucket_name}")
        self.error_code = "EFP-S305"
        self.context = {"bucket_name": bucket_name}


class InvalidBucketNameError(BucketError):
    """Raised when a bucket name violates S3 naming rules.

    Bucket names must be 3-63 characters, lowercase alphanumeric with
    hyphens and periods, must start and end with a letter or number,
    must not contain consecutive periods, must not be formatted as an
    IPv4 address, must not start with 'xn--', and must not end with
    '-s3alias' or '--ol-s3'.
    """

    def __init__(self, bucket_name: str, violations: list) -> None:
        super().__init__(
            f"Invalid bucket name '{bucket_name}': {', '.join(violations)}"
        )
        self.error_code = "EFP-S306"
        self.context = {"bucket_name": bucket_name, "violations": violations}


class TooManyBucketsError(BucketError):
    """Raised when the maximum bucket count per owner is exceeded.

    Each owner has a configurable maximum number of buckets (default 100).
    Attempts to create buckets beyond this limit are rejected until
    existing buckets are deleted.
    """

    def __init__(self, max_buckets: int) -> None:
        super().__init__(f"Maximum bucket count exceeded: {max_buckets}")
        self.error_code = "EFP-S307"
        self.context = {"max_buckets": max_buckets}


# -- Object errors (S308-S314) -----------------------------------------------


class ObjectError(FizzS3Error):
    """Base exception for object-related errors.

    Object operations include PUT, GET, HEAD, DELETE, COPY, and LIST.
    All object-specific failures inherit from this class.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-S308"
        self.context = {"reason": reason}


class ObjectNotFoundError(ObjectError):
    """Raised when the requested object key does not exist or has a delete marker.

    The key does not exist in the specified bucket, or the current
    version is a delete marker.  For versioned buckets, specific
    version IDs may still be accessible even when the current version
    is a delete marker.
    """

    def __init__(self, bucket_name: str, key: str) -> None:
        super().__init__(f"Object not found: {bucket_name}/{key}")
        self.error_code = "EFP-S309"
        self.context = {"bucket_name": bucket_name, "key": key}


class ObjectTooLargeError(ObjectError):
    """Raised when an object exceeds the single-part upload size limit.

    Single PUT operations are limited to 5 GiB.  Objects larger than
    this must use multipart upload, which supports objects up to 5 TiB.
    """

    def __init__(self, size: int, max_size: int) -> None:
        super().__init__(f"Object too large: {size} bytes (max {max_size})")
        self.error_code = "EFP-S310"
        self.context = {"size": size, "max_size": max_size}


class InvalidObjectKeyError(ObjectError):
    """Raised when an object key exceeds maximum length or contains invalid characters.

    Object keys must be valid UTF-8, at most 1024 bytes, and must not
    contain null bytes or control characters.
    """

    def __init__(self, key: str, reason: str) -> None:
        super().__init__(f"Invalid object key '{key[:64]}...': {reason}")
        self.error_code = "EFP-S311"
        self.context = {"key": key, "reason": reason}


class PreconditionFailedError(ObjectError):
    """Raised when If-Match or If-Unmodified-Since conditions are not met.

    The conditional request specified an ETag or timestamp that does
    not match the current object state.  The client should refresh
    its cached state and retry.
    """

    def __init__(self, condition: str, expected: str, actual: str) -> None:
        super().__init__(
            f"Precondition failed ({condition}): expected {expected}, got {actual}"
        )
        self.error_code = "EFP-S312"
        self.context = {"condition": condition, "expected": expected, "actual": actual}


class NotModifiedError(ObjectError):
    """Raised when If-None-Match or If-Modified-Since conditions indicate no change.

    The object has not been modified since the client's cached version.
    The client can continue using its cached copy.
    """

    def __init__(self, condition: str) -> None:
        super().__init__(f"Not modified: {condition}")
        self.error_code = "EFP-S313"
        self.context = {"condition": condition}


class InvalidRangeError(ObjectError):
    """Raised when a byte range request specifies a range outside the object size.

    The Range header specifies a byte range that exceeds the object's
    content length.  The client should request a valid range within
    [0, content_length - 1].
    """

    def __init__(self, requested: str, object_size: int) -> None:
        super().__init__(
            f"Invalid byte range {requested} for object of size {object_size}"
        )
        self.error_code = "EFP-S314"
        self.context = {"requested": requested, "object_size": object_size}


# -- Versioning errors (S315-S318) -------------------------------------------


class VersionError(FizzS3Error):
    """Base exception for object versioning errors.

    Versioning operations include version ID assignment, version chain
    management, and version-specific retrieval and deletion.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-S315"
        self.context = {"reason": reason}


class NoSuchVersionError(VersionError):
    """Raised when the specified version ID does not exist.

    The version ID does not match any version in the object's version
    chain.  The version may have been permanently deleted or never existed.
    """

    def __init__(self, bucket_name: str, key: str, version_id: str) -> None:
        super().__init__(
            f"No such version: {bucket_name}/{key}?versionId={version_id}"
        )
        self.error_code = "EFP-S316"
        self.context = {
            "bucket_name": bucket_name,
            "key": key,
            "version_id": version_id,
        }


class VersioningNotEnabledError(VersionError):
    """Raised when a versioning operation is attempted on an unversioned bucket.

    Version-specific operations (get by version ID, delete by version ID)
    require the bucket to have versioning enabled or suspended.  Buckets
    in DISABLED state do not support these operations.
    """

    def __init__(self, bucket_name: str) -> None:
        super().__init__(f"Versioning not enabled on bucket: {bucket_name}")
        self.error_code = "EFP-S317"
        self.context = {"bucket_name": bucket_name}


class InvalidVersionIdError(VersionError):
    """Raised when a version ID is malformed.

    Version IDs must be valid UUID hex strings with a timestamp prefix.
    Malformed version IDs are rejected before any metadata lookup.
    """

    def __init__(self, version_id: str) -> None:
        super().__init__(f"Invalid version ID: {version_id}")
        self.error_code = "EFP-S318"
        self.context = {"version_id": version_id}


# -- Multipart upload errors (S319-S325) -------------------------------------


class MultipartUploadError(FizzS3Error):
    """Base exception for multipart upload errors.

    Multipart upload operations include session creation, part upload,
    completion, abortion, and listing.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-S319"
        self.context = {"reason": reason}


class NoSuchUploadError(MultipartUploadError):
    """Raised when the upload ID is not found or the upload has been completed/aborted.

    The upload session identified by the upload ID does not exist in
    the active uploads index.  The upload may have been completed,
    aborted, or never existed.
    """

    def __init__(self, upload_id: str) -> None:
        super().__init__(f"No such upload: {upload_id}")
        self.error_code = "EFP-S320"
        self.context = {"upload_id": upload_id}


class InvalidPartError(MultipartUploadError):
    """Raised when a part reference does not match any uploaded part.

    During multipart upload completion, each part reference must match
    a previously uploaded part.  ETag mismatches or missing part numbers
    trigger this exception.
    """

    def __init__(self, part_number: int, reason: str) -> None:
        super().__init__(f"Invalid part {part_number}: {reason}")
        self.error_code = "EFP-S321"
        self.context = {"part_number": part_number, "reason": reason}


class InvalidPartOrderError(MultipartUploadError):
    """Raised when parts are not in ascending order during completion.

    The parts list in a CompleteMultipartUpload request must be in
    strictly ascending order by part number.  Out-of-order or
    duplicate part numbers trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Invalid part order: {reason}")
        self.error_code = "EFP-S322"
        self.context = {"reason": reason}


class EntityTooSmallError(MultipartUploadError):
    """Raised when a non-final part is below the 5 MB minimum size.

    All parts except the final part must be at least 5 MB.  This
    minimum ensures efficient erasure coding and prevents excessive
    fragment overhead.
    """

    def __init__(self, part_number: int, size: int, min_size: int) -> None:
        super().__init__(
            f"Part {part_number} too small: {size} bytes (minimum {min_size})"
        )
        self.error_code = "EFP-S323"
        self.context = {"part_number": part_number, "size": size, "min_size": min_size}


class EntityTooLargeError(MultipartUploadError):
    """Raised when a part exceeds the 5 GiB maximum size.

    Individual parts must not exceed 5 GiB.  For very large objects,
    use more parts with smaller individual sizes.
    """

    def __init__(self, part_number: int, size: int, max_size: int) -> None:
        super().__init__(
            f"Part {part_number} too large: {size} bytes (maximum {max_size})"
        )
        self.error_code = "EFP-S324"
        self.context = {"part_number": part_number, "size": size, "max_size": max_size}


class TooManyPartsError(MultipartUploadError):
    """Raised when the part number exceeds the 10,000 maximum.

    Multipart uploads support at most 10,000 parts.  With the 5 GiB
    maximum part size, this allows objects up to 50 TiB -- well above
    the 5 TiB maximum object size.
    """

    def __init__(self, part_number: int, max_parts: int) -> None:
        super().__init__(
            f"Part number {part_number} exceeds maximum of {max_parts}"
        )
        self.error_code = "EFP-S325"
        self.context = {"part_number": part_number, "max_parts": max_parts}


# -- Access control errors (S326-S330) ---------------------------------------


class AccessControlError(FizzS3Error):
    """Base exception for authorization and access control errors.

    Access control operations include bucket policy evaluation, ACL
    checking, and block public access enforcement.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-S326"
        self.context = {"reason": reason}


class S3AccessDeniedError(AccessControlError):
    """Raised when the caller lacks permission for the requested operation.

    The access control evaluator determined that the caller's identity
    does not have the required permissions for the requested action on
    the specified resource.
    """

    def __init__(self, principal: str, action: str, resource: str) -> None:
        super().__init__(
            f"Access denied: {principal} cannot {action} on {resource}"
        )
        self.error_code = "EFP-S327"
        self.context = {"principal": principal, "action": action, "resource": resource}


class InvalidPolicyError(AccessControlError):
    """Raised when a bucket policy document is malformed.

    The policy JSON must conform to the IAM policy schema with valid
    Version, Statement, Effect, Principal, Action, and Resource fields.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Invalid policy: {reason}")
        self.error_code = "EFP-S328"
        self.context = {"reason": reason}


class MalformedACLError(AccessControlError):
    """Raised when an ACL document is malformed.

    ACL documents must contain valid owner and grant entries with
    recognized grantee types and permission levels.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Malformed ACL: {reason}")
        self.error_code = "EFP-S329"
        self.context = {"reason": reason}


class PublicAccessBlockedError(AccessControlError):
    """Raised when public access is blocked by bucket-level settings.

    The bucket's BlockPublicAccess configuration prevents the
    requested operation from granting public access.
    """

    def __init__(self, bucket_name: str, setting: str) -> None:
        super().__init__(
            f"Public access blocked on {bucket_name}: {setting}"
        )
        self.error_code = "EFP-S330"
        self.context = {"bucket_name": bucket_name, "setting": setting}


# -- Encryption errors (S331-S335) -------------------------------------------


class EncryptionError(FizzS3Error):
    """Base exception for server-side encryption errors.

    Encryption operations include SSE-S3 managed key encryption,
    SSE-KMS vault-managed encryption, and SSE-C client-provided
    key encryption.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-S331"
        self.context = {"reason": reason}


class InvalidEncryptionKeyError(EncryptionError):
    """Raised when an SSE-C client-provided key is invalid or mismatches.

    The client-provided key must be a valid 256-bit key.  On GET,
    the provided key must match the key used during PUT, verified
    by comparing MD5 hashes.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Invalid encryption key: {reason}")
        self.error_code = "EFP-S332"
        self.context = {"reason": reason}


class KMSKeyNotFoundError(EncryptionError):
    """Raised when the specified FizzVault key ID does not exist.

    SSE-KMS encryption requires a valid key ID in FizzVault.  The
    key may have been deleted, rotated out, or never existed.
    """

    def __init__(self, key_id: str) -> None:
        super().__init__(f"KMS key not found: {key_id}")
        self.error_code = "EFP-S333"
        self.context = {"key_id": key_id}


class KMSAccessDeniedError(EncryptionError):
    """Raised when the caller lacks permission to use the KMS key.

    The caller's identity does not have the required key usage
    permissions in FizzVault for the specified KMS key.
    """

    def __init__(self, key_id: str, principal: str) -> None:
        super().__init__(
            f"KMS access denied: {principal} cannot use key {key_id}"
        )
        self.error_code = "EFP-S334"
        self.context = {"key_id": key_id, "principal": principal}


class KeyRotationInProgressError(EncryptionError):
    """Raised when an operation is blocked by an in-progress key rotation.

    The SSE-S3 master key is currently being rotated.  Operations
    that require the master key must wait until rotation completes.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Key rotation in progress: {reason}")
        self.error_code = "EFP-S335"
        self.context = {"reason": reason}


# -- Replication errors (S336-S339) -------------------------------------------


class ReplicationError(FizzS3Error):
    """Base exception for cross-region replication errors.

    Replication operations include configuration management, object
    replication, delete marker replication, and conflict resolution.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-S336"
        self.context = {"reason": reason}


class ReplicationConfigurationError(ReplicationError):
    """Raised when a replication configuration is invalid.

    The replication configuration must specify valid destination
    buckets, regions, and storage class overrides.  Rules must have
    unique IDs and non-overlapping prefixes at the same priority.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Invalid replication configuration: {reason}")
        self.error_code = "EFP-S337"
        self.context = {"reason": reason}


class ReplicationFailedError(ReplicationError):
    """Raised when object replication fails after exhausting retries.

    The replication engine attempted to replicate the object to the
    destination bucket and failed after the configured maximum number
    of retry attempts.
    """

    def __init__(self, source: str, destination: str, reason: str) -> None:
        super().__init__(
            f"Replication failed from {source} to {destination}: {reason}"
        )
        self.error_code = "EFP-S338"
        self.context = {"source": source, "destination": destination, "reason": reason}


class ReplicationLoopDetectedError(ReplicationError):
    """Raised when bidirectional replication creates an infinite loop.

    The replication engine detected that the source object contains
    x-fizz-replication-source metadata indicating it was itself
    replicated from the destination, preventing an infinite cycle.
    """

    def __init__(self, source: str, destination: str) -> None:
        super().__init__(
            f"Replication loop detected: {source} <-> {destination}"
        )
        self.error_code = "EFP-S339"
        self.context = {"source": source, "destination": destination}


# -- Storage class errors (S340-S344) -----------------------------------------


class StorageClassError(FizzS3Error):
    """Base exception for storage class and archive restore errors.

    Storage class operations include tier transitions, archive restore
    initiation, and restore expiration management.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-S340"
        self.context = {"reason": reason}


class InvalidStorageClassTransitionError(StorageClassError):
    """Raised when a storage class transition violates the waterfall order.

    Storage classes follow a strict waterfall: STANDARD -> STANDARD_IA
    -> ARCHIVE -> DEEP_ARCHIVE.  Reverse transitions are not permitted
    except through the restore mechanism for archived objects.
    """

    def __init__(self, current_class: str, target_class: str) -> None:
        super().__init__(
            f"Invalid transition: {current_class} -> {target_class}"
        )
        self.error_code = "EFP-S341"
        self.context = {"current_class": current_class, "target_class": target_class}


class RestoreInProgressError(StorageClassError):
    """Raised when a restore is already in progress for the object.

    Only one restore operation can be active per object version.
    The caller should wait for the current restore to complete.
    """

    def __init__(self, bucket_name: str, key: str) -> None:
        super().__init__(f"Restore already in progress: {bucket_name}/{key}")
        self.error_code = "EFP-S342"
        self.context = {"bucket_name": bucket_name, "key": key}


class ObjectNotArchivedError(StorageClassError):
    """Raised when attempting to restore a non-archived object.

    Restore operations are only valid for objects in ARCHIVE or
    DEEP_ARCHIVE storage classes.  Objects in STANDARD or STANDARD_IA
    are already directly accessible.
    """

    def __init__(self, bucket_name: str, key: str, storage_class: str) -> None:
        super().__init__(
            f"Object not archived: {bucket_name}/{key} is in {storage_class}"
        )
        self.error_code = "EFP-S343"
        self.context = {
            "bucket_name": bucket_name,
            "key": key,
            "storage_class": storage_class,
        }


class RestoreExpiredError(StorageClassError):
    """Raised when accessing a restored copy that has expired.

    Restored copies of archived objects have a configurable lifetime.
    Once the restore period expires, the temporary copy is removed
    and the object reverts to archived-only access.
    """

    def __init__(self, bucket_name: str, key: str) -> None:
        super().__init__(f"Restore expired: {bucket_name}/{key}")
        self.error_code = "EFP-S344"
        self.context = {"bucket_name": bucket_name, "key": key}


# -- Erasure coding errors (S345-S348) ----------------------------------------


class ErasureCodingError(FizzS3Error):
    """Base exception for Reed-Solomon erasure coding errors.

    Erasure coding operations include encoding, decoding, fragment
    distribution, integrity verification, and repair.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-S345"
        self.context = {"reason": reason}


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


class FragmentCorruptionError(ErasureCodingError):
    """Raised when a fragment fails integrity verification.

    Each fragment is verified against its expected checksum on read.
    A mismatch indicates data corruption in the storage location,
    possibly from bit rot, hardware failure, or software bug.
    The erasure coding engine can recover the original data from
    remaining healthy fragments if sufficient are available.
    """

    def __init__(self, chunk_address: str, fragment_index: int) -> None:
        super().__init__(
            f"Fragment corruption: chunk {chunk_address[:16]}..., "
            f"fragment {fragment_index}"
        )
        self.error_code = "EFP-S347"
        self.context = {
            "chunk_address": chunk_address,
            "fragment_index": fragment_index,
        }


class FragmentLocationUnavailableError(ErasureCodingError):
    """Raised when a storage location is unreachable.

    The fragment distributor cannot access the storage location where
    a fragment is stored.  This may be a transient network failure or
    a permanent location loss.
    """

    def __init__(self, location: str, reason: str) -> None:
        super().__init__(f"Fragment location unavailable: {location}: {reason}")
        self.error_code = "EFP-S348"
        self.context = {"location": location, "reason": reason}


# -- Content-addressable store errors (S349-S352) ----------------------------


class ContentAddressError(FizzS3Error):
    """Base exception for content-addressable deduplication errors.

    Content-addressable operations include chunk splitting, SHA-256
    addressing, reference counting, and garbage collection.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-S349"
        self.context = {"reason": reason}


class ChunkNotFoundError(ContentAddressError):
    """Raised when a chunk is not found at the expected content address.

    The content-addressable store does not contain a chunk at the
    specified SHA-256 address.  This may indicate premature garbage
    collection or a corrupted chunk manifest.
    """

    def __init__(self, address: str) -> None:
        super().__init__(f"Chunk not found: {address[:16]}...")
        self.error_code = "EFP-S350"
        self.context = {"address": address}


class ReferenceIntegrityError(ContentAddressError):
    """Raised when the reference count for a chunk is inconsistent.

    The reference counter detected an inconsistency between the
    recorded reference count and the actual number of objects
    referencing the chunk.
    """

    def __init__(self, address: str, recorded: int, actual: int) -> None:
        super().__init__(
            f"Reference integrity error for {address[:16]}...: "
            f"recorded={recorded}, actual={actual}"
        )
        self.error_code = "EFP-S351"
        self.context = {
            "address": address,
            "recorded_count": recorded,
            "actual_count": actual,
        }


class DeduplicationHashCollisionError(ContentAddressError):
    """Raised when two different data blocks produce the same SHA-256 hash.

    SHA-256 collision probability is approximately 1 in 2^128 for
    random inputs.  This exception exists for completeness and
    correctness but is not expected to occur in practice.
    """

    def __init__(self, address: str) -> None:
        super().__init__(f"Hash collision detected at {address[:16]}...")
        self.error_code = "EFP-S352"
        self.context = {"address": address}


# -- Lifecycle errors (S353-S355) ---------------------------------------------


class LifecycleError(FizzS3Error):
    """Base exception for lifecycle management errors.

    Lifecycle operations include rule evaluation, storage class
    transitions, object expiration, and multipart upload cleanup.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-S353"
        self.context = {"reason": reason}


class InvalidLifecycleConfigurationError(LifecycleError):
    """Raised when a lifecycle configuration is malformed.

    Lifecycle configurations must contain valid rules with unique IDs,
    valid prefix filters, and transition days that respect the storage
    class waterfall ordering.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Invalid lifecycle configuration: {reason}")
        self.error_code = "EFP-S354"
        self.context = {"reason": reason}


class TooManyLifecycleRulesError(LifecycleError):
    """Raised when the lifecycle rule count exceeds the maximum.

    Each bucket supports at most 1000 lifecycle rules.  Consolidate
    rules with the same transition/expiration targets to reduce count.
    """

    def __init__(self, count: int, max_rules: int) -> None:
        super().__init__(f"Too many lifecycle rules: {count} (max {max_rules})")
        self.error_code = "EFP-S355"
        self.context = {"count": count, "max_rules": max_rules}


# -- Presigned URL errors (S356-S359) ----------------------------------------


class PresignedURLError(FizzS3Error):
    """Base exception for presigned URL generation and verification errors.

    Presigned URL operations include URL generation with AWS Signature
    Version 4, POST parameter generation, and incoming URL verification.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-S356"
        self.context = {"reason": reason}


class ExpiredPresignedURLError(PresignedURLError):
    """Raised when a presigned URL has expired.

    The current time exceeds the URL's X-Amz-Date plus X-Amz-Expires
    parameters.  The maximum presigned URL validity is 7 days.
    """

    def __init__(self, url: str, expired_at: str) -> None:
        super().__init__(f"Presigned URL expired at {expired_at}")
        self.error_code = "EFP-S357"
        self.context = {"url": url, "expired_at": expired_at}


class InvalidSignatureError(PresignedURLError):
    """Raised when the signature in a presigned URL does not match.

    The recomputed signature does not match the X-Amz-Signature
    parameter.  This may indicate URL tampering, key mismatch,
    or incorrect signing implementation.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Invalid signature: {reason}")
        self.error_code = "EFP-S358"
        self.context = {"reason": reason}


class SignatureMethodMismatchError(PresignedURLError):
    """Raised when the HTTP method does not match the signed method.

    The presigned URL was generated for a specific HTTP method.
    Using a different method (e.g., PUT on a GET-signed URL) is
    rejected because the method is part of the signed payload.
    """

    def __init__(self, signed_method: str, actual_method: str) -> None:
        super().__init__(
            f"Method mismatch: signed for {signed_method}, "
            f"received {actual_method}"
        )
        self.error_code = "EFP-S359"
        self.context = {
            "signed_method": signed_method,
            "actual_method": actual_method,
        }


# -- Metadata errors (S360-S362) ---------------------------------------------


class MetadataError(FizzS3Error):
    """Base exception for metadata tier errors.

    Metadata operations include B-tree and hash index management,
    WAL-protected writes, checkpoints, and range queries.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-S360"
        self.context = {"reason": reason}


class MetadataCorruptionError(MetadataError):
    """Raised when the metadata index detects an inconsistency.

    The metadata index has detected a structural inconsistency in the
    B-tree or hash index.  This may require a full index rebuild from
    the segment log.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Metadata corruption: {reason}")
        self.error_code = "EFP-S361"
        self.context = {"reason": reason}


class MetadataCapacityExceededError(MetadataError):
    """Raised when user-defined metadata exceeds the 2 KB limit.

    Each object supports up to 2 KB of user-defined metadata (key-value
    pairs).  The total size includes both keys and values encoded as
    UTF-8.
    """

    def __init__(self, size: int, max_size: int) -> None:
        super().__init__(
            f"Metadata capacity exceeded: {size} bytes (max {max_size})"
        )
        self.error_code = "EFP-S362"
        self.context = {"size": size, "max_size": max_size}


# -- Notification errors (S363-S365) ------------------------------------------


class NotificationError(FizzS3Error):
    """Base exception for event notification errors.

    Notification operations include configuration management, event
    matching, and asynchronous dispatch to destinations.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-S363"
        self.context = {"reason": reason}


class InvalidNotificationConfigurationError(NotificationError):
    """Raised when a notification configuration is malformed.

    Notification configurations must specify valid event types,
    destination types, and destination targets.  Prefix and suffix
    filters must be valid UTF-8 strings.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Invalid notification configuration: {reason}")
        self.error_code = "EFP-S364"
        self.context = {"reason": reason}


class NotificationDeliveryFailedError(NotificationError):
    """Raised when notification delivery fails after exhausting retries.

    The notification dispatcher attempted to deliver the event
    notification to the configured destination and failed after
    the maximum number of retry attempts with exponential backoff.
    """

    def __init__(self, destination: str, reason: str) -> None:
        super().__init__(
            f"Notification delivery failed to {destination}: {reason}"
        )
        self.error_code = "EFP-S365"
        self.context = {"destination": destination, "reason": reason}


# -- Middleware / dashboard errors (S366-S367) --------------------------------


class FizzS3MiddlewareError(FizzS3Error):
    """Raised when the FizzS3 middleware fails to process an evaluation.

    The middleware intercepts each FizzBuzz evaluation to store the
    result as an S3 object.  If storage or metadata operations fail
    during middleware processing, this exception is raised.
    """

    def __init__(self, evaluation_number: int, reason: str) -> None:
        super().__init__(
            f"FizzS3 middleware error at evaluation {evaluation_number}: {reason}"
        )
        self.error_code = "EFP-S366"
        self.context = {"evaluation_number": evaluation_number, "reason": reason}
        self.evaluation_number = evaluation_number


class FizzS3DashboardError(FizzS3Error):
    """Raised when the FizzS3 dashboard rendering fails.

    The dashboard renders storage metrics, bucket summaries,
    deduplication statistics, erasure coding health, and replication
    status in ASCII format.  Data retrieval or rendering failures
    trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"FizzS3 dashboard rendering failed: {reason}")
        self.error_code = "EFP-S367"
        self.context = {"reason": reason}
