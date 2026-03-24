# FizzS3 -- S3-Compatible Object Storage

## The Problem

The Enterprise FizzBuzz Platform has three persistence backends: in-memory (for development), SQLite (for structured relational data), and filesystem (for flat file output). It has a virtual filesystem (FizzVFS) providing POSIX-compatible file operations with inodes, directory entries, and file descriptors. It has a copy-on-write union filesystem (FizzOverlay) for container image layering. It has a columnar storage engine (FizzColumn) for analytical queries. It has a version control system (FizzVCS) for source artifact tracking. It has a content-addressable store inside FizzContainerd for OCI image blobs. It has a database replication system (FizzReplica) for high availability of structured data.

None of these are object storage.

Object storage is a fundamentally different storage paradigm from file systems and relational databases. File systems organize data hierarchically in directories with mutable files. Relational databases organize data in tables with rows and columns, supporting transactions and joins. Object storage organizes data as immutable blobs identified by keys within flat namespaces called buckets. Objects have no hierarchy, no directory structure, no rename operation, and no append operation. They are written once, read many times, and optionally versioned. Each object carries arbitrary metadata (key-value pairs) alongside its data payload.

Amazon S3 established the object storage API in 2006. It became the de facto standard for cloud-native data persistence. Every major cloud provider implements S3-compatible APIs: Google Cloud Storage, Azure Blob Storage (with S3 compatibility layer), MinIO, Ceph RADOS Gateway, Wasabi, Backblaze B2, DigitalOcean Spaces. The S3 API is the lingua franca of unstructured data storage. Applications that store ML model weights, log archives, backup snapshots, container images, media files, data lake partitions, or configuration bundles overwhelmingly use S3-compatible storage as their backend.

The Enterprise FizzBuzz Platform produces artifacts that belong in object storage. The FizzFlame flame graph generator produces SVG renderings. The FizzRay ray tracer produces image buffers. The FizzPDF document generator produces PDF files. The FizzCodec video encoder produces compressed video frames. The FizzELF binary generator produces ELF executables. The FizzPrint typesetter produces formatted output documents. The FizzSheet spreadsheet engine produces workbook files. The FizzRegistry OCI image registry stores blobs that are inherently object-storage workloads. The FizzWAL write-ahead log produces segment files. The FizzVCS version control system produces packfiles. Every one of these subsystems currently writes to FizzVFS using POSIX file operations, storing their artifacts in a hierarchical filesystem that imposes directory structure, path length limits, and inode overhead on data that has no need for hierarchy.

Object storage provides durability guarantees that file systems do not. S3 achieves 99.999999999% (eleven nines) durability through erasure coding -- splitting each object into data fragments and parity fragments distributed across independent failure domains, such that the object can be reconstructed from any subset of fragments exceeding the data fragment count. A file system achieves durability through replication (keeping multiple copies) or RAID (hardware-level striping with parity). Erasure coding is more storage-efficient than replication (1.5x overhead vs 2x or 3x) while providing higher durability guarantees.

Object storage provides lifecycle management that file systems do not. S3 lifecycle policies automatically transition objects between storage classes (Standard -> Infrequent Access -> Glacier -> Deep Archive) based on age, reducing storage costs for data that is accessed less frequently over time. A file system stores all data at the same cost regardless of access frequency. The platform's historical evaluation logs, archived audit trails, old flame graph renderings, and superseded ML model weights consume the same storage resources as actively accessed data.

Object storage provides cross-region replication that file systems do not. S3 Cross-Region Replication automatically copies objects to buckets in different geographic regions, providing disaster recovery and data locality. FizzReplica provides replication for the SQLite relational database, but no replication exists for unstructured data artifacts.

Object storage provides presigned URLs that file systems do not. S3 presigned URLs allow time-limited, credential-free access to specific objects, enabling secure sharing of artifacts without exposing storage credentials. The platform has no mechanism for generating temporary access URLs to stored artifacts.

Object storage provides event notifications that file systems do not. S3 event notifications fire when objects are created, deleted, or transitioned between storage classes, enabling event-driven architectures. FizzVFS has no file-level event notification system.

The platform has databases. It has file systems. It has columnar storage. It does not have object storage. This is a gap in the storage tier that affects every subsystem producing unstructured artifacts.

## The Vision

FizzS3 is a complete S3-compatible object storage service for the Enterprise FizzBuzz Platform, implementing the core S3 REST API surface: bucket operations (create, delete, list, get location, get versioning), object operations (PUT, GET, HEAD, DELETE, LIST with prefix/delimiter, multipart upload), object versioning (version IDs, delete markers, version-specific GET/DELETE), presigned URLs (time-limited, method-scoped, signature-verified), storage classes (Standard, Infrequent Access, Archive, Deep Archive), lifecycle policies (transition rules, expiration rules, abort incomplete multipart upload rules, noncurrent version expiration), cross-region replication (continuous asynchronous replication with conflict resolution), server-side encryption (SSE-S3 with platform-managed keys, SSE-KMS with FizzVault-managed keys, SSE-C with client-provided keys), access control (bucket policies with IAM-style condition operators, access control lists with canned ACL presets, block public access settings), event notifications (object-created, object-deleted, object-transitioned events published to FizzEventBus), content-addressable deduplication (SHA-256 content hashing with reference counting to eliminate duplicate storage), and erasure coding (Reed-Solomon coding with configurable data/parity fragment ratios for tunable durability).

The storage engine uses a two-tier architecture: a metadata tier storing bucket configurations, object metadata, version histories, lifecycle policies, and access control rules in a B-tree index; and a data tier storing object content as content-addressed chunks in an append-only segment log with periodic compaction. The metadata tier is designed for low-latency key lookups. The data tier is designed for high-throughput sequential reads and writes. This separation mirrors the architecture of production object storage systems like MinIO and Ceph RGW, where metadata operations (LIST, HEAD) have fundamentally different performance characteristics from data operations (GET body, PUT body).

FizzS3 integrates with the platform's existing subsystems: FizzCap for capability-based access control on bucket and object operations, FizzOTel for distributed tracing of storage requests, FizzSLI for storage-tier service level indicators (availability, latency, durability), FizzBill for per-bucket storage metering and API call billing, FizzWAL for crash-consistent metadata updates, FizzEventBus for object lifecycle event notifications, FizzVault for encryption key management, and FizzRegistry as an optional backend (storing OCI blobs in FizzS3 instead of the containerd content store).

## Key Components

### Module: `fizzs3.py` (~3,500 lines)

---

### 1. Bucket Management

Buckets are the top-level namespace containers in FizzS3. Each bucket has a globally unique name, a region assignment, a versioning configuration, a lifecycle policy, an access control policy, and a set of server-side encryption defaults.

- **`Bucket`**: the core bucket model containing:
  - `name` (str): globally unique bucket identifier, validated against S3 naming rules (3-63 characters, lowercase alphanumeric and hyphens, must start with a letter or number, must not be formatted as an IP address, must not start with `xn--` or end with `-s3alias`)
  - `region` (str): the region where the bucket's data is stored, defaulting to `fizz-east-1`. Supported regions: `fizz-east-1`, `fizz-west-1`, `fizz-eu-1`, `fizz-ap-1`
  - `creation_date` (datetime): UTC timestamp of bucket creation
  - `versioning` (`BucketVersioning`): enum with states `DISABLED`, `ENABLED`, `SUSPENDED`. Once enabled, versioning cannot be disabled -- only suspended. Suspended versioning preserves existing versions but assigns `null` version IDs to new object writes
  - `lifecycle_configuration` (Optional[`LifecycleConfiguration`]): lifecycle rules governing object transitions and expirations
  - `acl` (`AccessControlList`): the bucket's access control list, initialized to the default `private` canned ACL
  - `policy` (Optional[`BucketPolicy`]): IAM-style bucket policy document
  - `encryption_configuration` (`EncryptionConfiguration`): default server-side encryption settings for objects stored in this bucket
  - `replication_configuration` (Optional[`ReplicationConfiguration`]): cross-region replication rules
  - `notification_configuration` (Optional[`NotificationConfiguration`]): event notification rules
  - `block_public_access` (`BlockPublicAccessConfiguration`): four independent boolean flags -- `block_public_acls`, `ignore_public_acls`, `block_public_policy`, `restrict_public_buckets` -- defaulting to all `True`
  - `object_lock_enabled` (bool): whether S3 Object Lock is enabled for compliance retention
  - `tags` (Dict[str, str]): bucket-level tags for cost allocation and organization, maximum 50 tags per bucket

- **`BucketManager`**: manages the lifecycle of buckets:
  - `create_bucket(name, region, acl, object_lock)`: creates a new bucket. Validates the bucket name against naming rules. Checks for name uniqueness across all regions (bucket names are globally unique, not per-region). Initializes the bucket with the default ACL, encryption configuration, and block public access settings. Writes the bucket metadata record to the metadata tier via a WAL-protected transaction. Emits a `BucketCreated` event to FizzEventBus. Returns the `Bucket` object
  - `delete_bucket(name)`: deletes a bucket. Validates that the bucket is empty (contains no objects and no incomplete multipart uploads). If the bucket contains objects, raises `BucketNotEmptyError` with the count of remaining objects. Removes the bucket metadata record from the metadata tier. Emits a `BucketDeleted` event. Deletion is permanent and irreversible -- the bucket name becomes available for reuse after deletion
  - `head_bucket(name)`: checks whether a bucket exists and the caller has permission to access it. Returns `200 OK` equivalent if the bucket exists and is accessible, `404 Not Found` if the bucket does not exist, `403 Forbidden` if the bucket exists but the caller lacks access. This operation does not return the bucket's contents or configuration
  - `list_buckets(owner)`: returns all buckets owned by the specified principal. Each entry includes the bucket name and creation date. The list is sorted alphabetically by bucket name
  - `get_bucket_location(name)`: returns the region where the bucket is stored
  - `get_bucket_versioning(name)`: returns the versioning state of the bucket (`DISABLED`, `ENABLED`, or `SUSPENDED`)
  - `put_bucket_versioning(name, status)`: enables or suspends versioning on a bucket. Enabling versioning on a bucket that has never been versioned transitions it from `DISABLED` to `ENABLED`. Suspending versioning on a versioned bucket transitions it from `ENABLED` to `SUSPENDED`. Versioning cannot transition from `ENABLED` or `SUSPENDED` back to `DISABLED`

- **`BucketNameValidator`**: validates bucket names against the S3 naming specification:
  - Length between 3 and 63 characters
  - Contains only lowercase letters, numbers, hyphens, and periods
  - Starts and ends with a letter or number
  - Does not contain consecutive periods
  - Is not formatted as an IPv4 address (e.g., `192.168.1.1`)
  - Does not start with the prefix `xn--` (reserved for Internationalized Domain Names)
  - Does not end with the suffix `-s3alias` (reserved for access point aliases)
  - Does not end with the suffix `--ol-s3` (reserved for Object Lambda access points)
  - Returns a `BucketNameValidationResult` with `is_valid` boolean and `violations` list

