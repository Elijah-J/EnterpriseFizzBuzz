# Research Report: Container Image Architecture

**Researcher**: Rizz
**Date**: 2026-03-24
**Scope**: OCI Image Specification, build best practices, init/sidecar patterns, vulnerability scanning, multi-architecture manifests

---

## 1. OCI Image Specification

### 1.1 Core Data Model

The OCI Image Specification defines a content-addressable, layered filesystem model for container images. The specification comprises four primary artifacts linked by cryptographic descriptors.

**Component Hierarchy:**
```
Image Index (fat manifest)
  └── Image Manifest (per-platform)
        ├── Image Config (execution metadata)
        └── Layers[] (filesystem changesets)
```

### 1.2 Content Descriptors

Every reference between components uses a **Content Descriptor** — a uniform pointer containing three required fields:

```json
{
  "mediaType": "application/vnd.oci.image.manifest.v1+json",
  "digest": "sha256:5b0bcabd1ed22e9fb1310cf6c2dec7cdef19f0ad69efa1f392e94a4333501270",
  "size": 7682
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `mediaType` | string | yes | MIME type of referenced content |
| `digest` | string | yes | SHA-256 hash for content addressing |
| `size` | int64 | yes | Byte size of raw content |
| `data` | string | no | Base64-encoded inline content |
| `annotations` | map | no | Arbitrary key-value metadata |
| `platform` | object | no | Platform filter (used in image indexes) |

**Digest Format**: `algorithm:hex` — e.g., `sha256:a9561eb1b190625c9adb5a9513e72c4dedafc1cb2d4c5236c9a6957ec7dfd5a9`

Content-addressable storage guarantees immutability: any modification produces a different digest, making tampering detectable at every level of the graph.

### 1.3 Image Manifest

The manifest binds a config and an ordered set of layers for a single platform.

**Media Type**: `application/vnd.oci.image.manifest.v1+json`

```json
{
  "schemaVersion": 2,
  "mediaType": "application/vnd.oci.image.manifest.v1+json",
  "config": {
    "mediaType": "application/vnd.oci.image.config.v1+json",
    "digest": "sha256:b5b2b2c507a0944348e0303114d8d93aaaa081732b86451d9bce1f432a537bc7",
    "size": 7023
  },
  "layers": [
    {
      "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip",
      "digest": "sha256:9834876dcfb05cb167a5c24953eba58c4ac89b1adf57f28f2f9d09af107ee8f0",
      "size": 32654
    }
  ],
  "subject": {
    "mediaType": "application/vnd.oci.image.manifest.v1+json",
    "digest": "sha256:...",
    "size": 1234
  },
  "annotations": {
    "com.example.key1": "value1"
  }
}
```

**Required Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `schemaVersion` | int | Must be `2` for backward compatibility |
| `config` | descriptor | References the image configuration blob |

**Optional Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `mediaType` | string | Should be set for compatibility |
| `layers` | descriptor[] | Filesystem layers in application order |
| `subject` | descriptor | Weak association to another manifest |
| `artifactType` | string | Type when config is empty |
| `annotations` | map | Arbitrary metadata |

**Layer Media Types (required support):**
- `application/vnd.oci.image.layer.v1.tar` — uncompressed tar
- `application/vnd.oci.image.layer.v1.tar+gzip` — gzip-compressed tar
- `application/vnd.oci.image.layer.v1.tar+zstd` — zstd-compressed (recommended)
- `application/vnd.oci.image.layer.nondistributable.v1.tar` — deprecated
- `application/vnd.oci.image.layer.nondistributable.v1.tar+gzip` — deprecated

**Empty Descriptor** (for artifacts without content):
- Media Type: `application/vnd.oci.empty.v1+json`
- Digest: `sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a`
- Size: `2`
- Payload: `{}`

### 1.4 Image Configuration

The config blob defines execution parameters and layer identity.

**Media Type**: `application/vnd.oci.image.config.v1+json`

```json
{
  "created": "2015-10-31T22:22:56.015925234Z",
  "author": "Alyssa P. Hacker <alyspdev@example.com>",
  "architecture": "amd64",
  "os": "linux",
  "config": {
    "User": "alice",
    "ExposedPorts": { "8080/tcp": {} },
    "Env": [
      "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
      "FOO=oci_is_a",
      "BAR=well_written_spec"
    ],
    "Entrypoint": ["/bin/my-app-binary"],
    "Cmd": ["--foreground", "--config", "/etc/my-app.d/default.cfg"],
    "Volumes": {
      "/var/job-result-data": {},
      "/var/log/my-app-logs": {}
    },
    "WorkingDir": "/home/alice",
    "Labels": {
      "com.example.project.git.url": "https://example.com/project.git",
      "com.example.project.git.commit": "45a939b2999782a3f005621a8d0f29aa387e1d6b"
    },
    "StopSignal": "SIGTERM"
  },
  "rootfs": {
    "type": "layers",
    "diff_ids": [
      "sha256:c6f988f4874bb0add23a778f753c65efe992244e148a1d2ec2a8b664fb66bbd1",
      "sha256:5f70bf18a086007016e948b04aed3b82103a36bea41755b6cddfaf10ace3c6ef"
    ]
  },
  "history": [
    {
      "created": "2015-10-31T22:22:54.690851953Z",
      "created_by": "/bin/sh -c #(nop) ADD file:a3bc1e842b69636f9df5256c49c5374fb4eef1e281fe3f282c65fb853ee171c5 in /"
    },
    {
      "created": "2015-10-31T22:22:55.613815829Z",
      "created_by": "/bin/sh -c #(nop) CMD [\"sh\"]",
      "empty_layer": true
    }
  ]
}
```

**Root-Level Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `architecture` | string | yes | CPU architecture (Go GOARCH values: `amd64`, `arm64`, `ppc64le`, `s390x`, `386`, `arm`) |
| `os` | string | yes | Operating system (Go GOOS values: `linux`, `windows`, `darwin`, `freebsd`) |
| `created` | string | no | RFC 3339 creation timestamp |
| `author` | string | no | Creator name/email |
| `os.version` | string | no | OS version (e.g., `10.0.14393.1066` for Windows) |
| `os.features` | array | no | Required OS features (e.g., `win32k`) |
| `variant` | string | no | CPU variant (e.g., ARM `v6`/`v7`/`v8`, AMD64 `v1`/`v2`/`v3`) |

**config Object Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `User` | string | Username or UID for process execution |
| `ExposedPorts` | object | Ports to expose; keys as `"port/protocol"` |
| `Env` | array | Environment variables in `"NAME=VALUE"` format |
| `Entrypoint` | array | Container startup command |
| `Cmd` | array | Default arguments to entrypoint |
| `Volumes` | object | Directories for container-specific data |
| `WorkingDir` | string | Working directory path |
| `Labels` | object | Arbitrary key-value metadata |
| `StopSignal` | string | System signal for container exit |
| `Memory` | int | Reserved for compatibility |
| `MemorySwap` | int | Reserved for compatibility |
| `CpuShares` | int | Reserved for compatibility |
| `Healthcheck` | object | Reserved for compatibility |

**rootfs Object (required):**
- `type`: Must be `"layers"`
- `diff_ids`: Array of DiffID digests (SHA-256 of uncompressed tar) in application order

**history Array (optional):**
Each entry records a build step:
- `created`: RFC 3339 timestamp
- `author`: Build step author
- `created_by`: Command that produced the layer
- `comment`: Custom message
- `empty_layer`: Boolean — `true` for metadata-only steps (no filesystem change)

### 1.5 Layer Identity: DiffID vs Descriptor Digest

A critical distinction in the specification:

- **Descriptor digest**: SHA-256 of the *compressed* blob (used for storage/transfer)
- **DiffID**: SHA-256 of the *uncompressed* tar content (used in config `rootfs.diff_ids`)

Example:
```
Compressed blob:    sha256:df9b9388f04ad6279a7410b85cedfdcb2208c0a003da7ab5613af71079148139
Uncompressed DiffID: sha256:4fc242d58285699eca05db3cc7c7122a2b8e014d9481f323bd9277baacfa0628
```

**ChainID** provides recursive identity for layer stacks:
```
ChainID(L0) = DiffID(L0)
ChainID(L0|...|Ln) = SHA256(ChainID(L0|...|Ln-1) + " " + DiffID(Ln))
```

**ImageID** = SHA-256 of the config JSON blob itself, making images content-addressable.

### 1.6 Image Layout (On-Disk Format)

The OCI image layout stores blobs in a content-addressable directory:

```
image-root/
├── oci-layout          # {"imageLayoutVersion": "1.0.0"}
├── index.json          # References image indexes/manifests
└── blobs/
    └── sha256/
        ├── <manifest-digest>
        ├── <config-digest>
        ├── <layer-1-digest>
        ├── <layer-2-digest>
        └── <layer-n-digest>
