"""
Enterprise FizzBuzz Platform - FizzRegistry: OCI Distribution-Compliant Image Registry
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class RegistryError(FizzBuzzError):
    """Base exception for all FizzRegistry image registry errors.

    FizzRegistry provides OCI Distribution-compliant image storage
    and distribution with content-addressable blob management,
    manifest validation, and registry API operations.  All
    registry-specific failures inherit from this class to enable
    categorical error handling in the middleware pipeline.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Registry error: {reason}",
            error_code="EFP-REG00",
            context={"reason": reason},
        )


class BlobNotFoundError(RegistryError):
    """Raised when a blob digest is not found in the blob store.

    The blob store indexes blobs by their SHA-256 digest.
    Operations referencing a digest that does not exist in the
    store are rejected with this exception.
    """

    def __init__(self, digest: str) -> None:
        super().__init__(f"Blob not found: {digest}")
        self.error_code = "EFP-REG01"
        self.context = {"digest": digest}


class BlobCorruptionError(RegistryError):
    """Raised when blob data fails integrity verification.

    Every blob is verified against its SHA-256 digest on access.
    If the stored content does not match the expected digest, the
    blob is considered corrupt and this exception is raised.
    """

    def __init__(self, digest: str, reason: str) -> None:
        super().__init__(f"Blob corruption detected for {digest}: {reason}")
        self.error_code = "EFP-REG02"
        self.context = {"digest": digest, "reason": reason}


class BlobStoreFullError(RegistryError):
    """Raised when the blob store has reached its capacity limit.

    The blob store has a configurable maximum number of blobs.
    Attempts to store blobs beyond this limit are rejected with
    this exception until garbage collection reclaims unreferenced
    blobs.
    """

    def __init__(self, max_blobs: int, reason: str) -> None:
        super().__init__(f"Blob store full ({max_blobs} blobs): {reason}")
        self.error_code = "EFP-REG03"
        self.context = {"max_blobs": max_blobs, "reason": reason}


class ManifestNotFoundError(RegistryError):
    """Raised when a manifest reference is not found in the registry.

    Manifests are indexed by repository name and reference (tag or
    digest).  Operations referencing a manifest that does not exist
    trigger this exception.
    """

    def __init__(self, reference: str) -> None:
        super().__init__(f"Manifest not found: {reference}")
        self.error_code = "EFP-REG04"
        self.context = {"reference": reference}


class ManifestValidationError(RegistryError):
    """Raised when a manifest fails structural or referential validation.

    Manifests must reference existing blobs and conform to the OCI
    image manifest schema.  Missing blob references, invalid media
    types, or schema violations trigger this exception.
    """

    def __init__(self, reference: str, reason: str) -> None:
        super().__init__(f"Manifest validation failed for '{reference}': {reason}")
        self.error_code = "EFP-REG05"
        self.context = {"reference": reference, "reason": reason}


class ManifestExistsError(RegistryError):
    """Raised when attempting to push a manifest that already exists.

    Content-addressable storage guarantees uniqueness by digest.
    Pushing a manifest whose digest matches an existing manifest
    in the same repository triggers this exception when overwrite
    is not permitted.
    """

    def __init__(self, reference: str) -> None:
        super().__init__(f"Manifest already exists: {reference}")
        self.error_code = "EFP-REG06"
        self.context = {"reference": reference}


class RepositoryNotFoundError(RegistryError):
    """Raised when a repository name is not found in the registry catalog.

    The registry maintains a catalog of repositories.  Operations
    targeting a repository that does not exist trigger this
    exception.
    """

    def __init__(self, repository: str) -> None:
        super().__init__(f"Repository not found: {repository}")
        self.error_code = "EFP-REG07"
        self.context = {"repository": repository}


class RepositoryLimitError(RegistryError):
    """Raised when the maximum number of repositories has been reached.

    The registry enforces a configurable limit on the number of
    repositories to prevent unbounded catalog growth.  Attempts
    to create repositories beyond this limit trigger this exception.
    """

    def __init__(self, max_repos: int, reason: str) -> None:
        super().__init__(f"Repository limit reached ({max_repos}): {reason}")
        self.error_code = "EFP-REG08"
        self.context = {"max_repos": max_repos, "reason": reason}


class TagNotFoundError(RegistryError):
    """Raised when a tag is not found in a repository.

    Tags are mutable references to manifest digests within a
    repository.  Operations referencing a tag that does not exist
    trigger this exception.
    """

    def __init__(self, repository: str, tag: str) -> None:
        super().__init__(f"Tag '{tag}' not found in repository '{repository}'")
        self.error_code = "EFP-REG09"
        self.context = {"repository": repository, "tag": tag}