---

### 2. Object Operations

Objects are the fundamental storage units in FizzS3. Each object consists of a key (string identifier within a bucket), a data payload (bytes), metadata (system-defined and user-defined key-value pairs), and storage class assignment.

- **`S3Object`**: the core object model containing:
  - `key` (str): the object's key within its bucket. Keys can contain any UTF-8 character and have a maximum length of 1,024 bytes. Keys can contain forward slashes to simulate directory hierarchy (e.g., `logs/2026/03/24/access.log`), but this hierarchy is purely notional -- FizzS3 stores all objects in a flat namespace and simulates directory listing through prefix/delimiter queries
  - `version_id` (Optional[str]): the version identifier for this object. `None` for unversioned buckets. A UUID for versioned buckets. The special value `null` for objects written to a bucket while versioning is suspended
  - `data` (bytes): the object's content payload. Maximum object size is 5 TiB (5,497,558,138,880 bytes). Objects larger than 5 GiB must use multipart upload
  - `size` (int): the size of the data payload in bytes
  - `etag` (str): the entity tag, computed as the MD5 hex digest of the object data for single-part uploads, or the MD5 hex digest of the concatenated part MD5s followed by a hyphen and the part count for multipart uploads (e.g., `d41d8cd98f00b204e9800998ecf8427e-3` for a 3-part multipart upload)
  - `content_type` (str): the MIME type of the object content, defaulting to `application/octet-stream`
  - `content_encoding` (Optional[str]): the encoding applied to the object content (e.g., `gzip`, `deflate`)
  - `content_disposition` (Optional[str]): presentation information for the object (e.g., `attachment; filename="report.pdf"`)
  - `content_language` (Optional[str]): the language the object content is in (e.g., `en-US`, `tlh` for Klingon)
  - `cache_control` (Optional[str]): caching directives for the object (e.g., `max-age=3600, public`)
  - `last_modified` (datetime): UTC timestamp of the last modification (creation for immutable objects)
  - `storage_class` (`StorageClass`): the storage class assignment for this object
  - `metadata` (Dict[str, str]): user-defined metadata key-value pairs. Keys are prefixed with `x-amz-meta-` in the API but stored without the prefix internally. Maximum 2 KB total size for all user metadata
  - `server_side_encryption` (Optional[`ServerSideEncryption`]): encryption algorithm and key information if the object is encrypted
  - `delete_marker` (bool): whether this version is a delete marker (a zero-byte placeholder indicating that the object was deleted in a versioned bucket)
  - `is_latest` (bool): whether this version is the current (latest) version of the object
  - `checksum` (Optional[`ObjectChecksum`]): additional integrity checksum (CRC32, CRC32C, SHA-1, SHA-256) provided at upload time

- **`ObjectStore`**: the core object storage operations:
  - `put_object(bucket, key, data, metadata, content_type, storage_class, encryption, checksum_algorithm)`: stores an object in a bucket. Validates that the bucket exists, the caller has `s3:PutObject` permission, the object size does not exceed the single-part upload limit (5 GiB), and the metadata size does not exceed 2 KB. Computes the ETag (MD5 of the data). Assigns a version ID if the bucket has versioning enabled. Encrypts the data if server-side encryption is configured. Chunks the data into content-addressed blocks, deduplicates against existing blocks, applies erasure coding to each block, and writes the encoded fragments to the data tier. Writes the object metadata record to the metadata tier. Publishes an `s3:ObjectCreated:Put` event to the notification configuration. Returns the `S3Object` with version ID and ETag
  - `get_object(bucket, key, version_id, range, if_match, if_none_match, if_modified_since, if_unmodified_since)`: retrieves an object from a bucket. Supports conditional GET via `If-Match` (ETag match), `If-None-Match` (ETag mismatch), `If-Modified-Since` (timestamp comparison), and `If-Unmodified-Since` (timestamp comparison). If the object has a delete marker at the current version, returns `404 Not Found` with an `x-amz-delete-marker: true` header. Supports byte-range requests via the `Range` parameter (e.g., `bytes=0-1023` for the first 1 KB), returning partial content with a `206 Partial Content` status. Decrypts the data if server-side encryption is applied. Reassembles the object from content-addressed blocks, decoding erasure-coded fragments as needed. Returns the `S3Object` with data, metadata, and headers
  - `head_object(bucket, key, version_id)`: retrieves object metadata without the data payload. Returns all headers that `get_object` would return (ETag, Content-Type, Content-Length, Last-Modified, version ID, storage class, encryption info, user metadata) but no body. Used for existence checks, metadata inspection, and conditional request evaluation without data transfer
  - `delete_object(bucket, key, version_id)`: deletes an object. Behavior depends on versioning state:
    - **Unversioned bucket**: permanently deletes the object and its data. Publishes `s3:ObjectRemoved:Delete` event
    - **Versioned bucket, no version_id specified**: inserts a delete marker as the current version. The object appears deleted to `get_object` (returns 404 with delete marker header) but all previous versions remain accessible via version-specific GET. Publishes `s3:ObjectRemoved:DeleteMarkerCreated` event
    - **Versioned bucket, version_id specified**: permanently deletes the specified version. If the deleted version was the current version, the previous version becomes current. If the deleted version was a delete marker, removes the delete marker (effectively undeleting the object). Publishes `s3:ObjectRemoved:Delete` event
  - `delete_objects(bucket, objects)`: batch delete of up to 1,000 objects in a single request. Each entry specifies a key and optional version ID. Returns a list of successfully deleted objects and a list of errors. Processes deletions in parallel. This is the multi-object delete API used for bulk cleanup operations
  - `copy_object(source_bucket, source_key, dest_bucket, dest_key, source_version_id, metadata_directive, storage_class)`: copies an object from one location to another. The `metadata_directive` controls whether the copy preserves the source's metadata (`COPY`) or replaces it with new metadata provided in the request (`REPLACE`). Copy can change the storage class, encryption, or metadata of an object without re-uploading the data. For content-addressed storage, copy is a metadata-only operation when the source and destination are in the same region -- no data is transferred, only a new metadata record pointing to the same content-addressed blocks
  - `list_objects_v2(bucket, prefix, delimiter, start_after, continuation_token, max_keys, encoding_type)`: lists objects in a bucket with prefix filtering and delimiter-based hierarchy simulation. The `prefix` parameter filters results to only include objects whose keys start with the specified string. The `delimiter` parameter (typically `/`) groups keys that share a common prefix up to the delimiter, returning them as `CommonPrefixes` (simulating directory listing). `max_keys` limits the result set (default 1,000, maximum 1,000). If the result is truncated, `is_truncated` is `True` and `next_continuation_token` is returned for pagination. Results are sorted lexicographically by key. Each returned object includes key, last modified, ETag, size, storage class, and owner

- **`ListObjectsResult`**: the response model for `list_objects_v2`:
  - `contents` (List[`ObjectSummary`]): list of objects matching the query, each containing `key`, `last_modified`, `etag`, `size`, `storage_class`, `owner`
  - `common_prefixes` (List[str]): list of key prefixes shared by multiple keys, rolled up by the delimiter (e.g., with delimiter `/` and keys `logs/a.txt`, `logs/b.txt`, `data/c.txt`, the common prefixes are `logs/` and `data/`)
  - `is_truncated` (bool): whether the result set was truncated at `max_keys`
  - `next_continuation_token` (Optional[str]): opaque token for requesting the next page of results
  - `key_count` (int): number of keys returned in this response
  - `max_keys` (int): the maximum number of keys requested
  - `prefix` (Optional[str]): the prefix filter applied to the listing
  - `delimiter` (Optional[str]): the delimiter used for hierarchy simulation

---

### 3. Object Versioning

Versioning provides immutable history for every object in a bucket. When versioning is enabled, every PUT operation creates a new version rather than overwriting the existing object. DELETE operations insert delete markers rather than removing data. Every version is independently addressable by its version ID.

- **`VersioningEngine`**: manages version chains for objects in versioned buckets:
  - `assign_version_id()`: generates a UUID-based version ID for a new object version. Version IDs are chronologically sortable -- they encode the creation timestamp in their most significant bits so that version listing returns results in reverse chronological order (newest first) without requiring a secondary sort
  - `get_version_chain(bucket, key)`: returns the complete version history for an object key, ordered from newest to oldest. Each entry includes the version ID, last modified timestamp, ETag, size, storage class, and whether the version is a delete marker. The first entry in the chain is the current version. If the current version is a delete marker, the object appears deleted to non-version-aware API calls
  - `get_specific_version(bucket, key, version_id)`: retrieves a specific version of an object. Returns the object data and metadata for the requested version regardless of whether it is the current version or whether the current version is a delete marker. Raises `NoSuchVersion` if the version ID does not exist
  - `delete_specific_version(bucket, key, version_id)`: permanently removes a specific version from the version chain. This is the only way to permanently delete data in a versioned bucket. If the deleted version was the current version, the previous non-delete-marker version becomes current. If the deleted version was a delete marker and it was the only entry with that key's current state, removing it effectively restores the object
  - `list_object_versions(bucket, prefix, key_marker, version_id_marker, max_keys)`: lists all versions of all objects in a bucket, including delete markers. Supports prefix filtering and pagination via key marker / version ID marker. Returns versions in key-ascending, version-descending order (all versions of key A before key B, newest version of each key first)

- **`DeleteMarker`**: a special zero-byte object version that indicates an object has been deleted:
  - `key` (str): the object key
  - `version_id` (str): the version ID of the delete marker
  - `last_modified` (datetime): when the delete was issued
  - `owner` (str): the principal who issued the delete
  - `is_latest` (bool): whether this delete marker is the current version (most recent entry in the version chain)

- **`VersionSuspension`**: manages the transition from enabled to suspended versioning:
  - When versioning is suspended, new PUT operations assign the special version ID `null` instead of a UUID. If a previous object version with version ID `null` exists, it is overwritten (the only case where a PUT operation replaces an existing version). UUID-versioned objects are unaffected by suspension -- they remain accessible by their version IDs
  - When versioning is re-enabled after suspension, new PUT operations resume assigning UUID version IDs. The `null`-versioned objects remain in the version chain alongside UUID-versioned objects

---

### 4. Multipart Upload

Multipart upload allows objects larger than 5 GiB to be uploaded in parts, and provides resilience for large uploads by allowing individual parts to be retried independently without re-uploading the entire object.