```

Each blob file is named by its SHA-256 digest. The `index.json` entry point references the top-level manifest or image index.

### 1.7 Filesystem Layers and Whiteout Files

Layers are tar archives representing filesystem changesets applied sequentially:

- **Added/Modified files**: Present in the tar with their new content
- **Deleted files**: Represented by **whiteout files** — empty files named `.wh.<deleted-filename>`
- **Opaque directories**: A whiteout marker `.wh..wh..opq` indicates the entire directory should be replaced

In OverlayFS (the standard storage driver), layers map to:
- **lowerdir**: Read-only image layers (stacked, up to 128 layers)
- **upperdir**: Writable container layer where runtime changes are recorded
- **merged**: Unified filesystem view presented to the container
- **workdir**: Scratch space for the overlay kernel module

Deleted files appear as character devices with 0/0 device numbers in overlayfs. Deleted directories get an extended attribute `trusted.overlay.opaque=y`.

---

## 2. OCI Image Index (Multi-Architecture Manifests)

### 2.1 Structure

The image index (also called a "fat manifest") aggregates platform-specific manifests under a single tag.

**Media Type**: `application/vnd.oci.image.index.v1+json`

```json
{
  "schemaVersion": 2,
  "mediaType": "application/vnd.oci.image.index.v1+json",
  "manifests": [
    {
      "mediaType": "application/vnd.oci.image.manifest.v1+json",
      "size": 7143,
      "digest": "sha256:e692418e4cbaf90ca69d05a66403747baa33ee08806650b51fab815ad7fc331f",
      "platform": {
        "architecture": "ppc64le",
        "os": "linux"
      }
    },
    {
      "mediaType": "application/vnd.oci.image.manifest.v1+json",
      "size": 7682,
      "digest": "sha256:5b0bcabd1ed22e9fb1310cf6c2dec7cdef19f0ad69efa1f392e94a4333501270",
      "platform": {
        "architecture": "amd64",
        "os": "linux"
      }
    },
    {
      "mediaType": "application/vnd.oci.image.manifest.v1+json",
      "size": 7344,
      "digest": "sha256:aaa...",
      "platform": {
        "architecture": "arm64",
        "os": "linux",
        "variant": "v8"
      }
    }
  ],
  "annotations": {
    "com.example.key1": "value1"
  }
}
```

### 2.2 Platform Object

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `architecture` | string | yes | CPU architecture (Go GOARCH values) |
| `os` | string | yes | Operating system (Go GOOS values) |
| `os.version` | string | no | OS version targeting (e.g., Windows build numbers) |
| `os.features` | array | no | Required OS features |
| `variant` | string | no | CPU variant (ARM: `v6`/`v7`/`v8`; AMD64: `v1`/`v2`/`v3`) |

### 2.3 Platform Resolution Algorithm

Resolution follows a simple priority rule: **first matching entry wins**. Container runtimes match the host platform against the `platform` object in each manifest entry. If multiple manifests match the client's requirements, the first matching entry in the array is selected.

This means ordering in the `manifests` array establishes priority — preferred platforms should appear first.

**Nested indexes** are supported: an image index can reference other image indexes (not only manifests), enabling hierarchical multi-platform structures.

---

## 3. OCI Annotations (Standard Labels)

### 3.1 Pre-Defined Keys

The OCI specification reserves the `org.opencontainers.image` namespace:

| Key | Description |
|-----|-------------|
| `org.opencontainers.image.created` | RFC 3339 creation timestamp |
| `org.opencontainers.image.authors` | Contact details (freeform string) |
| `org.opencontainers.image.url` | URL for more information |
| `org.opencontainers.image.documentation` | Documentation URL |
| `org.opencontainers.image.source` | Source code URL |
| `org.opencontainers.image.version` | Packaged software version |
| `org.opencontainers.image.revision` | Source control revision identifier |
| `org.opencontainers.image.vendor` | Distributing entity name |
| `org.opencontainers.image.licenses` | SPDX License Expression |
| `org.opencontainers.image.ref.name` | Reference name for target |
| `org.opencontainers.image.title` | Human-readable title |
| `org.opencontainers.image.description` | Human-readable description |
| `org.opencontainers.image.base.digest` | Digest of parent/base image |
| `org.opencontainers.image.base.name` | Reference of parent/base image |

### 3.2 Annotation Rules

- Keys and values must be strings
- Values may be empty strings
- Keys must be unique within a map
- Keys should use reverse-domain notation for namespacing
- The `org.opencontainers` prefix is reserved for OCI specifications

---

## 4. Container Image Best Practices

### 4.1 Base Image Selection

| Base Type | Size | Use Case |
|-----------|------|----------|
| `scratch` | 0 bytes | Statically compiled binaries (Go, Rust) |
| Distroless | 2-20 MB | Language-specific runtimes without shell |
| Alpine | ~6 MB | Minimal Linux with package manager |
| Chainguard/Wolfi | ~5-15 MB | Security-hardened minimal bases |
| Ubuntu/Debian slim | ~25-80 MB | When full package ecosystem needed |

Switching from `ubuntu` to `distroless/static` typically reduces image size from 800 MB to 15-30 MB.

### 4.2 Multi-Stage Build Pattern

Separates build-time dependencies from runtime artifacts:

```dockerfile
# Stage 1: Build
FROM golang:1.21 AS builder
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /app