class TagLimitError(RegistryError):
    """Raised when the maximum number of tags per repository is reached.

    Each repository has a configurable maximum number of tags.
    Attempts to create tags beyond this limit trigger this
    exception until old tags are removed.
    """

    def __init__(self, repository: str, max_tags: int, reason: str) -> None:
        super().__init__(
            f"Tag limit reached for '{repository}' ({max_tags} tags): {reason}"
        )
        self.error_code = "EFP-REG10"
        self.context = {"repository": repository, "max_tags": max_tags, "reason": reason}


class FizzFileParseError(RegistryError):
    """Raised when parsing a FizzFile build script fails.

    FizzFile is the platform's Dockerfile equivalent.  Syntax
    errors, unknown instructions, or invalid arguments in the
    build script trigger this exception.
    """

    def __init__(self, line_number: int, reason: str) -> None:
        super().__init__(f"FizzFile parse error at line {line_number}: {reason}")
        self.error_code = "EFP-REG11"
        self.context = {"line_number": line_number, "reason": reason}


class FizzFileMissingFromError(RegistryError):
    """Raised when a FizzFile does not begin with a FROM instruction.

    Every FizzFile must specify a base image as its first
    instruction.  FizzFiles that omit the FROM instruction or
    place other instructions before it trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"FizzFile missing FROM instruction: {reason}")
        self.error_code = "EFP-REG12"
        self.context = {"reason": reason}


class ImageBuildError(RegistryError):
    """Raised when the image builder fails to produce an image.

    The image builder processes FizzFile instructions to produce
    OCI images.  Instruction execution failures, layer capture
    errors, or manifest generation failures trigger this exception.
    """

    def __init__(self, instruction: str, reason: str) -> None:
        super().__init__(f"Image build error at '{instruction}': {reason}")
        self.error_code = "EFP-REG13"
        self.context = {"instruction": instruction, "reason": reason}


class LayerCacheMissError(RegistryError):
    """Raised when a layer cache lookup fails to find the expected entry.

    The image builder caches layers by instruction hash to avoid
    re-executing unchanged build steps.  This exception indicates
    a cache miss when a cache hit was expected, typically due to
    instruction or context changes invalidating the cache.
    """

    def __init__(self, cache_key: str, reason: str) -> None:
        super().__init__(f"Layer cache miss for key '{cache_key}': {reason}")
        self.error_code = "EFP-REG14"
        self.context = {"cache_key": cache_key, "reason": reason}


class GarbageCollectionError(RegistryError):
    """Raised when the garbage collector encounters an error.

    The garbage collector identifies and removes unreferenced
    blobs using a mark-and-sweep algorithm.  Reference walking
    failures, blob deletion errors, or grace period violations
    trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Garbage collection error: {reason}")
        self.error_code = "EFP-REG15"
        self.context = {"reason": reason}


class ImageSignatureError(RegistryError):
    """Raised when image signing or verification fails.

    The image signer provides cosign-style ECDSA-P256 signing
    and verification of manifest digests.  Key generation failures,
    signing errors, or verification mismatches trigger this
    exception.
    """

    def __init__(self, image_ref: str, reason: str) -> None:
        super().__init__(f"Image signature error for '{image_ref}': {reason}")
        self.error_code = "EFP-REG16"
        self.context = {"image_ref": image_ref, "reason": reason}


class VulnerabilityScanError(RegistryError):
    """Raised when vulnerability scanning encounters an error.

    The vulnerability scanner analyzes image layers for known
    CVEs.  Layer analysis failures, database errors, or scan
    timeouts trigger this exception.
    """

    def __init__(self, image_ref: str, reason: str) -> None:
        super().__init__(f"Vulnerability scan error for '{image_ref}': {reason}")
        self.error_code = "EFP-REG17"
        self.context = {"image_ref": image_ref, "reason": reason}


class RegistryDashboardError(RegistryError):
    """Raised when the registry dashboard rendering fails.

    The dashboard renders registry statistics, repository catalog,
    blob store metrics, and scan results in ASCII format.  Data
    retrieval or rendering failures trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Registry dashboard rendering failed: {reason}")
        self.error_code = "EFP-REG18"
        self.context = {"reason": reason}


class RegistryMiddlewareError(RegistryError):
    """Raised when the registry middleware fails to process an evaluation.

    The middleware intercepts each FizzBuzz evaluation to make the
    registry available for image pull operations during startup.
    If registry initialization or image resolution fails during
    middleware processing, this exception is raised.
    """

    def __init__(self, evaluation_number: int, reason: str) -> None:
        super().__init__(
            f"Registry middleware error at evaluation {evaluation_number}: {reason}"
        )
        self.error_code = "EFP-REG19"
        self.context = {"evaluation_number": evaluation_number, "reason": reason}
        self.evaluation_number = evaluation_number