- **`MultipartUploadManager`**: orchestrates multipart upload lifecycle:
  - `create_multipart_upload(bucket, key, metadata, content_type, storage_class, encryption)`: initiates a multipart upload session. Validates permissions and bucket existence. Generates a unique `upload_id` that identifies this upload session. Records the upload metadata (key, content type, storage class, encryption, timestamp) in the metadata tier. Returns the `upload_id`. No data is stored at this point -- the upload is in-flight until completed or aborted
  - `upload_part(bucket, key, upload_id, part_number, data)`: uploads a single part of a multipart upload. Part numbers range from 1 to 10,000. Each part (except the last) must be at least 5 MB. Parts can be uploaded in any order and can be re-uploaded (a new upload of the same part number replaces the previous upload for that part number). Computes the part's MD5 ETag. Stores the part data in the data tier using content-addressed blocks with erasure coding. Records the part metadata (part number, ETag, size) in the upload's part manifest. Returns the part's ETag
  - `upload_part_copy(bucket, key, upload_id, part_number, source_bucket, source_key, source_version_id, byte_range)`: uploads a part by copying a byte range from an existing object. This enables server-side copy of large objects: initiate a multipart upload, copy each byte range from the source as a part, and complete the upload. No data leaves the storage service -- copy is performed server-side. The `byte_range` parameter specifies which bytes of the source object to copy (e.g., `bytes=0-5242879` for the first 5 MB)
  - `complete_multipart_upload(bucket, key, upload_id, parts)`: completes a multipart upload by assembling the parts into a final object. The `parts` parameter is an ordered list of (part_number, etag) tuples that must match the uploaded parts. Validates that all specified parts exist and their ETags match. Concatenates the parts in order to form the complete object. Computes the composite ETag (MD5 of concatenated part MD5s, hyphen, part count). Creates the object metadata record with the specified storage class, encryption, and metadata. Publishes `s3:ObjectCreated:CompleteMultipartUpload` event. Cleans up the upload session's temporary part storage. Returns the final object's ETag, version ID, and location
  - `abort_multipart_upload(bucket, key, upload_id)`: aborts a multipart upload session. Deletes all uploaded parts from the data tier. Removes the upload session record from the metadata tier. After abortion, the upload ID is no longer valid. Parts that were uploaded are permanently deleted and their storage is reclaimed
  - `list_multipart_uploads(bucket, prefix, key_marker, upload_id_marker, max_uploads)`: lists in-progress multipart uploads for a bucket. Each entry includes the key, upload ID, initiation timestamp, and storage class. Supports prefix filtering and pagination. Used for auditing in-progress uploads and identifying uploads that should be aborted (stale uploads consume storage for their uploaded parts without producing a completed object)
  - `list_parts(bucket, key, upload_id, part_number_marker, max_parts)`: lists the parts uploaded so far for a specific multipart upload. Each entry includes the part number, ETag, size, and last modified timestamp. Supports pagination via part number marker. Used for resuming an interrupted multipart upload (check which parts have been uploaded, upload the remaining parts, then complete)

- **`MultipartUpload`**: the upload session model:
  - `upload_id` (str): unique identifier for this upload session
  - `bucket` (str): the target bucket
  - `key` (str): the target object key
  - `initiated` (datetime): when the upload was initiated
  - `storage_class` (`StorageClass`): the storage class for the completed object
  - `encryption` (Optional[`ServerSideEncryption`]): encryption configuration
  - `metadata` (Dict[str, str]): user-defined metadata for the completed object
  - `parts` (Dict[int, `UploadPart`]): map of part number to uploaded part metadata

- **`UploadPart`**: metadata for a single uploaded part:
  - `part_number` (int): the part's sequence number (1-10000)
  - `etag` (str): MD5 hex digest of the part data
  - `size` (int): the part's size in bytes
  - `last_modified` (datetime): when the part was uploaded or last re-uploaded

- **`IncompleteUploadReaper`**: a background cleanup process that identifies and aborts multipart uploads that have been in progress longer than a configurable threshold (default: 7 days). Stale multipart uploads can accumulate significant storage costs from uploaded parts that will never be assembled into a complete object. The reaper runs on a configurable interval (default: every 24 hours) and respects lifecycle policy rules for `AbortIncompleteMultipartUpload` with per-bucket thresholds

---

### 5. Presigned URLs

Presigned URLs enable time-limited access to specific objects without requiring the requester to have storage credentials. The URL encodes the operation, the target object, the expiration time, and a cryptographic signature that proves the URL was generated by an authorized principal.