# Stage 2: Runtime
FROM gcr.io/distroless/static-debian12
COPY --from=builder /app /app
ENTRYPOINT ["/app"]
```

Benefits:
- Build tools never appear in the final image
- Stages can run in parallel (BuildKit)
- Shared stages are built only once

### 4.3 Layer Caching Strategy

Instructions should be ordered from least to most frequently changing:

1. `FROM` — base image (changes rarely)
2. `LABEL`, `ENV` — metadata/configuration
3. `COPY requirements.txt` — dependency declarations
4. `RUN pip install` — dependency installation (cached if requirements unchanged)
5. `COPY . .` — application source (changes most often)

Key rules:
- Each instruction creates a layer; cache invalidation cascades to all subsequent layers
- Combine `apt-get update && apt-get install` to prevent stale cache issues
- Use `--mount=type=cache` for persistent package caches across builds

### 4.4 Security Hardening

**Non-root execution:**
```dockerfile
RUN groupadd -r appuser && \
    useradd --no-log-init -r -g appuser -u 1001 appuser
USER appuser
```

**Digest pinning for supply chain security:**
```dockerfile
FROM alpine:3.21@sha256:a8560b36e8b8210634f77d9f7f9efd7ffa463e380b75e2e74aff4511df3ef88c
```

**Signal handling with exec form:**
```dockerfile
COPY ./docker-entrypoint.sh /
ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["postgres"]
```

With `exec "$@"` inside the script to ensure PID 1 receives signals for graceful shutdown.

### 4.5 HEALTHCHECK Instruction

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8080/health || exit 1
```

Fields:
- `interval`: Time between checks (default 30s)
- `timeout`: Check timeout (default 30s)
- `start-period`: Grace period before checks count (default 0s)
- `retries`: Consecutive failures before unhealthy (default 3)

### 4.6 .dockerignore Patterns

```
*.md
.git
.gitignore
node_modules
__pycache__
*.log
.env
.DS_Store
```

Reduces build context size and prevents sensitive files from leaking into images.

---

## 5. Init Container Patterns

### 5.1 Lifecycle Model

Init containers execute sequentially before any application containers start:

```
Init Container 1 → Init Container 2 → ... → Init Container N → App Containers
```

Guarantees:
- Each init container must complete successfully (exit 0) before the next starts
- All init containers must complete before any app container starts
- If an init container fails, the pod enters `Init:Error` or `Init:CrashLoopBackOff`
- On init failure, the pod restarts according to `restartPolicy`, re-running all init containers

### 5.2 Common Patterns

| Pattern | Description | Example |
|---------|-------------|---------|
| **Dependency wait** | Block until upstream service is available | Wait for database port to accept connections |
| **Configuration generation** | Generate config files from templates | Render config from ConfigMap/Secret into shared volume |
| **Data seeding** | Pre-populate data before app starts | Download ML model, seed database |
| **Schema migration** | Run database migrations | Apply Flyway/Liquibase migrations |
| **Permission setup** | Fix filesystem permissions | `chown`/`chmod` on mounted volumes |
| **Certificate provisioning** | Fetch TLS certificates | Download certs from Vault, write to shared volume |
| **Cache warming** | Pre-populate caches | Download lookup tables, precompute indexes |