- **`PresignedURLGenerator`**: generates presigned URLs for object operations:
  - `generate_presigned_url(method, bucket, key, version_id, expiration, headers, query_params)`: generates a presigned URL for the specified HTTP method (`GET`, `PUT`, `DELETE`, `HEAD`). The URL includes:
    - `X-Amz-Algorithm`: the signing algorithm, always `AWS4-HMAC-SHA256` (using FizzVault's HMAC key infrastructure)
    - `X-Amz-Credential`: the access key ID, date stamp, region, service, and request type, formatted as `{access_key}/{date}/{region}/s3/aws4_request`
    - `X-Amz-Date`: the timestamp of URL generation in ISO 8601 format
    - `X-Amz-Expires`: the validity duration in seconds (minimum 1, maximum 604,800 = 7 days)
    - `X-Amz-SignedHeaders`: the headers included in the signature computation (at minimum `host`)
    - `X-Amz-Signature`: the HMAC-SHA256 signature computed over the canonical request, string to sign, and signing key
  - `generate_presigned_post(bucket, key, conditions, expiration)`: generates presigned POST parameters for browser-based uploads. Returns a dictionary containing the URL to POST to and a set of form fields (including the policy document and signature) that must be included in the POST body. The `conditions` parameter specifies constraints on the upload: exact key match, key prefix, content type, content length range, and metadata values. The policy document is a Base64-encoded JSON structure listing these conditions, signed with the same HMAC-SHA256 mechanism

- **`PresignedURLVerifier`**: validates presigned URLs on incoming requests:
  - `verify_presigned_url(url, method, headers)`: extracts the signing parameters from the URL's query string. Recomputes the signature using the same algorithm, key, and canonical request. Compares the computed signature against the URL's signature. Validates that the URL has not expired (current time is before generation time plus expiration duration). Validates that the HTTP method matches the signed method. Returns `VerificationResult` with `is_valid`, `principal` (the access key that signed the URL), `expiration`, and `rejection_reason` if invalid

- **`SignatureV4Computer`**: implements AWS Signature Version 4 for request signing:
  - `compute_signing_key(secret_key, date, region, service)`: derives the signing key through a chain of HMAC-SHA256 operations: `HMAC(HMAC(HMAC(HMAC("AWS4" + secret_key, date), region), service), "aws4_request")`
  - `compute_canonical_request(method, path, query_params, headers, signed_headers, payload_hash)`: constructs the canonical request string by normalizing the HTTP method, URI-encoding the path, sorting query parameters, lowercasing and trimming header values, and listing signed headers
  - `compute_string_to_sign(algorithm, datetime, scope, canonical_request_hash)`: constructs the string to sign by combining the algorithm identifier, the request timestamp, the credential scope, and the SHA-256 hash of the canonical request
  - `compute_signature(signing_key, string_to_sign)`: computes the final HMAC-SHA256 signature

---

### 6. Storage Classes

Storage classes provide tiered storage with different performance, availability, and cost characteristics. Objects are assigned a storage class at creation time and can be transitioned between classes by lifecycle policies or explicit API calls.

- **`StorageClass`**: enumeration of available storage classes:
  - `STANDARD`: the default storage class. Designed for frequently accessed data. Provides millisecond-latency access, high throughput, and the highest availability (99.99%). Objects are erasure-coded with a 10:4 data-to-parity ratio (10 data fragments, 4 parity fragments), requiring any 10 of 14 fragments for reconstruction. Storage overhead is 1.4x the object size
  - `STANDARD_IA` (Infrequent Access): designed for data accessed less than once per month but requiring rapid access when needed. Same millisecond-latency access as STANDARD but with lower per-GB storage cost and a per-GB retrieval fee. Minimum object size billing of 128 KB (objects smaller than 128 KB are billed as 128 KB). Minimum storage duration of 30 days (objects deleted or transitioned before 30 days are billed for the full 30-day period). Erasure coded with a 6:4 ratio (6 data, 4 parity), providing the same durability with lower total fragment count
  - `ARCHIVE`: designed for data that is rarely accessed and can tolerate retrieval latency. Objects in ARCHIVE are not immediately accessible -- retrieval requires a restore operation that copies the object to STANDARD storage for a configurable duration. Restore times: Expedited (1-5 minutes), Standard (3-5 hours), Bulk (5-12 hours). Per-GB retrieval fee applies. Minimum storage duration of 90 days. Erasure coded with a 4:4 ratio (4 data, 4 parity), providing 2x storage overhead but extreme durability
  - `DEEP_ARCHIVE`: the lowest-cost storage class, designed for data that is accessed less than once per year. Restore times: Standard (12 hours), Bulk (48 hours). Minimum storage duration of 180 days. Minimum object size billing of 40 KB. Erasure coded with a 2:4 ratio (2 data, 4 parity), providing 3x storage overhead for maximum durability with minimal fragment count on the data side

- **`StorageClassManager`**: manages storage class transitions and retrieval operations:
  - `transition_object(bucket, key, version_id, target_class)`: transitions an object to a different storage class. Validates that the transition is allowed (transitions must follow the waterfall: STANDARD -> STANDARD_IA -> ARCHIVE -> DEEP_ARCHIVE; reverse transitions are not directly supported -- objects must be restored then copied with a new storage class). Re-encodes the object's data fragments with the target class's erasure coding parameters. Updates the object's metadata record. Publishes an `s3:ObjectTransition` event
  - `restore_object(bucket, key, version_id, days, tier)`: initiates an asynchronous restore of an archived object. Creates a temporary copy of the object in STANDARD storage that is accessible for the specified number of days. The `tier` parameter selects the restore speed: `EXPEDITED`, `STANDARD`, or `BULK`. The restore is processed by the `RestoreProcessor` background task. The object's metadata is updated to reflect the restore status (`in-progress` or `completed`) and the expiration date of the restored copy
  - `get_storage_class_stats(bucket)`: returns aggregate statistics for a bucket's storage class distribution: object count and total size per storage class, number of in-progress restores, and number of objects with expired restores pending cleanup

- **`RestoreProcessor`**: processes restore requests asynchronously:
  - Maintains a priority queue of pending restore requests, ordered by tier priority (Expedited > Standard > Bulk) and submission time
  - For each restore request: reads the archived object's erasure-coded fragments from the data tier, decodes them, re-encodes with STANDARD erasure coding parameters, writes the STANDARD-class fragments, and updates the object metadata to mark the restore as complete with the expiration timestamp
  - Monitors restored objects for expiration: when a restore's `days` parameter expires, the restored copy's STANDARD-class fragments are deleted, and the object reverts to its archived state

---

### 7. Lifecycle Policies

Lifecycle policies automate the management of objects over their lifetime: transitioning objects to lower-cost storage classes as they age, expiring objects that are no longer needed, cleaning up incomplete multipart uploads, and managing noncurrent versions in versioned buckets.

- **`LifecycleConfiguration`**: a set of lifecycle rules applied to a bucket:
  - `rules` (List[`LifecycleRule`]): up to 1,000 rules per bucket. Each rule has:
    - `id` (str): unique identifier for the rule within the configuration
    - `status` (`RuleStatus`): `ENABLED` or `DISABLED`. Disabled rules are retained in the configuration but not evaluated
    - `filter` (`RuleFilter`): determines which objects the rule applies to. Filters can match by:
      - `prefix` (str): object key prefix (e.g., `logs/` matches all objects under the `logs/` prefix)
      - `tags` (Dict[str, str]): object tags (all specified tags must be present on the object)
      - `object_size_greater_than` (int): minimum object size in bytes
      - `object_size_less_than` (int): maximum object size in bytes
      - `and` (combines prefix, tags, and size filters with logical AND)
    - `transitions` (List[`TransitionRule`]): rules for transitioning objects to different storage classes:
      - `days` (int): number of days after object creation to trigger the transition
      - `date` (Optional[datetime]): specific date on which to trigger the transition (alternative to `days`)
      - `storage_class` (`StorageClass`): the target storage class
    - `expiration` (Optional[`ExpirationRule`]): rule for permanently deleting objects:
      - `days` (int): number of days after creation to delete the object
      - `date` (Optional[datetime]): specific date on which to delete
      - `expired_object_delete_marker` (bool): if `True`, removes delete markers where the object has no non-delete-marker versions remaining (cleanup of orphaned delete markers in versioned buckets)
    - `noncurrent_version_transitions` (List[`NoncurrentVersionTransitionRule`]): rules for transitioning noncurrent versions:
      - `noncurrent_days` (int): number of days after a version becomes noncurrent to trigger transition
      - `storage_class` (`StorageClass`): target storage class
      - `newer_noncurrent_versions` (Optional[int]): number of newer noncurrent versions to retain before transitioning
    - `noncurrent_version_expiration` (Optional[`NoncurrentVersionExpirationRule`]): rule for permanently deleting noncurrent versions:
      - `noncurrent_days` (int): number of days after a version becomes noncurrent to delete it
      - `newer_noncurrent_versions` (Optional[int]): number of newer noncurrent versions to retain before deleting
    - `abort_incomplete_multipart_upload` (Optional[`AbortIncompleteMultipartUploadRule`]): rule for aborting stale multipart uploads:
      - `days_after_initiation` (int): number of days after upload initiation to abort

- **`LifecycleEvaluator`**: evaluates lifecycle rules against objects:
  - `evaluate(bucket)`: scans all objects in the bucket, evaluates each object against all enabled rules, and returns a list of `LifecycleAction` instances representing the operations to perform. Actions are deduplicated and prioritized: expiration takes precedence over transition, transitions to lower-cost classes take precedence over higher-cost classes. Noncurrent version rules are evaluated against the version chain, not individual versions
  - `apply_actions(actions)`: executes the lifecycle actions in batch. Transitions are performed via `StorageClassManager.transition_object()`. Expirations are performed via `ObjectStore.delete_object()` (with version ID for noncurrent version expiration, without for current object expiration). Multipart upload abortions are performed via `MultipartUploadManager.abort_multipart_upload()`. Each action is logged to the server access log with action type, object key, and rule ID

- **`LifecycleDaemon`**: background process that runs lifecycle evaluation on a configurable schedule:
  - Default evaluation interval: every 24 hours (midnight UTC)
  - Evaluates all buckets with lifecycle configurations
  - Processes actions in batches to limit resource consumption
  - Reports metrics: objects transitioned (count, total bytes), objects expired (count, total bytes), multipart uploads aborted (count), evaluation duration

---

### 8. Cross-Region Replication

Cross-region replication continuously copies objects from a source bucket to one or more destination buckets in different regions, providing geographic redundancy, data locality, and disaster recovery.

- **`ReplicationConfiguration`**: defines replication rules for a source bucket:
  - `role` (str): the IAM role assumed by the replication engine when writing to the destination bucket
  - `rules` (List[`ReplicationRule`]): up to 1,000 replication rules. Each rule has:
    - `id` (str): unique identifier
    - `status` (`RuleStatus`): `ENABLED` or `DISABLED`
    - `priority` (int): rule evaluation priority (higher number = higher priority). When multiple rules match an object, the highest-priority rule wins
    - `filter` (`ReplicationFilter`): determines which objects are replicated. Same filter semantics as lifecycle rules (prefix, tags, size)
    - `destination` (`ReplicationDestination`):
      - `bucket` (str): the destination bucket name
      - `region` (str): the destination region
      - `storage_class` (Optional[`StorageClass`]): override the storage class in the destination (defaults to the source object's storage class)
      - `encryption_configuration` (Optional[`EncryptionConfiguration`]): override encryption in the destination
      - `replica_modifications` (bool): whether to replicate metadata modifications (tag changes, ACL changes) in addition to new object versions
    - `delete_marker_replication` (bool): whether to replicate delete markers. If `False`, deletes in the source bucket are not propagated to the destination -- the destination retains the object even after it is deleted in the source. Default: `False`
    - `source_selection_criteria` (`SourceSelectionCriteria`):
      - `replica_modifications_enabled` (bool): replicate changes made by other replication rules
      - `sse_kms_encrypted_objects_enabled` (bool): replicate objects encrypted with KMS keys (requires additional key policy configuration)

- **`ReplicationEngine`**: processes replication asynchronously:
  - `replicate_object(source_bucket, source_key, source_version_id, rule)`: copies an object from the source to the destination. Reads the source object's data and metadata. Applies any destination overrides (storage class, encryption). Writes the object to the destination bucket using `ObjectStore.put_object()`. Records the replication status on the source object's metadata: `COMPLETED`, `FAILED`, or `REPLICA` (for objects that are themselves replicas)
  - `replicate_delete_marker(source_bucket, source_key, source_version_id, rule)`: if `delete_marker_replication` is enabled for the rule, copies the delete marker to the destination bucket. The destination receives a delete marker with the same version ID as the source
  - `get_replication_status(bucket, key, version_id)`: returns the replication status for a specific object version: `PENDING` (queued for replication), `COMPLETED` (successfully replicated), `FAILED` (replication failed, will be retried), or `REPLICA` (this object is a replica, not a source)

- **`ReplicationQueue`**: ordered queue of pending replication operations:
  - New object versions matching replication rules are enqueued immediately upon successful PUT
  - Failed replications are re-enqueued with exponential backoff (initial delay 1 minute, maximum delay 1 hour, maximum retries 24)
  - Queue is persisted to the WAL to survive process restarts

- **`ReplicationConflictResolver`**: handles conflicts when bidirectional replication is configured (bucket A replicates to bucket B and bucket B replicates to bucket A):
  - **Last-writer-wins**: compares `last_modified` timestamps. The object with the later timestamp wins. Ties are broken by lexicographic comparison of version IDs
  - **Replication loop detection**: each replicated object carries an `x-fizz-replication-source` metadata entry recording the source bucket and region. If a replication engine encounters an object whose replication source matches the current bucket, it skips replication to prevent infinite loops

- **`ReplicationMetrics`**: tracks replication health:
  - `replication_latency` (per-rule): time between object creation in source and completion of replication to destination
  - `bytes_pending` (per-rule): total bytes of objects waiting to be replicated
  - `operations_failed` (per-rule): count of failed replication attempts
  - `operations_completed` (per-rule): count of successful replications

---

### 9. Server-Side Encryption

Server-side encryption protects data at rest by encrypting object content before writing it to the data tier and decrypting it when reading. FizzS3 supports three encryption modes matching the S3 encryption model.

- **`ServerSideEncryption`**: encryption metadata attached to each encrypted object:
  - `algorithm` (`EncryptionAlgorithm`): the encryption algorithm, always `AES-256` (AES-256-GCM for authenticated encryption)
  - `mode` (`EncryptionMode`): one of `SSE_S3`, `SSE_KMS`, `SSE_C`
  - `kms_key_id` (Optional[str]): for SSE-KMS, the FizzVault key ID used for encryption
  - `key_md5` (Optional[str]): for SSE-C, the Base64-encoded MD5 of the client-provided key (used for verification, not stored)

- **`EncryptionEngine`**: handles encryption and decryption of object data:
  - **SSE-S3** (FizzS3-managed keys): the simplest encryption mode. FizzS3 generates a unique 256-bit data encryption key (DEK) for each object. The DEK encrypts the object data using AES-256-GCM. The DEK is then encrypted (wrapped) with a master key managed internally by FizzS3 and stored alongside the object's metadata. Key rotation is automatic: when the master key is rotated, existing objects are not re-encrypted (envelope encryption ensures that only the DEK wrapper needs to change, and this happens lazily on next access or proactively via a background key rotation job)
  - **SSE-KMS** (FizzVault-managed keys): provides key management through FizzVault's key management service. The caller specifies a FizzVault key ID (or uses the default FizzS3 service key). FizzS3 requests a data key from FizzVault, which returns both a plaintext DEK and a ciphertext DEK (the plaintext encrypted with the KMS key). The plaintext DEK encrypts the object data. The ciphertext DEK is stored in the object's metadata. On read, FizzS3 sends the ciphertext DEK to FizzVault for decryption, then uses the plaintext DEK to decrypt the object data. This provides centralized key management, auditable key usage, and the ability to disable access by revoking the KMS key
  - **SSE-C** (client-provided keys): the caller provides a 256-bit encryption key in the request headers. FizzS3 uses the key to encrypt the object data, stores the MD5 of the key (for verification), and discards the key. On read, the caller must provide the same key. If the key MD5 does not match, the request is rejected. FizzS3 never stores or logs client-provided keys. This mode is for callers who require exclusive control over their encryption keys

- **`EncryptionConfiguration`**: bucket-level default encryption settings:
  - `default_encryption` (`EncryptionMode`): the encryption mode applied to objects that do not specify encryption in the PUT request. Default: `SSE_S3`
  - `kms_key_id` (Optional[str]): for SSE-KMS default encryption, the FizzVault key ID
  - `bucket_key_enabled` (bool): when `True` with SSE-KMS, uses a bucket-level key derived from the KMS key for encrypting DEKs, reducing the number of KMS API calls. The bucket key is valid for a configurable duration (default: 24 hours) before re-derivation

- **`KeyRotationManager`**: manages encryption key rotation:
  - `rotate_master_key()`: generates a new SSE-S3 master key. New objects use the new master key for DEK wrapping. Existing objects retain their current DEK wrappers until re-encrypted
  - `re_encrypt_objects(bucket, prefix)`: proactively re-encrypts objects by unwrapping their DEKs with the old master key and re-wrapping with the current master key. This is a background operation that processes objects in batches
  - `rotation_schedule`: configurable automatic rotation interval (default: 90 days)

---

### 10. Access Control

FizzS3 implements a multi-layer access control model matching S3's authorization logic: bucket policies, access control lists (ACLs), and block public access settings. Authorization decisions evaluate all three layers and apply the most restrictive result.

- **`BucketPolicy`**: IAM-style policy document for bucket-level access control:
  - `version` (str): policy language version, always `"2012-10-17"` (matching the IAM policy language version)
  - `statements` (List[`PolicyStatement`]): one or more policy statements:
    - `sid` (Optional[str]): statement identifier for documentation
    - `effect` (`PolicyEffect`): `ALLOW` or `DENY`
    - `principal` (`PolicyPrincipal`): the entity the statement applies to. Can be `*` (anyone), a specific principal identifier, or a list of principals
    - `action` (List[str]): S3 actions the statement governs (e.g., `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject`, `s3:ListBucket`, `s3:*`)
    - `resource` (List[str]): ARN patterns specifying which resources the statement applies to (e.g., `arn:fizz:s3:::my-bucket/*` for all objects in a bucket, `arn:fizz:s3:::my-bucket` for the bucket itself)
    - `condition` (Optional[Dict]): condition operators for fine-grained access control:
      - `StringEquals` / `StringNotEquals` / `StringLike` / `StringNotLike`: string comparison on request context values
      - `IpAddress` / `NotIpAddress`: source IP comparison
      - `DateGreaterThan` / `DateLessThan`: temporal access windows
      - Condition keys: `aws:SourceIp`, `aws:CurrentTime`, `aws:SecureTransport`, `s3:prefix`, `s3:max-keys`, `s3:x-amz-content-sha256`, `s3:x-amz-storage-class`

- **`AccessControlList`**: legacy ACL-based access control:
  - `owner` (`Owner`): the bucket or object owner (principal ID and display name)
  - `grants` (List[`Grant`]): access grants:
    - `grantee` (`Grantee`): the recipient of the grant. Can be a canonical user (by principal ID), an email address, or a predefined group (`AllUsers` for public access, `AuthenticatedUsers` for any authenticated principal, `LogDelivery` for access log delivery)
    - `permission` (`ACLPermission`): one of `FULL_CONTROL`, `READ`, `WRITE`, `READ_ACP` (read the ACL), `WRITE_ACP` (modify the ACL)
  - **Canned ACLs**: predefined ACL configurations applied at bucket or object creation:
    - `private`: owner gets `FULL_CONTROL`, no other grants (default)
    - `public-read`: owner gets `FULL_CONTROL`, `AllUsers` gets `READ`
    - `public-read-write`: owner gets `FULL_CONTROL`, `AllUsers` gets `READ` and `WRITE`
    - `authenticated-read`: owner gets `FULL_CONTROL`, `AuthenticatedUsers` gets `READ`
    - `bucket-owner-read`: object owner gets `FULL_CONTROL`, bucket owner gets `READ` (for cross-account object uploads)
    - `bucket-owner-full-control`: both object owner and bucket owner get `FULL_CONTROL`

- **`BlockPublicAccessConfiguration`**: four independent settings that override bucket policies and ACLs to prevent public access:
  - `block_public_acls` (bool): rejects PUT requests that include a public ACL (ACLs granting access to `AllUsers` or `AuthenticatedUsers`)
  - `ignore_public_acls` (bool): ignores any existing public ACLs on the bucket or its objects -- even if a public ACL is present, it is not evaluated during authorization
  - `block_public_policy` (bool): rejects PUT bucket policy requests that would make the bucket publicly accessible
  - `restrict_public_buckets` (bool): restricts access to publicly accessible buckets to authorized principals only (effectively overrides public policies for cross-account access)

- **`AccessControlEvaluator`**: evaluates authorization for incoming requests:
  - `evaluate(principal, action, resource, context)`: implements the S3 authorization algorithm:
    1. Check block public access settings. If the request would be granted by a public ACL or policy and block public access is active, deny
    2. Evaluate all applicable bucket policy statements. Collect all `DENY` and `ALLOW` results
    3. Evaluate the ACL grants for the requested permission
    4. Apply the authorization logic: explicit DENY in any layer -> deny. No explicit ALLOW in any layer -> deny. Explicit ALLOW with no explicit DENY -> allow
    5. Return `AuthorizationResult` with `allowed` (bool), `reason` (str), and `evaluated_policies` (list of policy/ACL entries that contributed to the decision)

---

### 11. Event Notifications

Event notifications publish messages to subscribers when specific operations occur on objects within a bucket. This enables event-driven architectures where downstream processing is triggered by storage events rather than polling.

- **`NotificationConfiguration`**: defines event notification rules for a bucket:
  - `event_rules` (List[`EventRule`]): notification rules, each containing:
    - `id` (str): unique identifier for the rule
    - `events` (List[`S3EventType`]): the event types that trigger notification:
      - `s3:ObjectCreated:*`: any object creation (PUT, POST, COPY, CompleteMultipartUpload)
      - `s3:ObjectCreated:Put`: object created via PUT
      - `s3:ObjectCreated:Post`: object created via POST (presigned POST)
      - `s3:ObjectCreated:Copy`: object created via COPY
      - `s3:ObjectCreated:CompleteMultipartUpload`: object created via multipart upload completion
      - `s3:ObjectRemoved:*`: any object removal
      - `s3:ObjectRemoved:Delete`: object permanently deleted
      - `s3:ObjectRemoved:DeleteMarkerCreated`: delete marker created in versioned bucket
      - `s3:ObjectRestore:Post`: restore initiated for archived object
      - `s3:ObjectRestore:Completed`: restore completed for archived object
      - `s3:ObjectTransition`: object transitioned between storage classes by lifecycle policy
      - `s3:Replication:*`: replication events
      - `s3:Replication:OperationCompleted`: object successfully replicated
      - `s3:Replication:OperationFailed`: replication failed
      - `s3:LifecycleExpiration:*`: lifecycle expiration events
      - `s3:LifecycleExpiration:Delete`: object expired by lifecycle policy
      - `s3:LifecycleExpiration:DeleteMarkerCreated`: lifecycle created a delete marker for expired object
    - `filter` (`NotificationFilter`): determines which objects trigger notifications:
      - `key_filter` (`KeyFilter`): filter by object key using `prefix` and/or `suffix` rules (e.g., prefix `images/`, suffix `.png` -- triggers only for PNG files under the images prefix)
    - `destination` (`NotificationDestination`): where to publish the notification:
      - `type` (`DestinationType`): `EVENT_BUS` (FizzEventBus), `WEBHOOK` (FizzWebhook), `QUEUE` (internal notification queue for polling consumers)
      - `target_id` (str): the destination identifier (event bus topic, webhook URL, or queue name)

- **`S3EventMessage`**: the notification payload published for each event:
  - `event_version` (str): message format version, `"2.1"`
  - `event_source` (str): always `"fizz:s3"`
  - `event_time` (datetime): when the event occurred
  - `event_name` (str): the event type (e.g., `"s3:ObjectCreated:Put"`)
  - `bucket` (`EventBucket`): bucket name, owner, and ARN
  - `object` (`EventObject`): key, size, ETag, version ID, and sequencer (monotonically increasing per-key sequence number for ordering)
  - `request_parameters` (Dict): source IP, request ID
  - `response_elements` (Dict): request ID, host ID
  - `user_identity` (Dict): principal type and principal ID of the requester

- **`NotificationDispatcher`**: processes and dispatches event notifications:
  - Maintains an in-memory buffer of pending notifications
  - Evaluates each object operation against the bucket's notification configuration
  - Matches event type and key filter against each rule
  - For matching rules, constructs the `S3EventMessage` and dispatches to the configured destination
  - Dispatching is asynchronous and non-blocking -- notification failures do not affect the success of the storage operation that triggered them
  - Failed dispatches are retried with exponential backoff (3 attempts, initial delay 1 second, maximum delay 30 seconds)
  - Dead-letter queue for notifications that fail all retry attempts

---

### 12. Content-Addressable Deduplication

Content-addressable storage assigns each unique data chunk a storage address derived from its content hash. Identical chunks stored by different objects share the same physical storage, eliminating redundant data and reducing storage consumption.

- **`ContentAddressableStore`**: the core deduplication engine:
  - `chunk_object(data, chunk_size)`: splits object data into fixed-size chunks (default chunk size: 4 MB, configurable per storage class). The last chunk may be smaller than the chunk size. Returns a list of `Chunk` objects, each containing the chunk data and its position in the original object
  - `address_chunk(chunk)`: computes the content address for a chunk using SHA-256 hash of the chunk data. The 256-bit hash serves as both the unique identifier and the storage address for the chunk. Identical data always produces the same address regardless of which object, bucket, or region it belongs to
  - `store_chunk(address, data)`: stores a chunk at its content address. If a chunk with this address already exists in the data tier, the store is a no-op -- the chunk data is not written again. The reference count for the address is incremented. Returns `StoreResult` indicating whether the chunk was newly stored (`CREATED`) or already existed (`DEDUPLICATED`)
  - `retrieve_chunk(address)`: reads a chunk from its content address. Locates the erasure-coded fragments for this address, decodes them, and returns the chunk data. Raises `ChunkNotFoundError` if no chunk exists at the address (should not occur in normal operation -- indicates a reference integrity violation)
  - `delete_chunk_reference(address, object_id)`: decrements the reference count for a content address from the specified object. When the reference count reaches zero, the chunk data and its erasure-coded fragments are eligible for garbage collection
  - `get_deduplication_stats(bucket)`: returns deduplication metrics for a bucket:
    - `logical_size`: total size of all objects (sum of object sizes, counting each object's full size even if its chunks are shared)
    - `physical_size`: actual storage consumed (sum of unique chunk sizes, counting each deduplicated chunk once)
    - `deduplication_ratio`: `logical_size / physical_size` (ratio > 1 indicates deduplication savings)
    - `shared_chunks`: number of chunks referenced by more than one object
    - `unique_chunks`: number of chunks referenced by exactly one object

- **`ChunkManifest`**: maps an object to its content-addressed chunks:
  - `object_id` (str): composite identifier of bucket, key, and version ID
  - `chunks` (List[`ChunkReference`]): ordered list of chunk references:
    - `address` (str): SHA-256 content address
    - `offset` (int): byte offset of this chunk within the original object
    - `size` (int): chunk size in bytes
    - `sequence` (int): chunk sequence number (0-indexed)
  - `total_size` (int): total object size (sum of chunk sizes)
  - `chunk_count` (int): number of chunks

- **`ReferenceCounter`**: tracks the number of object references to each content address:
  - `increment(address, object_id)`: adds a reference from the specified object to the content address. If this is the first reference, initializes the counter to 1. Otherwise increments it
  - `decrement(address, object_id)`: removes a reference from the specified object. Decrements the counter. Returns the new count. If the count reaches zero, the address is added to the garbage collection candidate set
  - `get_count(address)`: returns the current reference count for a content address
  - Reference counts are stored in the metadata tier and protected by WAL transactions to prevent count corruption during crashes

- **`GarbageCollector`**: reclaims storage from unreferenced content-addressed chunks:
  - `collect()`: scans the garbage collection candidate set (addresses with zero references). For each candidate, verifies the reference count is still zero (guards against race conditions where a new reference was added after the candidate was identified). If confirmed zero, deletes the chunk's erasure-coded fragments from the data tier and removes the chunk metadata record. Records the reclaimed space
  - `schedule`: runs on a configurable interval (default: every 6 hours)
  - `safety_delay`: chunks are not collected until they have been unreferenced for a configurable duration (default: 24 hours), preventing collection of chunks that are in the process of being referenced by an in-flight PUT operation

---

### 13. Erasure Coding

Erasure coding provides durability by encoding each data chunk into a set of fragments (data fragments and parity fragments) such that the original data can be reconstructed from any subset of fragments whose count equals or exceeds the number of data fragments. This is more storage-efficient than replication while providing higher durability.

- **`ErasureCodingEngine`**: implements Reed-Solomon erasure coding:
  - `encode(data, data_fragments, parity_fragments)`: encodes a data chunk into `data_fragments + parity_fragments` fragments using Reed-Solomon coding over GF(2^8) (Galois Field with 256 elements). The encoding process:
    1. Pads the data to be evenly divisible by `data_fragments`
    2. Splits the padded data into `data_fragments` equal-sized shards
    3. Constructs a Vandermonde encoding matrix of size `(data_fragments + parity_fragments) x data_fragments`
    4. Multiplies each column of the data matrix by the encoding matrix to produce `data_fragments + parity_fragments` fragment shards
    5. The first `data_fragments` fragments are identical to the original data shards (systematic encoding). The remaining `parity_fragments` are parity shards computed from the Vandermonde matrix multiplication
    6. Returns a list of `Fragment` objects, each containing the fragment data, fragment index, and the coding parameters
  - `decode(fragments, data_fragments, parity_fragments)`: reconstructs the original data from any `data_fragments` or more fragments (out of the total `data_fragments + parity_fragments`). The decoding process:
    1. Selects `data_fragments` available fragments (preferring data fragments over parity fragments to minimize computation)
    2. Constructs the sub-matrix of the encoding matrix corresponding to the selected fragment indices
    3. Inverts the sub-matrix using Gaussian elimination over GF(2^8)
    4. Multiplies the inverted sub-matrix by the selected fragments to reconstruct the original data shards
    5. Concatenates the data shards and removes padding
    6. Returns the original data bytes
  - `verify_fragments(fragments, data_fragments, parity_fragments)`: verifies that a set of fragments is consistent (no corruption) by encoding the data fragments and comparing the computed parity against the stored parity. Returns a list of fragment indices whose data does not match the expected values

- **`GaloisField`**: arithmetic operations over GF(2^8) for Reed-Solomon coding:
  - `add(a, b)`: addition in GF(2^8), implemented as XOR
  - `multiply(a, b)`: multiplication in GF(2^8), implemented via log/antilog tables with the irreducible polynomial x^8 + x^4 + x^3 + x^2 + 1 (0x11D)
  - `divide(a, b)`: division in GF(2^8), implemented as multiplication by the multiplicative inverse
  - `inverse(a)`: multiplicative inverse in GF(2^8), computed via the log/antilog tables
  - `exp_table` and `log_table`: precomputed lookup tables (256 entries each) for fast multiplication and division. Generated at module load time by iterating the generator element

- **`VandermondeMatrix`**: constructs and operates on Vandermonde matrices for Reed-Solomon encoding:
  - `build(rows, cols)`: constructs a Vandermonde matrix where element (i, j) = i^j in GF(2^8). The first `cols` rows form an identity matrix (systematic encoding). The remaining rows are the parity generation rows
  - `invert_submatrix(indices)`: extracts the submatrix corresponding to the given row indices and computes its inverse using Gaussian elimination over GF(2^8). Used during decoding to reconstruct data from an arbitrary subset of fragments
  - `multiply_vector(matrix, vector)`: matrix-vector multiplication over GF(2^8)

- **`FragmentDistributor`**: distributes erasure-coded fragments across independent failure domains:
  - `distribute(fragments, fragment_locations)`: assigns each fragment to a storage location (in-memory storage node simulation). Fragments from the same chunk are distributed across different locations to ensure that a single location failure does not destroy more fragments than the parity count can recover
  - `collect(chunk_address, required_count)`: collects fragments for a chunk from their storage locations. Returns at least `required_count` fragments (the data fragment count). If some locations are unavailable, collects fragments from available locations. If fewer than `required_count` fragments are available, raises `InsufficientFragmentsError` (data loss has occurred)

- **`FragmentIntegrityChecker`**: monitors fragment health:
  - `check_chunk(chunk_address)`: retrieves all fragments for a chunk and verifies their consistency using `ErasureCodingEngine.verify_fragments()`. Reports any corrupt or missing fragments
  - `repair_chunk(chunk_address, corrupt_indices)`: reconstructs corrupt or missing fragments by decoding the available healthy fragments and re-encoding to produce replacement fragments. Writes the replacement fragments to their storage locations
  - `scrub(bucket)`: performs a full integrity scan of all chunks in a bucket. Identifies and repairs corrupt or missing fragments. Reports scrub results: chunks scanned, fragments verified, corruptions detected, repairs performed

---

### 14. Metadata Index

The metadata tier provides fast lookup of bucket configurations, object metadata, version histories, and access control policies. It uses a B-tree index for range queries (prefix listing, version chain enumeration) and a hash index for point lookups (get object by key, get bucket by name).

- **`MetadataIndex`**: the metadata storage engine:
  - `BTreeIndex`: a B-tree supporting ordered key traversal for range queries. Used for:
    - Object listing with prefix filter: find all keys in a bucket that start with a given prefix
    - Version chain enumeration: find all versions of a given key in reverse chronological order
    - Lifecycle evaluation: scan all objects in a bucket ordered by creation date
  - `HashIndex`: a hash table for O(1) point lookups. Used for:
    - Get bucket by name
    - Get object by (bucket, key, version_id) tuple
    - Get chunk by content address
    - Get multipart upload by upload ID
  - `put(key, value, index_type)`: inserts or updates a metadata record in the specified index. Writes are WAL-protected: the record is first written to the write-ahead log, then applied to the in-memory index, then flushed to persistent storage on the next checkpoint
  - `get(key, index_type)`: retrieves a metadata record by key from the specified index
  - `delete(key, index_type)`: removes a metadata record from the specified index. WAL-protected
  - `range_query(start_key, end_key, limit, index_type)`: returns metadata records whose keys fall within the specified range (inclusive start, exclusive end), ordered by key, limited to `limit` results. Only supported on BTreeIndex
  - `prefix_query(prefix, limit, continuation_token)`: returns metadata records whose keys start with the specified prefix, supporting pagination via continuation tokens. Implemented as a range query from `prefix` to `prefix + \xff`

- **`MetadataRecord`**: a generic metadata record:
  - `record_type` (`RecordType`): `BUCKET`, `OBJECT`, `VERSION`, `MULTIPART_UPLOAD`, `PART`, `CHUNK`, `LIFECYCLE_RULE`, `REPLICATION_RULE`, `NOTIFICATION_RULE`
  - `primary_key` (str): the record's primary key in the index
  - `data` (Dict): the record's data fields, serialized to JSON for storage
  - `created_at` (datetime): record creation timestamp
  - `updated_at` (datetime): last update timestamp

- **`MetadataCheckpointer`**: periodically flushes the in-memory metadata index to persistent storage:
  - `checkpoint_interval`: configurable interval (default: every 60 seconds)
  - `checkpoint()`: writes the current state of the in-memory index to the persistent store (FizzVFS file). The checkpoint is atomic: a new file is written, then renamed to replace the previous checkpoint. If the process crashes between checkpoints, the WAL is replayed from the last checkpoint to recover the in-memory state

---

### 15. Data Tier Storage Engine

The data tier stores object content as erasure-coded fragments in an append-only segment log. Segments are immutable once sealed, enabling efficient sequential writes and simplified garbage collection.

- **`SegmentLog`**: the append-only storage backend:
  - `active_segment` (`Segment`): the currently open segment accepting writes. When the active segment reaches the maximum segment size (default: 256 MB), it is sealed and a new active segment is opened
  - `sealed_segments` (List[`Segment`]): previously sealed segments, indexed by segment ID
  - `append(fragment_address, fragment_data)`: appends a fragment to the active segment. Records the fragment's offset and length in the segment index. Returns the `FragmentLocation` (segment ID, offset, length)
  - `read(location)`: reads a fragment from a sealed or active segment using the segment ID, offset, and length from the `FragmentLocation`
  - `seal_segment(segment)`: marks a segment as immutable. No further writes are accepted. The segment's index is finalized and written to the segment footer
  - `compact(segment_ids)`: compacts multiple sealed segments into a new segment by copying live fragments (those with non-zero reference counts) and discarding dead fragments (those with zero reference counts). This reclaims space from garbage-collected chunks. The old segments are deleted after compaction completes and all fragment location references have been updated

- **`Segment`**: a single segment file in the log:
  - `segment_id` (str): unique identifier, based on creation timestamp
  - `header` (`SegmentHeader`): segment metadata (version, creation time, status)
  - `index` (Dict[str, `FragmentEntry`]): maps fragment addresses to their offset and length within the segment
  - `data` (bytes): the raw segment data (concatenated fragment payloads)
  - `status` (`SegmentStatus`): `ACTIVE` (open for writes), `SEALED` (immutable), `COMPACTING` (being compacted), `DELETED` (marked for removal)
  - `size` (int): current size of the segment data in bytes
  - `live_bytes` (int): bytes occupied by live (referenced) fragments
  - `dead_bytes` (int): bytes occupied by dead (unreferenced) fragments
  - `fragmentation_ratio`: `dead_bytes / size` (ratio of wasted space, triggers compaction when above threshold)

- **`CompactionPolicy`**: determines when and which segments to compact:
  - `fragmentation_threshold` (float): compact segments whose fragmentation ratio exceeds this threshold (default: 0.5 = 50% dead space)
  - `min_segment_age` (timedelta): do not compact segments newer than this age (default: 1 hour), allowing recent writes to stabilize before compaction
  - `max_compaction_concurrency` (int): maximum number of segments being compacted simultaneously (default: 2)
  - `select_segments()`: returns a list of segments eligible for compaction, ordered by fragmentation ratio (most fragmented first)

---

### 16. S3 REST API Layer

The API layer translates S3-compatible HTTP requests into FizzS3 storage operations and formats responses according to the S3 API specification.

- **`S3RequestRouter`**: routes incoming requests to the appropriate handler based on HTTP method, path, and query parameters:
  - `route(request)`: parses the request to determine the operation:
    - `GET /` -> `ListBuckets`
    - `PUT /{bucket}` -> `CreateBucket`
    - `DELETE /{bucket}` -> `DeleteBucket`
    - `HEAD /{bucket}` -> `HeadBucket`
    - `GET /{bucket}?location` -> `GetBucketLocation`
    - `GET /{bucket}?versioning` -> `GetBucketVersioning`
    - `PUT /{bucket}?versioning` -> `PutBucketVersioning`
    - `GET /{bucket}?lifecycle` -> `GetBucketLifecycle`
    - `PUT /{bucket}?lifecycle` -> `PutBucketLifecycle`
    - `GET /{bucket}?replication` -> `GetBucketReplication`
    - `PUT /{bucket}?replication` -> `PutBucketReplication`
    - `GET /{bucket}?notification` -> `GetBucketNotification`
    - `PUT /{bucket}?notification` -> `PutBucketNotification`
    - `GET /{bucket}?policy` -> `GetBucketPolicy`
    - `PUT /{bucket}?policy` -> `PutBucketPolicy`
    - `GET /{bucket}?acl` -> `GetBucketAcl`
    - `PUT /{bucket}?acl` -> `PutBucketAcl`
    - `GET /{bucket}?encryption` -> `GetBucketEncryption`
    - `PUT /{bucket}?encryption` -> `PutBucketEncryption`
    - `GET /{bucket}?list-type=2` -> `ListObjectsV2`
    - `GET /{bucket}?versions` -> `ListObjectVersions`
    - `GET /{bucket}?uploads` -> `ListMultipartUploads`
    - `PUT /{bucket}/{key}` -> `PutObject`
    - `GET /{bucket}/{key}` -> `GetObject`
    - `HEAD /{bucket}/{key}` -> `HeadObject`
    - `DELETE /{bucket}/{key}` -> `DeleteObject`
    - `POST /{bucket}?delete` -> `DeleteObjects` (multi-object delete)
    - `PUT /{bucket}/{key}?copy` -> `CopyObject`
    - `POST /{bucket}/{key}?uploads` -> `CreateMultipartUpload`
    - `PUT /{bucket}/{key}?partNumber={n}&uploadId={id}` -> `UploadPart`
    - `PUT /{bucket}/{key}?partNumber={n}&uploadId={id}&copy` -> `UploadPartCopy`
    - `POST /{bucket}/{key}?uploadId={id}` -> `CompleteMultipartUpload`
    - `DELETE /{bucket}/{key}?uploadId={id}` -> `AbortMultipartUpload`
    - `GET /{bucket}/{key}?uploadId={id}` -> `ListParts`
    - `POST /{bucket}/{key}?restore` -> `RestoreObject`

- **`S3ResponseFormatter`**: formats operation results into S3-compatible HTTP responses:
  - `format_xml_response(operation, result)`: serializes operation results to XML response bodies following the S3 API schema. List operations return XML with element names matching S3 exactly (`<ListBucketResult>`, `<ListVersionsResult>`, `<InitiateMultipartUploadResult>`, etc.)
  - `format_error_response(error_code, message, resource, request_id)`: serializes error responses to S3-compatible XML error format: `<Error><Code>...</Code><Message>...</Message><Resource>...</Resource><RequestId>...</RequestId></Error>`
  - Standard error codes: `NoSuchBucket`, `NoSuchKey`, `NoSuchVersion`, `NoSuchUpload`, `BucketAlreadyExists`, `BucketNotEmpty`, `InvalidBucketName`, `InvalidArgument`, `AccessDenied`, `MalformedXML`, `EntityTooLarge`, `EntityTooSmall`, `InvalidPart`, `InvalidPartOrder`, `MethodNotAllowed`, `PreconditionFailed`, `NotModified`, `InvalidRange`, `InternalError`, `ServiceUnavailable`

- **`S3RequestAuthenticator`**: validates request authentication:
  - Supports Signature Version 4 authentication (Authorization header and query string presigned URL)
  - Validates the signature by recomputing it using the caller's secret key (retrieved from FizzCap's principal store)
  - Validates the request timestamp is within the allowed clock skew (15 minutes)
  - Returns the authenticated principal or raises `AccessDenied` with a specific reason (invalid signature, expired request, unknown access key)

---

### 17. Metrics and Observability

FizzS3 exposes storage-tier metrics through FizzSLI and FizzOTel integration, providing visibility into storage utilization, request patterns, and system health.

- **`S3Metrics`**: storage-tier metrics collector:
  - **Request metrics** (per-bucket, per-operation):
    - `request_count`: total number of API requests
    - `request_latency_ms`: request processing duration (p50, p95, p99)
    - `request_errors`: count of error responses by error code
    - `bytes_uploaded`: total bytes received via PUT and multipart upload
    - `bytes_downloaded`: total bytes served via GET
  - **Storage metrics** (per-bucket, per-storage-class):
    - `object_count`: number of objects
    - `total_size_bytes`: total logical size (before deduplication)
    - `physical_size_bytes`: total physical size (after deduplication and erasure coding)
    - `version_count`: number of object versions (including delete markers)
    - `multipart_upload_count`: number of in-progress multipart uploads
    - `multipart_upload_bytes`: total bytes consumed by in-progress multipart upload parts
  - **Deduplication metrics**:
    - `deduplication_ratio`: logical size / physical size
    - `chunks_total`: total content-addressed chunks
    - `chunks_shared`: chunks referenced by multiple objects
    - `bytes_saved`: logical size - physical size (storage savings from deduplication)
  - **Erasure coding metrics**:
    - `fragments_total`: total erasure-coded fragments across all storage locations
    - `fragments_healthy`: fragments that pass integrity verification
    - `fragments_degraded`: fragments that are corrupt or missing (system is operating on reduced redundancy)
    - `fragments_repaired`: fragments repaired by the integrity checker
    - `scrub_duration_ms`: time taken for the last full integrity scrub
  - **Replication metrics**: (as defined in `ReplicationMetrics` above)
  - **Lifecycle metrics**:
    - `transitions_executed`: objects transitioned between storage classes
    - `expirations_executed`: objects expired by lifecycle rules
    - `bytes_transitioned`: total bytes moved between storage classes
    - `bytes_expired`: total bytes reclaimed by expiration

- **`S3TracingMiddleware`**: integrates with FizzOTel to produce distributed traces for storage operations:
  - Creates a span for each API request with attributes: `s3.bucket`, `s3.key`, `s3.operation`, `s3.request_id`, `s3.response_status`
  - Creates child spans for internal operations: metadata lookup, chunk retrieval, erasure decoding, encryption/decryption, access control evaluation
  - Propagates trace context through cross-region replication requests

---

### 18. FizzS3 Middleware and CLI Integration

- **`FizzS3Middleware`**: integrates FizzS3 with the FizzBuzz evaluation middleware pipeline:
  - On each evaluation request, records the evaluation input, output, and timestamp as an object in the `fizzbuzz-evaluations` bucket with key format `evaluations/{year}/{month}/{day}/{request_id}.json`
  - Enables query-by-prefix listing of historical evaluations by date range
  - Optionally stores evaluation results in ARCHIVE storage class for long-term retention with lifecycle policy transitioning from STANDARD after 30 days

- **`FizzS3CLI`**: command-line interface for FizzS3 operations:
  - `--fizzs3`: enable the FizzS3 object storage subsystem
  - `--fizzs3-create-bucket <name>`: create a new bucket
  - `--fizzs3-delete-bucket <name>`: delete an empty bucket
  - `--fizzs3-list-buckets`: list all buckets
  - `--fizzs3-put <bucket> <key> <file>`: upload a file as an object
  - `--fizzs3-get <bucket> <key>`: retrieve an object and print to stdout
  - `--fizzs3-head <bucket> <key>`: retrieve object metadata
  - `--fizzs3-delete <bucket> <key>`: delete an object
  - `--fizzs3-list <bucket>`: list objects in a bucket (with optional `--prefix` and `--delimiter`)
  - `--fizzs3-list-versions <bucket> <key>`: list all versions of an object
  - `--fizzs3-presign <bucket> <key>`: generate a presigned URL (with `--expires` duration)
  - `--fizzs3-multipart-create <bucket> <key>`: initiate a multipart upload
  - `--fizzs3-multipart-upload <bucket> <key> <upload-id> <part-number> <file>`: upload a part
  - `--fizzs3-multipart-complete <bucket> <key> <upload-id>`: complete a multipart upload
  - `--fizzs3-multipart-abort <bucket> <key> <upload-id>`: abort a multipart upload
  - `--fizzs3-multipart-list <bucket>`: list in-progress multipart uploads
  - `--fizzs3-storage-class <class>`: set the storage class for PUT operations
  - `--fizzs3-versioning <bucket> <enable|suspend>`: enable or suspend versioning
  - `--fizzs3-lifecycle <bucket> <policy.yaml>`: apply a lifecycle policy to a bucket
  - `--fizzs3-replication <bucket> <config.yaml>`: configure cross-region replication
  - `--fizzs3-encryption <bucket> <mode>`: set default encryption (sse-s3, sse-kms, sse-c)
  - `--fizzs3-policy <bucket> <policy.json>`: apply a bucket policy
  - `--fizzs3-acl <bucket> <acl>`: set bucket ACL (private, public-read, etc.)
  - `--fizzs3-block-public-access <bucket>`: configure block public access settings
  - `--fizzs3-notifications <bucket> <config.yaml>`: configure event notifications
  - `--fizzs3-dedup-stats <bucket>`: show deduplication statistics
  - `--fizzs3-scrub <bucket>`: run erasure coding integrity scrub
  - `--fizzs3-metrics`: show storage metrics summary
  - `--fizzs3-region <region>`: set the region for operations (default: `fizz-east-1`)

---

### 19. Exception Hierarchy

FizzS3 defines a comprehensive exception hierarchy for precise error handling and S3-compatible error code mapping:

- **`FizzS3Error`**: base exception for all FizzS3 errors
  - **`BucketError`**: base for bucket-related errors
    - `BucketAlreadyExistsError`: bucket name is already in use globally
    - `BucketAlreadyOwnedByYouError`: caller already owns a bucket with this name
    - `BucketNotEmptyError`: attempt to delete a bucket that contains objects
    - `BucketNotFoundError`: the specified bucket does not exist
    - `InvalidBucketNameError`: bucket name violates naming rules
    - `TooManyBucketsError`: maximum bucket count exceeded (default: 100 per owner)
  - **`ObjectError`**: base for object-related errors
    - `ObjectNotFoundError`: the specified key does not exist (or has a delete marker as current version)
    - `ObjectTooLargeError`: object exceeds the maximum size for single-part upload (5 GiB)
    - `InvalidObjectKeyError`: key exceeds maximum length or contains invalid characters
    - `PreconditionFailedError`: conditional request precondition not met (If-Match/If-Unmodified-Since)
    - `NotModifiedError`: conditional request indicates no modification (If-None-Match/If-Modified-Since)
    - `InvalidRangeError`: byte range request specifies a range outside the object's size
  - **`VersionError`**: base for versioning errors
    - `NoSuchVersionError`: the specified version ID does not exist
    - `VersioningNotEnabledError`: version-specific operation on an unversioned bucket
    - `InvalidVersionIdError`: malformed version ID
  - **`MultipartUploadError`**: base for multipart upload errors
    - `NoSuchUploadError`: the specified upload ID does not exist or has been completed/aborted
    - `InvalidPartError`: a specified part does not exist or its ETag does not match
    - `InvalidPartOrderError`: parts are not in ascending order in the completion request
    - `EntityTooSmallError`: a part (other than the last) is smaller than the minimum part size (5 MB)
    - `EntityTooLargeError`: a part exceeds the maximum part size (5 GiB)
    - `TooManyPartsError`: part number exceeds the maximum (10,000)
  - **`AccessControlError`**: base for authorization errors
    - `AccessDeniedError`: the caller does not have permission for the requested operation
    - `InvalidPolicyError`: the bucket policy document is malformed or invalid
    - `MalformedACLError`: the ACL document is malformed
    - `PublicAccessBlockedError`: the operation would grant public access but block public access is enabled
  - **`EncryptionError`**: base for encryption errors
    - `InvalidEncryptionKeyError`: client-provided key (SSE-C) is invalid or does not match
    - `KMSKeyNotFoundError`: the specified FizzVault key ID does not exist
    - `KMSAccessDeniedError`: the caller does not have permission to use the specified KMS key
    - `KeyRotationInProgressError`: a key rotation is in progress and the operation cannot proceed
  - **`ReplicationError`**: base for replication errors
    - `ReplicationConfigurationError`: invalid replication configuration
    - `ReplicationFailedError`: object replication to the destination bucket failed
    - `ReplicationLoopDetectedError`: bidirectional replication loop detected
  - **`StorageClassError`**: base for storage class errors
    - `InvalidStorageClassTransitionError`: attempted transition violates the storage class waterfall
    - `RestoreInProgressError`: a restore is already in progress for this object
    - `ObjectNotArchivedError`: restore requested for an object that is not in ARCHIVE or DEEP_ARCHIVE
    - `RestoreExpiredError`: the restored copy has expired and the object is archived again
  - **`ErasureCodingError`**: base for erasure coding errors
    - `InsufficientFragmentsError`: not enough fragments available to reconstruct the data (data loss)
    - `FragmentCorruptionError`: a fragment's data does not match its expected content address
    - `FragmentLocationUnavailableError`: a storage location is unreachable
  - **`ContentAddressError`**: base for deduplication errors
    - `ChunkNotFoundError`: a content-addressed chunk does not exist at the expected address
    - `ReferenceIntegrityError`: reference count is inconsistent with actual object references
    - `DeduplicationHashCollisionError`: two different data payloads produced the same SHA-256 hash (astronomically unlikely but handled)
  - **`LifecycleError`**: base for lifecycle errors
    - `InvalidLifecycleConfigurationError`: lifecycle configuration is malformed or contains conflicting rules
    - `TooManyLifecycleRulesError`: configuration exceeds 1,000 rules
  - **`PresignedURLError`**: base for presigned URL errors
    - `ExpiredPresignedURLError`: the presigned URL has expired
    - `InvalidSignatureError`: the signature does not match the expected value
    - `SignatureMethodMismatchError`: the HTTP method does not match the signed method
  - **`MetadataError`**: base for metadata tier errors
    - `MetadataCorruptionError`: metadata index is in an inconsistent state
    - `MetadataCapacityExceededError`: user-defined metadata exceeds the 2 KB limit
  - **`NotificationError`**: base for event notification errors
    - `InvalidNotificationConfigurationError`: notification configuration is malformed
    - `NotificationDeliveryFailedError`: event delivery to destination failed after all retries

---

## Why This Is Necessary

The Enterprise FizzBuzz Platform has databases for structured data. It has file systems for hierarchical data. It has columnar storage for analytical data. It has a content-addressable store for OCI image blobs. It does not have object storage.

Object storage is the third pillar of cloud data persistence, alongside block storage and file storage. Every production cloud platform provides S3-compatible object storage as a primitive service. AWS S3, Google Cloud Storage, Azure Blob Storage, MinIO, Ceph RADOS Gateway -- the S3 API is the industry-standard interface for unstructured data at scale.

The platform's subsystems produce artifacts that are fundamentally object storage workloads: flame graph SVGs, ray-traced images, PDF documents, compressed video frames, ELF binaries, typeset output, ML model weights, evaluation result archives. These artifacts are immutable after creation, identified by unique keys, accessed by key lookup, and benefit from tiered storage (recent results in fast storage, historical results in archive storage). Storing them in a POSIX filesystem imposes unnecessary hierarchy, mutable semantics, and uniform storage cost on workloads that need none of these.

Furthermore, the platform's container ecosystem (FizzRegistry, FizzImage, FizzDeploy) relies on content-addressable blob storage for OCI image layers. FizzContainerd's content store serves this purpose today, but it lacks the durability guarantees (erasure coding), access control model (bucket policies, ACLs), lifecycle management (storage class transitions, expiration), and cross-region replication that a production container registry requires. FizzS3 provides the storage foundation on which FizzRegistry can build production-grade artifact storage.

Content-addressable deduplication addresses the storage efficiency problem inherent in the platform's evaluation result archival. FizzBuzz evaluations produce highly repetitive output -- the same "Fizz", "Buzz", and "FizzBuzz" strings appear across millions of evaluations. Deduplication eliminates redundant storage of identical data chunks, reducing physical storage consumption by an order of magnitude for repetitive workloads.

Erasure coding addresses the durability problem. A single-copy file in FizzVFS is lost if the storage medium fails. FizzReplica provides replication for SQLite databases but not for unstructured artifacts. Erasure coding achieves eleven-nines durability (99.999999999%) with only 1.4x storage overhead, compared to three-way replication's 3x overhead for the same durability. This is the storage-efficient path to durable artifact storage.

Presigned URLs address the secure sharing problem. The platform has no mechanism for generating temporary, credential-free access links to stored artifacts. A flame graph produced by FizzFlame cannot be shared with an external reviewer without sharing the reviewer's storage credentials (or the platform's). Presigned URLs provide time-limited, operation-scoped access to specific objects -- the industry-standard solution for secure artifact sharing.

Event notifications address the event-driven integration problem. When a new evaluation result is stored, downstream systems (the audit trail, the ML training pipeline, the compliance log) must be notified. Without event notifications, these systems must poll the storage tier for changes -- an inefficient pattern that introduces latency and wastes resources. Object lifecycle events published to FizzEventBus enable real-time, push-based integration between the storage tier and the rest of the platform.

## Estimated Scale

~3,500 lines of FizzS3 object storage implementation:
- ~250 lines of bucket management (Bucket model, BucketManager, BucketNameValidator, bucket CRUD operations, versioning configuration)
- ~350 lines of object operations (S3Object model, ObjectStore, put/get/head/delete/copy/list operations, conditional requests, byte-range requests)
- ~200 lines of object versioning (VersioningEngine, version chain management, delete markers, version suspension, version listing)
- ~300 lines of multipart upload (MultipartUploadManager, session lifecycle, part upload/list/copy, completion/abortion, IncompleteUploadReaper)
- ~200 lines of presigned URLs (PresignedURLGenerator, PresignedURLVerifier, SignatureV4Computer, Galois field operations for signing)
- ~200 lines of storage classes (StorageClass enum, StorageClassManager, transitions, RestoreProcessor, archive/restore lifecycle)
- ~250 lines of lifecycle policies (LifecycleConfiguration, LifecycleRule, LifecycleEvaluator, LifecycleDaemon, transition/expiration/cleanup actions)
- ~250 lines of cross-region replication (ReplicationConfiguration, ReplicationEngine, ReplicationQueue, ReplicationConflictResolver, loop detection)
- ~250 lines of server-side encryption (EncryptionEngine, SSE-S3/SSE-KMS/SSE-C modes, KeyRotationManager, envelope encryption)
- ~200 lines of access control (BucketPolicy, AccessControlList, BlockPublicAccessConfiguration, AccessControlEvaluator, canned ACLs)
- ~150 lines of event notifications (NotificationConfiguration, S3EventMessage, NotificationDispatcher, dead-letter queue)
- ~200 lines of content-addressable deduplication (ContentAddressableStore, ChunkManifest, ReferenceCounter, GarbageCollector)
- ~250 lines of erasure coding (ErasureCodingEngine, GaloisField, VandermondeMatrix, FragmentDistributor, FragmentIntegrityChecker)
- ~100 lines of metadata index (MetadataIndex, BTreeIndex, HashIndex, MetadataCheckpointer)
- ~100 lines of data tier (SegmentLog, Segment, CompactionPolicy)
- ~100 lines of S3 REST API layer (S3RequestRouter, S3ResponseFormatter, S3RequestAuthenticator)
- ~50 lines of metrics and observability integration (S3Metrics, S3TracingMiddleware)
- ~50 lines of middleware and CLI integration (FizzS3Middleware, FizzS3CLI)
- ~60 exception classes across 14 error categories
- ~500 tests covering bucket CRUD, object CRUD, versioning, multipart upload, presigned URLs, storage classes, lifecycle policies, cross-region replication, encryption, access control, event notifications, deduplication, erasure coding, metadata indexing, API routing, and error handling

Total: ~3,500 lines implementation + ~500 tests = ~4,000 lines