### 5.3 Shared Volume Communication

Init containers communicate with app containers via shared volumes:

```yaml
spec:
  initContainers:
  - name: config-generator
    image: config-tool:1.0
    command: ["generate-config", "--output", "/config/app.yaml"]
    volumeMounts:
    - name: config-volume
      mountPath: /config
  containers:
  - name: app
    image: my-app:2.0
    volumeMounts:
    - name: config-volume
      mountPath: /etc/app
  volumes:
  - name: config-volume
    emptyDir: {}
```

The init container writes configuration to the shared `emptyDir` volume; the app container reads it at startup.

### 5.4 Key Properties

- Init containers can contain utilities or setup scripts not present in the app image
- Init containers run with different security contexts than app containers
- Init containers always run to completion — they are not long-running
- All init containers re-run if the pod restarts (idempotency is essential)
- Resource requests/limits are computed independently from app containers

---

## 6. Sidecar Container Patterns

### 6.1 Pattern Categories

Sidecars run concurrently with the main container for the entire pod lifecycle, sharing network and storage namespaces.

**Logging Sidecar (Fluent Bit):**
- Main container writes logs to stdout/stderr or a shared volume
- Fluent Bit sidecar reads, parses, and ships logs to backends (Elasticsearch, CloudWatch, Loki)
- Pattern: shared `emptyDir` volume at `/var/log/app`

**Metrics Sidecar (Prometheus):**
- Exposes metrics endpoint (typically `/metrics` on port 9090)
- Prometheus annotations for auto-discovery: `prometheus.io/scrape: "true"`, `prometheus.io/port: "9090"`
- Can aggregate metrics from multiple containers in the pod

**Tracing Sidecar (OpenTelemetry Collector):**
- Runs as a separate container in the same pod
- Application sends traces to `localhost:4317` (OTLP gRPC) or `localhost:4318` (OTLP HTTP)
- Collector processes, batches, and exports to backends (Jaeger, Zipkin, Tempo)
- Supports receiving, processing, and forwarding metrics, traces, and logs

**Proxy Sidecar (Envoy):**
- Intercepts all inbound/outbound network traffic via iptables rules
- Provides load balancing, circuit breaking, rate limiting, mTLS
- Exposes admin metrics on `/stats/prometheus` (port 9901)
- Service mesh implementations (Istio, Linkerd) auto-inject proxy sidecars

**Security Sidecar (Vault Agent):**
- Syncs secrets from HashiCorp Vault to shared volumes
- Handles token renewal and secret rotation
- Enforces TLS termination and token validation

**Configuration Sidecar:**
- Watches external sources (Git, Consul, etcd) for changes
- Writes updated configuration to shared volumes
- Main container detects changes via filesystem watchers (inotify)

### 6.2 Kubernetes Native Sidecar Support

Kubernetes 1.28+ introduced native sidecar containers via the `restartPolicy: Always` field on init containers:

```yaml
spec:
  initContainers:
  - name: log-collector
    image: fluent-bit:2.2
    restartPolicy: Always    # Makes this a native sidecar
    volumeMounts:
    - name: logs
      mountPath: /var/log/app
```

Native sidecars:
- Start before regular containers and keep running throughout pod lifecycle
- Shut down after all regular containers have terminated (enabling log flushing)
- Participate in pod readiness calculation
- Have clearly defined startup ordering relative to init containers

### 6.3 Shared Namespace Benefits

Containers in the same pod share:
- **Network namespace**: Communicate via `localhost`, see same IP address
- **IPC namespace**: Can use shared memory and semaphores
- **Storage volumes**: `emptyDir` volumes for inter-container data exchange
- **Process namespace** (optional): Can see each other's processes when enabled

### 6.4 Resource Considerations

- Sidecar resource requests/limits are set independently per container
- Total pod resource request = sum of all container requests
- Sidecars should be lightweight to avoid consuming excessive resources
- CPU/memory limits prevent sidecars from starving the main application

---

## 7. Vulnerability Scanning

### 7.1 Scanning Approaches

**Static Analysis (Layer-by-Layer):**
Both Trivy and Grype analyze container images by inspecting each filesystem layer:
1. Pull and decompress the image
2. Extract package manifests from each layer (dpkg, rpm, apk databases; language lock files)
3. Match installed packages against vulnerability databases
4. Report findings with severity classification

**Two Major Tools:**

| Feature | Trivy | Grype |
|---------|-------|-------|
| Vendor | Aqua Security | Anchore |
| Package detection | OS + language + non-packaged | OS + language (via Syft) |
| SBOM generation | Built-in (SPDX, CycloneDX) | Via Syft companion tool |
| Severity source | Vendor-first with NVD fallback | Composite score (CVSS + EPSS + KEV) |
| Detection modes | `precise` (fewer false positives) / `comprehensive` | Single mode |
| Scanning targets | Images, filesystems, repos, K8s clusters, IaC, secrets | Images, filesystems, SBOMs |

### 7.2 Vulnerability Database Architecture

**Trivy's cascading source priority:**
1. OS vendor advisories (Red Hat, Ubuntu, Alpine, Debian) — most accurate for distribution packages because vendors backport fixes
2. Language-specific databases (GitHub Advisory, Go Vulnerability DB, Ruby Advisory DB)
3. NVD (National Vulnerability Database) — fallback when vendor data unavailable

**Grype's composite approach:**
- Combines CVSS base scores with EPSS (Exploit Prediction Scoring System) probability and CISA KEV (Known Exploited Vulnerabilities) catalog status
- Produces a 0-10 composite risk score

### 7.3 CVE Severity Classification

CVSS v3.x score ranges map to severity levels:

| Score Range | Severity | Color Convention |
|-------------|----------|-----------------|
| 0.0 | None | — |
| 0.1 - 3.9 | Low | Yellow |
| 4.0 - 6.9 | Medium | Orange |
| 7.0 - 8.9 | High | Red |
| 9.0 - 10.0 | Critical | Dark Red |

Vendor severity can override NVD severity. Example: CVE-2023-0464 is rated HIGH by NVD but LOW by Red Hat. Trivy respects vendor assessments by default, as vendors understand the actual impact on their packages.

### 7.4 SBOM (Software Bill of Materials)

Two standard formats:

**SPDX (System Package Data Exchange):**
- ISO/IEC 5962:2021 standard
- Supports multiple serialization formats (JSON, XML, YAML, tag-value)
- Strong license compliance focus

**CycloneDX:**
- OWASP standard
- Designed for security use cases
- Includes vulnerability and dependency relationship data
- Supports VEX (Vulnerability Exploitability eXchange) documents

**Recommended Workflow:**
1. Generate SBOM once using Syft/Trivy at build time
2. Store SBOM alongside the image (as OCI artifact or attestation)
3. Rescan the SBOM against updated vulnerability databases — avoids re-analyzing the image on every scan

### 7.5 Scanning Configuration

Key Trivy configuration flags:
- `--severity CRITICAL,HIGH` — filter by severity threshold
- `--ignore-unfixed` — suppress vulnerabilities without available patches
- `--pkg-types os,library` — restrict to OS or language packages
- `--pkg-relationships direct,indirect` — filter by dependency relationship
- `--detection-priority precise|comprehensive` — trade-off between false positives and coverage
- `--distro <family>/<version>` — override OS detection
- `--vuln-severity-source` — customize severity source priority order

---

## 8. Implementation Considerations for FizzImage

### 8.1 Data Structures to Model

Based on the research, these are the core data structures needed for a technically faithful container image catalog:

1. **ContentDescriptor** — mediaType, digest, size, annotations, platform
2. **ImageManifest** — schemaVersion, config descriptor, layers array, subject, annotations, artifactType
3. **ImageIndex** — schemaVersion, manifests array (with platform objects), annotations
4. **ImageConfig** — architecture, os, variant, config (User/Env/Cmd/Entrypoint/ExposedPorts/Volumes/WorkingDir/Labels/StopSignal), rootfs (type + diff_ids), history array
5. **Platform** — architecture, os, os.version, os.features, variant
6. **LayerDescriptor** — extends ContentDescriptor with compression type tracking
7. **WhiteoutEntry** — path, type (file deletion vs opaque directory)
8. **ImageAnnotation** — key-value with OCI standard key validation
9. **VulnerabilityReport** — CVE ID, severity, CVSS score, affected package, fixed version, data source
10. **SBOM** — format (SPDX/CycloneDX), packages list, dependency graph
11. **BuildHistory** — created, created_by, author, comment, empty_layer flag
12. **InitContainerSpec** — image, command, volumes, ordering, completion requirements
13. **SidecarSpec** — type (logging/metrics/tracing/proxy/security), image, ports, volume mounts, restart policy

### 8.2 Lifecycle Flows

**Image Build Pipeline:**
```
Dockerfile → Parse → Execute Stages → Generate Layers → Compute DiffIDs →
  Build Config JSON → Compute ImageID → Create Manifest → Sign → Push to Registry
```

**Image Pull and Resolution:**
```
Tag Reference → Resolve to Digest → Fetch Index → Platform Match →
  Select Manifest → Fetch Config → Verify DiffIDs → Pull Layers → Unpack
```

**Vulnerability Scan Pipeline:**
```
Image Reference → Pull/Load → Extract Layers → Identify Packages →
  Query Vulnerability DB → Match CVEs → Compute Severity → Generate Report
```

**Init Container Lifecycle:**
```
Pod Scheduled → Init Container 1 Start → Wait for Exit 0 →
  Init Container 2 Start → Wait for Exit 0 → ... → Start App Containers
```

**Sidecar Lifecycle (Native):**
```
Pod Scheduled → Sidecar Start → Wait for Ready → Start App Containers →
  App Running → App Terminates → Sidecar Cleanup → Sidecar Terminates
```

### 8.3 Integration Points with Existing Codebase

The existing codebase already has related infrastructure:
- `fizzregistry.py` — OCI image registry with `OCIImageIndex`, `OCIImageConfig`, `ContainerConfig`, `ImageSignature`, platform enums
- `fizzcontainerd.py` — Container daemon with `ImageService`, `_ImageRecord`, container lifecycle
- `fizzoci.py` — OCI runtime with `OCIContainer`, `ContainerProcess`, `ContainerHooks`
- `fizzcni.py` — Container networking with `ContainerDNS`

FizzImage should complement these by providing the image catalog, build pipeline, vulnerability scanning, and init/sidecar pattern library — referencing the existing registry and runtime modules rather than duplicating their functionality.

---

## Sources

- [OCI Image Manifest Specification](https://github.com/opencontainers/image-spec/blob/main/manifest.md)
- [OCI Image Index Specification](https://github.com/opencontainers/image-spec/blob/main/image-index.md)
- [OCI Image Config Specification](https://github.com/opencontainers/image-spec/blob/main/config.md)
- [OCI Annotations Specification](https://github.com/opencontainers/image-spec/blob/main/annotations.md)
- [Quarkslab: Digging into the OCI Image Specification](https://blog.quarkslab.com/digging-into-the-oci-image-specification.html)
- [Docker Build Best Practices](https://docs.docker.com/build/building/best-practices/)
- [Docker Multi-Stage Builds](https://docs.docker.com/build/building/multi-stage/)
- [Docker OverlayFS Storage Driver](https://docs.docker.com/engine/storage/drivers/overlayfs-driver/)
- [Kubernetes Init Containers Guide](https://devopscube.com/kubernetes-init-containers/)
- [Kubernetes Sidecar Pattern Guide](https://www.plural.sh/blog/kubernetes-sidecar-guide/)
- [Trivy Vulnerability Scanner](https://trivy.dev/docs/latest/scanner/vulnerability/)
- [Trivy vs Grype Comparison](https://appsecsanta.com/sca-tools/trivy-vs-grype)
- [Aqua Security Trivy GitHub](https://github.com/aquasecurity/trivy)
