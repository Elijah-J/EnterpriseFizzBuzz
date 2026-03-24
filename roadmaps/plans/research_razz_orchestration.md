# Research Report: Deployment Pipelines, Orchestration, Chaos Engineering, and Container Observability

**Author:** Razz (Competitive Research Specialist)
**Date:** 2026-03-24
**Scope:** CI/CD pipelines, deployment strategies, Docker Compose specification, Kubernetes CRI, chaos engineering, container observability

---

## 1. CI/CD Pipelines

### 1.1 Argo CD — GitOps Reconciliation

Argo CD implements declarative GitOps continuous delivery for Kubernetes. Its architecture centers on a continuous reconciliation loop that compares desired state (stored in Git) against live cluster state and takes corrective action when drift is detected.

#### Architecture Components

| Component | Role |
|-----------|------|
| **API Server** | Exposes gRPC/REST API consumed by Web UI, CLI, and CI/CD integrations. Handles application management, authentication, RBAC enforcement. |
| **Repository Server** | Maintains local cache of Git repositories. Generates Kubernetes manifests by rendering Helm templates, applying Kustomize overlays, or processing plain YAML. |
| **Application Controller** | The reconciliation engine. Continuously monitors running applications, compares live state against desired state, and triggers sync operations. |
| **Redis** | Caches rendered manifests and application state for performance. |

#### Reconciliation Loop Sequence

```
1. Developer commits change to Git repository
2. Repo Server detects change (webhook or polling interval)
3. Repo Server fetches updated manifests from Git
4. Repo Server renders manifests (Helm/Kustomize/plain)
5. Application Controller compares desired state vs live state
6. If drift detected:
   a. Controller generates diff
   b. Sync operation applies manifests to Kubernetes API
   c. Controller monitors rollout progress
   d. Health assessment runs against deployed resources
7. Loop repeats (default: 3-minute polling interval, or webhook-triggered)
```

#### Sync Policies

| Policy | Behavior |
|--------|----------|
| **Manual Sync** | Requires explicit user action to apply changes |
| **Auto-Sync** | Automatically applies changes when drift is detected |
| **Self-Heal** | Reverts manual cluster changes back to Git-defined state |
| **Auto-Prune** | Deletes resources removed from Git |

#### Application Health States

- **Healthy**: All resources match desired state and are operational
- **Progressing**: Resources are being created/updated
- **Degraded**: Resources exist but are not healthy
- **Suspended**: Application is paused
- **Missing**: Resources defined in Git do not exist in cluster
- **Unknown**: Health status cannot be determined

### 1.2 Spinnaker — Multi-Cloud Deployment Pipeline

Spinnaker is a multi-cloud continuous delivery platform originally developed by Netflix. It treats deployment strategies as first-class constructs and provides a rich stage-based pipeline model.

#### Pipeline Stage Catalog

**Core Stages:**

| Stage | Description |
|-------|-------------|
| **Bake** | Creates machine images using Hashicorp Packer. Generates unique keys from base OS + versioned packages; skips bake if no changes detected. |
| **Deploy** | Deploys baked/found images using configurable strategies (red/black, highlander, custom). |
| **Canary Analysis** | Runs automated canary analysis via Kayenta integration. |
| **Manual Judgment** | Pauses pipeline for human approval. Supports optional input choices. |
| **Wait** | Pauses execution for a specified duration. Supports manual skip. |
| **Webhook** | Makes HTTP calls to external systems. Succeeds on 2XX/3XX, fails on 4XX, retries on 5XX. |
| **Check Preconditions** | Verifies conditions (cluster size, expressions) before proceeding. |
| **Jenkins** | Triggers and monitors Jenkins jobs. |
| **Pipeline** | Executes another pipeline as a sub-pipeline. |
| **Run Job** | Executes a container from a configured Docker registry. |
| **Script** | Runs arbitrary scripts sandboxed through Jenkins. |

**Infrastructure Stages:**

| Stage | Description |
|-------|-------------|
| **Clone Server Group** | Copies all attributes of a Server Group to create a new one |
| **Destroy Server Group** | Deletes a Server Group and its resources |
| **Disable Server Group** | Stops traffic to a Server Group while keeping it running |
| **Enable Server Group** | Resumes traffic to a previously disabled Server Group |
| **Resize Server Group** | Adjusts capacity by percentage or specific count |
| **Rollback Cluster** | Rolls back one or more regions in a cluster |
| **Scale Down Cluster** | Reduces cluster size, optionally protecting active groups |
| **Shrink Cluster** | Reduces cluster to specified number of newest/largest groups |
| **Tag Image** | Applies tags to pipeline images |

**Kubernetes-Specific Stages:**

| Stage | Description |
|-------|-------------|
| **Bake (Manifest)** | Renders manifests using Helm or similar tools |
| **Deploy (Manifest)** | Deploys Kubernetes YAML/JSON manifests |
| **Delete (Manifest)** | Destroys Kubernetes objects |
| **Patch (Manifest)** | Updates existing Kubernetes resources in-place |
| **Scale (Manifest)** | Resizes Kubernetes objects |
| **Undo Rollout (Manifest)** | Rolls back manifests by revision count |
| **Find Artifacts From Resource** | Extracts artifacts from Kubernetes resources |

**Artifact Stages:**

| Stage | Description |
|-------|-------------|
| **Find Artifact From Execution** | Locates artifacts from different pipeline executions |
| **Find Image From Cluster** | Retrieves images from existing clusters |
| **Find Image From Tags** | Locates newest image matching specified tags |

#### Canary Analysis with Kayenta

Spinnaker integrates with Kayenta for automated canary analysis:

```
Pipeline Flow:
1. Bake Stage → creates deployment artifact
2. Deploy Canary → provisions canary server group
3. Canary Analysis → Kayenta compares canary vs baseline metrics
4. Judge (NetflixACAJudge-v1.0) → pass/fail/marginal verdict
5a. Pass → Deploy to production
5b. Fail → Rollback canary, alert team
```

The canary judge compares metric time series between canary and baseline groups, applying statistical tests to determine if the canary behaves significantly differently. The analysis runs iteratively over configurable intervals, providing increasing confidence over time.

### 1.3 Typical CI/CD Pipeline Stages

A production-grade container deployment pipeline follows this sequence:

```
Build → Scan → Sign → Push → Deploy → Validate → (Rollback)

1. BUILD
   - Compile application
   - Run unit tests
   - Build container image (Dockerfile / Buildpack)

2. SCAN
   - Static analysis (SAST)
   - Container image vulnerability scan (Trivy, Snyk, Grype)
   - License compliance check
   - SBOM generation

3. SIGN
   - Image signing (cosign / Notary v2)
   - Attestation generation (SLSA provenance)
   - Signature verification gate

4. PUSH
   - Push signed image to registry (OCI distribution)
   - Tag with semantic version + Git SHA
   - Update image manifest list (multi-arch)

5. DEPLOY
   - Apply deployment strategy (rolling/blue-green/canary)
   - Progressive traffic shifting
   - Health check validation

6. VALIDATE
   - Smoke tests against deployed version
   - Integration test suite
   - Canary analysis (if applicable)
   - SLO/SLI verification

7. ROLLBACK (on failure)
   - Revert to previous known-good version
   - Restore traffic routing
   - Alert and incident creation
```

---

## 2. Deployment Strategies

### 2.1 Rolling Update

The default Kubernetes deployment strategy. Gradually replaces old pods with new ones while maintaining availability.

#### Kubernetes Deployment Spec

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: fizzbuzz-deployment
spec:
  replicas: 3
  revisionHistoryLimit: 10          # Old ReplicaSets retained for rollback (default: 10)
  progressDeadlineSeconds: 600      # Max time for progress before failure (default: 600)
  minReadySeconds: 0                # Min seconds pod must be ready (default: 0)
  paused: false                     # Pause rollout for batch changes (default: false)
  selector:
    matchLabels:
      app: fizzbuzz
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1                   # Max pods above desired count during update
      maxUnavailable: 1             # Max pods that can be unavailable during update
  template:
    metadata:
      labels:
        app: fizzbuzz
    spec:
      terminationGracePeriodSeconds: 30
      containers:
      - name: fizzbuzz
        image: fizzbuzz:1.0.0
        ports:
        - containerPort: 8080
```

#### Key Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `maxSurge` | int or % | 25% | Maximum pods created above desired count during update |
| `maxUnavailable` | int or % | 25% | Maximum pods unavailable during update |
| `minReadySeconds` | int | 0 | Minimum seconds a pod must be ready before considered available |
| `progressDeadlineSeconds` | int | 600 | Maximum seconds for deployment to make progress |
| `revisionHistoryLimit` | int | 10 | Number of old ReplicaSets retained for rollback |
| `terminationGracePeriodSeconds` | int | 30 | Grace period before forceful pod termination |

#### Zero-Downtime Configuration

```yaml
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxSurge: 1
    maxUnavailable: 0    # All existing pods remain until new ones are ready
```

Setting `maxUnavailable: 0` ensures all existing pods remain running until new pods pass readiness checks, guaranteeing continuous availability.

#### Rollback Operations

```bash
# View rollout history
kubectl rollout history deployment/fizzbuzz-deployment

# View specific revision
kubectl rollout history deployment/fizzbuzz-deployment --revision=2

# Rollback to previous revision
kubectl rollout undo deployment/fizzbuzz-deployment

# Rollback to specific revision
kubectl rollout undo deployment/fizzbuzz-deployment --to-revision=2

# Pause rollout (apply multiple changes before resuming)
kubectl rollout pause deployment/fizzbuzz-deployment

# Resume paused rollout
kubectl rollout resume deployment/fizzbuzz-deployment
```

#### Proportional Scaling

When a rolling update is in progress and the deployment is scaled, the controller proportionally distributes new replicas across the old and new ReplicaSets based on existing replica counts.

#### Deployment Status Conditions

| Condition | Status | Meaning |
|-----------|--------|---------|
| `Progressing` | `True` | New ReplicaSet being rolled out or scaling |
| `Progressing` | `True`, reason `NewReplicaSetAvailable` | Rollout complete |
| `Progressing` | `False` | Exceeded `progressDeadlineSeconds` |
| `Available` | `True` | Minimum available replicas met |

#### Pod-Template-Hash Label

Every ReplicaSet and its pods receive an automatically generated `pod-template-hash` label (e.g., `pod-template-hash: 75675f5897`) computed from the pod template spec. This prevents hash collisions between ReplicaSets.

### 2.2 Blue-Green Deployment

Maintains two identical environments (blue = current, green = new). Traffic switches atomically after validation.

#### Sequence

```
1. Blue environment serves all production traffic
2. Deploy new version to Green environment
3. Run validation/smoke tests against Green
4. Switch load balancer / service selector to Green
5. Green now serves all production traffic
6. Blue retained as instant rollback target
7. After confidence period, decommission Blue
```

#### Implementation in Kubernetes

Blue-green can be implemented using Kubernetes Services with label selectors:

```yaml
# Service points to active version via selector
apiVersion: v1
kind: Service
metadata:
  name: fizzbuzz
spec:
  selector:
    app: fizzbuzz
    version: green    # Switch between "blue" and "green"
  ports:
  - port: 80
    targetPort: 8080
```

Traffic switching is achieved by updating the Service selector from `version: blue` to `version: green`.

#### Argo Rollouts Blue-Green Spec

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: fizzbuzz-rollout
spec:
  strategy:
    blueGreen:
      activeService: fizzbuzz-active       # Production traffic
      previewService: fizzbuzz-preview     # Preview/test traffic
      autoPromotionEnabled: false          # Require manual promotion
      scaleDownDelaySeconds: 30            # Delay before scaling down old version
      prePromotionAnalysis:                # Run analysis before promotion
        templates:
        - templateName: success-rate
      postPromotionAnalysis:               # Run analysis after promotion
        templates:
        - templateName: error-rate
```

#### Trade-offs

| Advantage | Disadvantage |
|-----------|--------------|
| Instant rollback (switch selector back) | Requires 2x resources during deployment |
| Zero-downtime guaranteed | Database schema changes require coordination |
| Full validation before traffic switch | Not suitable for stateful workloads |
| Simple mental model | Cost of maintaining two environments |

### 2.3 Canary Deployment

Gradually shifts traffic to a new version while monitoring key metrics. Automated analysis determines whether to proceed or roll back.

#### Argo Rollouts Canary Spec

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: fizzbuzz-rollout
spec:
  replicas: 10
  strategy:
    canary:
      maxSurge: "25%"            # Max replicas above desired during update
      maxUnavailable: 0          # No unavailable pods
      canaryService: fizzbuzz-canary
      stableService: fizzbuzz-stable
      dynamicStableScale: true   # Scale down stable as canary scales up
      canaryMetadata:
        labels:
          role: canary
      stableMetadata:
        labels:
          role: stable
      steps:
      - setWeight: 10            # 10% traffic to canary
      - pause: { duration: 5m }  # Wait 5 minutes
      - analysis:                # Run automated analysis
          templates:
          - templateName: success-rate
      - setWeight: 25            # 25% traffic
      - pause: { duration: 10m }
      - setWeight: 50            # 50% traffic
      - pause: { duration: 10m }
      - setWeight: 75            # 75% traffic
      - pause: { duration: 10m }
      # Implicit 100% after all steps
      trafficRouting:
        nginx:
          stableIngress: fizzbuzz-ingress
```

#### Canary Step Types

| Step | Description |
|------|-------------|
| `setWeight` | Sets percentage of traffic routed to canary |
| `pause` | Halts progression; with `duration` (auto-resume) or indefinite (manual promote) |
| `setCanaryScale` | Controls canary replica count independently of traffic weight |
| `analysis` | Runs inline AnalysisRun; blocks until complete |

#### setCanaryScale Modes

| Field | Description |
|-------|-------------|
| `replicas` | Explicit pod count for canary |
| `weight` | Percentage of total `spec.replicas` |
| `matchTrafficWeight` | Boolean; aligns replica count with `setWeight` value |

#### AnalysisTemplate and AnalysisRun

```yaml
apiVersion: argoproj.io/v1alpha1
kind: AnalysisTemplate
metadata:
  name: success-rate
spec:
  metrics:
  - name: success-rate
    interval: 60s
    count: 5
    successCondition: result[0] >= 0.95
    failureLimit: 3
    provider:
      prometheus:
        address: http://prometheus:9090
        query: |
          sum(rate(http_requests_total{status=~"2.*",app="fizzbuzz",role="canary"}[5m]))
          /
          sum(rate(http_requests_total{app="fizzbuzz",role="canary"}[5m]))
```

**Analysis Patterns:**

| Pattern | Behavior |
|---------|----------|
| **Inline Analysis** | AnalysisRun starts at the step and blocks until complete |
| **Background Analysis** | AnalysisRun starts at beginning and runs throughout rollout |
| **Pre-Promotion Analysis** | Runs before traffic switch (blue-green) |
| **Post-Promotion Analysis** | Runs after traffic switch to validate |

**AnalysisRun Outcomes:**

| Result | Effect on Rollout |
|--------|-------------------|
| Successful | Rollout proceeds to next step |
| Failed | Rollout is aborted; canary scaled to zero |
| Inconclusive | Rollout pauses; requires manual decision |

#### Traffic Routing Providers

Argo Rollouts supports traffic management through: Istio, NGINX Ingress, AWS ALB, Ambassador, Apache APISIX, Traefik, and SMI (Service Mesh Interface).

### 2.4 Recreate Strategy

Terminates all existing pods before creating new ones. Results in downtime but guarantees no version overlap.

```yaml
spec:
  strategy:
    type: Recreate
```

**Use cases:** Single-instance databases, applications that cannot tolerate running two versions simultaneously, or applications with exclusive resource locks.

---

## 3. Docker Compose Specification

### 3.1 Service Definition

Docker Compose uses a declarative YAML format to define multi-container applications. The Compose specification defines services, networks, volumes, and their relationships.

### 3.2 depends_on — Service Dependencies

Controls startup and shutdown order with health-aware conditions.

#### Short Syntax

```yaml
services:
  web:
    depends_on:
      - db
      - redis
```

Only ensures containers start in order; does not wait for readiness.

#### Long Syntax

```yaml
services:
  web:
    depends_on:
      db:
        condition: service_healthy     # Wait for healthcheck to pass
        restart: true                  # Restart if dependency restarts
        required: true                 # Fail if dependency unavailable (default)
      migrations:
        condition: service_completed_successfully  # Wait for exit code 0
```

#### Condition Values

| Condition | Description |
|-----------|-------------|
| `service_started` | Default. Container has started (no readiness check). |
| `service_healthy` | Container has started AND passed its healthcheck. Requires `healthcheck` defined on the dependency. |
| `service_completed_successfully` | Container has run to completion with exit code 0. For one-shot jobs (migrations, seed scripts). |

#### Additional Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `restart` | bool | `false` | Restart this service when dependency is updated/restarted |
| `required` | bool | `true` | If `false`, only warn when dependency unavailable |

### 3.3 Networks

```yaml
services:
  web:
    networks:
      frontend:
        aliases:
          - webapp              # Alternative hostnames
        ipv4_address: 172.16.238.10  # Static IP
        mac_address: "02:42:ac:11:00:02"
        interface_name: eth0
        gw_priority: 100        # Selects default gateway (highest wins)
        priority: 1000           # Connection order
      backend:
        aliases:
          - api

networks:
  frontend:
    driver: bridge
    driver_opts:
      com.docker.network.bridge.name: br-frontend
  backend:
    driver: bridge
    internal: true              # No external connectivity
```

#### Network Properties

| Property | Description |
|----------|-------------|
| `aliases` | Alternative hostnames reachable on this network |
| `ipv4_address` / `ipv6_address` | Static IP assignment |
| `mac_address` | MAC address for the container's network interface |
| `interface_name` | Name of the network interface |
| `link_local_ips` | List of link-local IP addresses |
| `driver_opts` | Driver-specific key-value options |
| `gw_priority` | Controls which network provides the default gateway (highest wins) |
| `priority` | Connection order (does not affect default gateway) |

If `networks` is omitted, containers connect to an implicit `default` bridge network.

### 3.4 Volumes

#### Short Syntax

```yaml
services:
  web:
    volumes:
      - ./data:/app/data:ro           # Bind mount (read-only)
      - db-data:/var/lib/postgresql    # Named volume
      - /tmp:/tmp:rw                   # Bind mount (read-write, default)
```

Access mode flags: `rw` (read-write, default), `ro` (read-only), `z` (shared SELinux label), `Z` (private SELinux label).

#### Long Syntax

```yaml
services:
  web:
    volumes:
      - type: volume
        source: db-data
        target: /var/lib/postgresql
        read_only: false
        volume:
          nocopy: false          # Disable data copying from container
          subpath: pg_data       # Mount specific subdirectory
      - type: bind
        source: ./config
        target: /app/config
        read_only: true
        bind:
          propagation: rprivate  # Bind propagation mode
          create_host_path: true # Auto-create directory (default: true)
      - type: tmpfs
        target: /tmp
        tmpfs:
          size: 67108864         # Size in bytes (64MB)
          mode: 1777             # Unix permission bits (octal)
```

#### Volume Types

| Type | Description |
|------|-------------|
| `volume` | Named volume managed by Docker |
| `bind` | Host filesystem path mounted into container |
| `tmpfs` | Temporary in-memory filesystem |
| `image` | Content from a container image |
| `npipe` | Named pipe (Windows) |
| `cluster` | Cluster-wide volume |

### 3.5 Restart Policies

```yaml
services:
  web:
    restart: unless-stopped
```

| Policy | Behavior |
|--------|----------|
| `no` | Never restart (default) |
| `always` | Always restart until container is removed |
| `on-failure[:max-retries]` | Restart on non-zero exit code; optional retry limit |
| `unless-stopped` | Always restart except when explicitly stopped |

### 3.6 Variable Interpolation

Compose processes `$VARIABLE` and `${VARIABLE}` syntax in YAML values.

```yaml
services:
  web:
    image: ${REGISTRY:-docker.io}/${IMAGE_NAME}:${TAG:-latest}
    environment:
      DB_HOST: ${DB_HOST:?Database host is required}
      API_KEY: ${API_KEY:-default_key}
```

#### Interpolation Syntax

| Syntax | Behavior |
|--------|----------|
| `${VAR}` | Substitute variable value |
| `${VAR:-default}` | Use default if VAR is unset or empty |
| `${VAR-default}` | Use default only if VAR is unset |
| `${VAR:+replacement}` | Use replacement if VAR is set and non-empty |
| `${VAR+replacement}` | Use replacement if VAR is set |
| `${VAR:?error}` | Error with message if VAR is unset or empty |
| `${VAR?error}` | Error with message if VAR is unset |
| `$$` | Literal dollar sign (escape) |

#### Environment Variable Precedence (highest wins)

1. Variables from `docker compose run -e`
2. Variables from shell environment
3. Variables from `environment` key in Compose file
4. Variables from `--env-file` flag
5. Variables from `env_file` key in Compose file
6. Variables from `.env` file in project directory

#### env_file Configuration

```yaml
services:
  web:
    env_file:
      - path: ./common.env
        required: true          # Fail if missing (default)
      - path: ./local.env
        required: false         # Warn if missing
        format: raw             # Prevent interpolation
```

Files are processed top-to-bottom; later values override earlier ones for the same variable.

### 3.7 Healthcheck

```yaml
services:
  db:
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "postgres"]
      interval: 30s            # Time between checks
      timeout: 10s             # Maximum time for a single check
      retries: 3               # Consecutive failures before unhealthy
      start_period: 40s        # Grace period during startup
      start_interval: 5s       # Check interval during start_period
      disable: false           # Set true to disable inherited healthcheck
```

#### Test Formats

| Format | Description |
|--------|-------------|
| `["CMD", "executable", "arg1"]` | Execute command directly |
| `["CMD-SHELL", "command string"]` | Execute via shell (`/bin/sh -c`) |
| `["NONE"]` | Disable healthcheck |
| `"command string"` | Shorthand for CMD-SHELL |

---

## 4. Kubernetes CRI (Container Runtime Interface)

### 4.1 CRI Protocol Overview

The Container Runtime Interface (CRI) is a plugin interface that enables the kubelet to use a wide variety of container runtimes without needing to recompile. CRI defines two gRPC services communicated over Unix domain sockets:

| Service | Responsibility |
|---------|---------------|
| **RuntimeService** | Pod sandbox lifecycle, container lifecycle, exec/attach/port-forward |
| **ImageService** | Image pull, inspect, remove, list |

### 4.2 RuntimeService gRPC Methods

#### Pod Sandbox Lifecycle

```protobuf
service RuntimeService {
    rpc RunPodSandbox(RunPodSandboxRequest) returns (RunPodSandboxResponse) {}
    rpc StopPodSandbox(StopPodSandboxRequest) returns (StopPodSandboxResponse) {}
    rpc RemovePodSandbox(RemovePodSandboxRequest) returns (RemovePodSandboxResponse) {}
    rpc PodSandboxStatus(PodSandboxStatusRequest) returns (PodSandboxStatusResponse) {}
    rpc ListPodSandbox(ListPodSandboxRequest) returns (ListPodSandboxResponse) {}
}
```

#### Container Lifecycle

```protobuf
service RuntimeService {
    rpc CreateContainer(CreateContainerRequest) returns (CreateContainerResponse) {}
    rpc StartContainer(StartContainerRequest) returns (StartContainerResponse) {}
    rpc StopContainer(StopContainerRequest) returns (StopContainerResponse) {}
    rpc RemoveContainer(RemoveContainerRequest) returns (RemoveContainerResponse) {}
    rpc ListContainers(ListContainersRequest) returns (ListContainersResponse) {}
    rpc ContainerStatus(ContainerStatusRequest) returns (ContainerStatusResponse) {}
}
```

#### Interactive Operations

```protobuf
service RuntimeService {
    rpc ExecSync(ExecSyncRequest) returns (ExecSyncResponse) {}
    rpc Exec(ExecRequest) returns (ExecResponse) {}
    rpc Attach(AttachRequest) returns (AttachResponse) {}
    rpc PortForward(PortForwardRequest) returns (PortForwardResponse) {}
}
```

### 4.3 ImageService gRPC Methods

```protobuf
service ImageService {
    rpc ListImages(ListImagesRequest) returns (ListImagesResponse) {}
    rpc ImageStatus(ImageStatusRequest) returns (ImageStatusResponse) {}
    rpc PullImage(PullImageRequest) returns (PullImageResponse) {}
    rpc RemoveImage(RemoveImageRequest) returns (RemoveImageResponse) {}
    rpc ImageFsInfo(ImageFsInfoRequest) returns (ImageFsInfoResponse) {}
}
```

### 4.4 Kubelet-to-Containerd Call Flow

When the scheduler assigns a pod to a node, the kubelet initiates the following CRI call sequence:

```
Pod Creation Sequence:
=====================

1. RunPodSandbox
   ├─ Create Linux namespaces (PID, NET, IPC, UTS, MNT)
   ├─ Start sandbox container (pause container)
   ├─ Call CNI plugin: ADD
   │   ├─ Create veth pair
   │   ├─ Attach to pod network namespace
   │   ├─ Assign IP address (IPAM plugin)
   │   └─ Configure routes and DNS
   └─ Return sandbox ID

2. For each init container (sequential):
   ├─ PullImage (if imagePullPolicy requires it)
   ├─ CreateContainer (within sandbox)
   ├─ StartContainer
   ├─ Wait for container to exit successfully (exit code 0)
   └─ RemoveContainer

3. For each regular container (parallel):
   ├─ PullImage (if imagePullPolicy requires it)
   ├─ CreateContainer (within sandbox)
   ├─ StartContainer
   ├─ Execute postStart lifecycle hook
   └─ Begin probe checks (startup → liveness + readiness)

4. For each sidecar container (restartPolicy: Always):
   ├─ PullImage (if imagePullPolicy requires it)
   ├─ CreateContainer (within sandbox)
   ├─ StartContainer
   └─ Runs for pod lifetime (restarts on failure)

Pod Termination Sequence:
=========================

1. For each container:
   ├─ Execute preStop lifecycle hook
   ├─ Send SIGTERM
   ├─ Wait terminationGracePeriodSeconds
   ├─ Send SIGKILL (if still running)
   ├─ StopContainer
   └─ RemoveContainer

2. StopPodSandbox
   ├─ Call CNI plugin: DEL
   │   ├─ Remove network configuration
   │   └─ Release IP address
   └─ Stop sandbox container

3. RemovePodSandbox
   └─ Clean up sandbox resources
```

### 4.5 Image Pull Policies

| Policy | Behavior |
|--------|----------|
| `Always` | Always pull the image from the registry, even if cached locally. Ensures latest version. |
| `IfNotPresent` | Pull only if the image is not already on the node. Default for tagged images (not `:latest`). |
| `Never` | Never pull from registry. Use only locally cached images. Fails if image is not present. |

#### Default Policy Selection

- If `imagePullPolicy` is omitted and tag is `:latest` or omitted → `Always`
- If `imagePullPolicy` is omitted and tag is specified (not `:latest`) → `IfNotPresent`
- If image uses a digest (`@sha256:...`) → `IfNotPresent`

#### Registry Authentication

```yaml
spec:
  imagePullSecrets:
  - name: regcred          # kubernetes.io/dockerconfigjson Secret
  containers:
  - name: app
    image: private-registry.io/app:1.0
```

Multiple `imagePullSecrets` can be specified; each credential matching the registry is tried in order.

### 4.6 Init Container Lifecycle

Init containers run sequentially before any regular containers start. Each must complete successfully (exit code 0) before the next begins.

```yaml
spec:
  initContainers:
  - name: init-db-schema
    image: flyway:latest
    command: ["flyway", "migrate"]
  - name: init-cache-warm
    image: app:latest
    command: ["warm-cache"]
  containers:
  - name: app
    image: app:latest
```

**Key properties:**
- Run to completion sequentially; each must exit 0
- Do not support `lifecycle`, `livenessProbe`, `readinessProbe`, or `startupProbe`
- Restart according to pod's `restartPolicy`
- Changes to init container spec trigger pod recreation

### 4.7 Sidecar Containers (Kubernetes 1.28+)

Sidecar containers have `restartPolicy: Always` and run for the pod's lifetime alongside regular containers.

```yaml
spec:
  initContainers:
  - name: log-agent
    image: fluent-bit:latest
    restartPolicy: Always    # Makes this a sidecar
  containers:
  - name: app
    image: app:latest
```

**Key properties:**
- Start before regular containers
- Run for pod lifetime (not sequential like init containers)
- Support startup and liveness probes (but not readiness probes)
- Restart on failure

### 4.8 Probes — Readiness, Liveness, and Startup

#### Probe Mechanisms

**HTTP GET Probe:**
```yaml
livenessProbe:
  httpGet:
    path: /healthz
    port: 8080
    httpHeaders:
    - name: X-Custom-Header
      value: Awesome
    scheme: HTTPS             # HTTP or HTTPS
```
Success: HTTP response code 200-399.

**TCP Socket Probe:**
```yaml
readinessProbe:
  tcpSocket:
    port: 5432
```
Success: TCP connection established.

**Exec Probe:**
```yaml
livenessProbe:
  exec:
    command:
    - cat
    - /tmp/healthy
```
Success: Command exits with code 0.

**gRPC Probe:**
```yaml
livenessProbe:
  grpc:
    port: 50051
    service: my.health.v1.Health   # Optional service name
```
Success: gRPC health check returns `SERVING`.

#### Probe Configuration Fields

| Field | Default | Description |
|-------|---------|-------------|
| `initialDelaySeconds` | 0 | Seconds to wait after container start before first probe |
| `periodSeconds` | 10 | How often to perform the probe |
| `timeoutSeconds` | 1 | Seconds after which probe times out |
| `successThreshold` | 1 | Consecutive successes to mark as healthy |
| `failureThreshold` | 3 | Consecutive failures before taking action |
| `terminationGracePeriodSeconds` | (pod default) | Override grace period when liveness probe fails |

#### Probe Behavior Summary

| Probe Type | On Failure | On Success |
|------------|------------|------------|
| **Startup** | Container killed (subject to restartPolicy). Blocks liveness/readiness until it succeeds. | Liveness and readiness probes activated. |
| **Liveness** | Container killed and restarted (subject to restartPolicy). | No action. |
| **Readiness** | Pod removed from Service EndpointSlices (no traffic). | Pod added to Service EndpointSlices. |

#### Slow-Starting Container Pattern

```yaml
startupProbe:
  httpGet:
    path: /healthz
    port: 8080
  failureThreshold: 30     # 30 * 10s = 300s max startup time
  periodSeconds: 10
livenessProbe:
  httpGet:
    path: /healthz
    port: 8080
  failureThreshold: 3
  periodSeconds: 10
```

The startup probe runs first. Until it succeeds, liveness and readiness probes are disabled. This prevents slow-starting applications from being killed during initialization.

---

## 5. Chaos Engineering

### 5.1 Chaos Mesh

Chaos Mesh is a Cloud Native Computing Foundation (CNCF) project for chaos engineering on Kubernetes. It uses CustomResourceDefinitions (CRDs) to define experiments declaratively.

#### Fault Type Catalog

| CRD | Description | Actions/Capabilities |
|-----|-------------|---------------------|
| **PodChaos** | Pod-level failure injection | `pod-kill`, `pod-failure`, `container-kill` |
| **NetworkChaos** | Network failure simulation | Latency, packet loss, packet disorder, packet duplication, bandwidth throttling, network partition |
| **StressChaos** | Resource pressure simulation | CPU stress, memory pressure |
| **IOChaos** | Disk I/O failure injection | I/O delays, read/write failures, attribute override |
| **TimeChaos** | Clock skew simulation | Time offset injection |
| **DNSChaos** | DNS resolution failure | DNS lookup failure, wrong IP address returned |
| **HTTPChaos** | HTTP communication tampering | Request/response latency, abort, body/header modification |
| **KernelChaos** | Kernel-level fault injection | Memory allocation failures, kernel fault injection |
| **JVMChaos** | JVM application faults | Method delay, exception injection, GC pressure |
| **AWSChaos** | AWS infrastructure faults | EC2 stop/restart, detach volume |
| **GCPChaos** | GCP infrastructure faults | Instance stop/restart |

#### PodChaos Specification

```yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: PodChaos
metadata:
  name: pod-kill-example
spec:
  action: pod-kill              # pod-kill | pod-failure | container-kill
  mode: one                     # one | all | fixed | fixed-percent | random-max-percent
  value: ""                     # Parameter for mode (e.g., "50" for fixed-percent)
  selector:
    namespaces:
    - production
    labelSelectors:
      app: fizzbuzz
  containerNames: []            # Required for container-kill
  gracePeriod: 0                # Seconds before pod deletion (pod-kill only)
  duration: "30s"               # Experiment duration
```

#### Mode Selection

| Mode | Behavior |
|------|----------|
| `one` | Select one random pod from matched set |
| `all` | Target all matched pods |
| `fixed` | Select exact count specified in `value` |
| `fixed-percent` | Select percentage of matched pods (value: "50" = 50%) |
| `random-max-percent` | Select up to percentage of matched pods randomly |

#### NetworkChaos Specification

```yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: network-partition
spec:
  action: partition             # partition | delay | loss | duplicate | corrupt | bandwidth
  mode: all
  selector:
    namespaces:
    - production
    labelSelectors:
      app: fizzbuzz-api
  direction: both               # to | from | both
  target:
    selector:
      namespaces:
      - production
      labelSelectors:
        app: fizzbuzz-db
  duration: "60s"
```

**NetworkChaos Actions:**

| Action | Parameters |
|--------|------------|
| `delay` | `latency`, `jitter`, `correlation` |
| `loss` | `loss` (percentage), `correlation` |
| `duplicate` | `duplicate` (percentage), `correlation` |
| `corrupt` | `corrupt` (percentage), `correlation` |
| `partition` | Complete network isolation between targets |
| `bandwidth` | `rate`, `limit`, `buffer` |

#### StressChaos Specification

```yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: StressChaos
metadata:
  name: cpu-stress
spec:
  mode: one
  selector:
    namespaces:
    - production
    labelSelectors:
      app: fizzbuzz
  stressors:
    cpu:
      workers: 4                # Number of CPU stress workers
      load: 80                  # Target CPU load percentage
    memory:
      workers: 2                # Number of memory stress workers
      size: "256MB"             # Memory consumption per worker
  duration: "5m"
```

#### Chaos Mesh Workflow (Multi-Step Experiments)

```yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: Workflow
metadata:
  name: game-day-scenario
spec:
  entry: game-day
  templates:
  - name: game-day
    templateType: Serial
    children:
    - network-delay
    - pod-kill-and-stress
  - name: network-delay
    templateType: NetworkChaos
    networkChaos:
      action: delay
      mode: one
      selector: { ... }
      delay:
        latency: "200ms"
      duration: "2m"
  - name: pod-kill-and-stress
    templateType: Parallel
    children:
    - kill-api
    - stress-db
  - name: kill-api
    templateType: PodChaos
    podChaos:
      action: pod-kill
      mode: one
      selector: { ... }
  - name: stress-db
    templateType: StressChaos
    stressChaos:
      stressors:
        cpu:
          workers: 2
          load: 90
      duration: "3m"
```

**Workflow Template Types:**

| Type | Description |
|------|-------------|
| `Serial` | Execute children sequentially |
| `Parallel` | Execute children concurrently |
| `Suspend` | Wait for specified duration |
| `Task` | Execute external task |
| `PodChaos`, `NetworkChaos`, etc. | Chaos experiment leaf nodes |

### 5.2 LitmusChaos

LitmusChaos is a cloud-native chaos engineering platform that provides a framework for managing, executing, and observing chaos experiments.

#### Core Custom Resources

| CRD | Description |
|-----|-------------|
| **ChaosExperiment** | Defines the experiment type, parameters, and target |
| **ChaosEngine** | Links a workload to one or more ChaosExperiments |
| **ChaosResult** | Records experiment outcomes, probe results, and verdict |

#### ChaosEngine Specification

```yaml
apiVersion: litmuschaos.io/v1alpha1
kind: ChaosEngine
metadata:
  name: fizzbuzz-chaos
spec:
  appinfo:
    appns: production
    applabel: app=fizzbuzz
    appkind: deployment
  engineState: active           # active | stop
  chaosServiceAccount: litmus-admin
  experiments:
  - name: pod-delete
    spec:
      probe:
      - name: check-api-health
        type: httpProbe
        httpProbe/inputs:
          url: http://fizzbuzz:8080/health
          expectedResponseCode: "200"
        mode: Continuous         # SOT | EOT | Edge | Continuous | OnChaos
        runProperties:
          probeTimeout: 5s
          interval: 10s
          retry: 3
      components:
        env:
        - name: TOTAL_CHAOS_DURATION
          value: "30"
        - name: CHAOS_INTERVAL
          value: "10"
        - name: FORCE
          value: "false"
```

#### Litmus Probes

Probes validate steady-state hypotheses during chaos experiments:

| Probe Type | Description |
|------------|-------------|
| **httpProbe** | Makes HTTP calls; validates response code and body |
| **cmdProbe** | Executes commands; validates exit code and output |
| **k8sProbe** | Checks Kubernetes resource state |
| **promProbe** | Queries Prometheus; validates metric values |

#### Probe Modes

| Mode | When Probe Runs |
|------|----------------|
| `SOT` | Start of Test — before chaos injection |
| `EOT` | End of Test — after chaos completes |
| `Edge` | Both SOT and EOT |
| `Continuous` | Throughout the experiment at regular intervals |
| `OnChaos` | Only during the chaos injection period |

#### ChaosResult Fields

| Field | Description |
|-------|-------------|
| `verdict` | `Pass`, `Fail`, or `Awaited` |
| `probeSuccessPercentage` | Ratio of successful probe checks to total probes |
| `failStep` | Phase where failure occurred |
| `phase` | `Running`, `Completed`, or `Aborted` |

### 5.3 Game Day Orchestration

A game day is a structured chaos engineering session that tests system resilience under controlled conditions.

#### Game Day Protocol

```
1. DEFINE SCOPE
   ├─ Identify target systems and blast radius
   ├─ Define steady-state hypothesis
   ├─ Set abort criteria
   └─ Notify all stakeholders

2. ESTABLISH BASELINE
   ├─ Record current SLI/SLO metrics
   ├─ Verify monitoring and alerting
   ├─ Confirm rollback procedures
   └─ Run pre-flight probe checks

3. INJECT FAULTS
   ├─ Start with smallest blast radius
   ├─ Apply fault injection (single or multi-step)
   ├─ Monitor steady-state hypothesis
   └─ Record observations

4. OBSERVE AND ANALYZE
   ├─ Compare observed vs expected behavior
   ├─ Track recovery time
   ├─ Note any cascading failures
   └─ Document unexpected behaviors

5. REMEDIATE AND RECOVER
   ├─ Remove fault injection
   ├─ Verify system returns to steady state
   ├─ If system does not recover, execute rollback
   └─ Confirm all SLIs restored

6. POST-MORTEM
   ├─ Compile findings
   ├─ Identify resilience gaps
   ├─ Create action items
   └─ Update runbooks
```

#### Blast Radius Limiting

| Technique | Description |
|-----------|-------------|
| **Namespace isolation** | Restrict chaos to specific namespaces |
| **Label selectors** | Target only pods matching specific labels |
| **Mode control** | Use `one` or `fixed-percent` instead of `all` |
| **Duration limits** | Set explicit `duration` on all experiments |
| **Abort conditions** | Define automatic abort when metrics exceed thresholds |
| **RBAC scoping** | Limit chaos service account permissions |
| **Network policies** | Prevent chaos from affecting external systems |

### 5.4 Steady-State Hypothesis

The steady-state hypothesis defines the expected normal behavior of the system. Chaos experiments verify whether the system maintains this steady state under fault conditions.

```
Hypothesis Template:
"Given [system state], when [fault injected], then [observable metric]
 remains within [acceptable range] within [time window]."

Example:
"Given the FizzBuzz API is serving traffic, when 1 of 3 API pods
 is killed, then p99 response latency remains below 500ms and
 error rate stays below 1% within 60 seconds."
```

---

## 6. Container Observability

### 6.1 cAdvisor — cgroup Metrics Collection

cAdvisor (Container Advisor) is an open-source daemon built by Google that reads Linux cgroup accounting data and translates it into Prometheus-format metrics. It is embedded in the kubelet and runs on every node.

#### How cAdvisor Collects Metrics

```
Linux Kernel cgroup filesystem
  └─ /sys/fs/cgroup/
      ├─ cpu/                    # CPU accounting
      ├─ memory/                 # Memory accounting
      ├─ blkio/                  # Block I/O accounting
      └─ net_cls/                # Network classification
          │
          └─ cAdvisor reads these files directly
              │
              └─ Translates to Prometheus metrics
                  │
                  └─ Exposed on :8080/metrics (or kubelet :10250/metrics/cadvisor)
```

#### CPU Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `container_cpu_usage_seconds_total` | counter | Cumulative CPU time consumed per CPU in seconds |
| `container_cpu_system_seconds_total` | counter | Cumulative system CPU time consumed in seconds |
| `container_cpu_user_seconds_total` | counter | Cumulative user CPU time consumed in seconds |
| `machine_cpu_cores` | gauge | Number of CPU cores on the machine |

#### Memory Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `container_memory_usage_bytes` | gauge | Current memory usage in bytes (includes cache) |
| `container_memory_working_set_bytes` | gauge | Current working set in bytes (active memory) |
| `container_memory_rss` | gauge | Size of RSS (resident set size) in bytes |
| `container_memory_cache` | gauge | Number of bytes of page cache memory |
| `container_memory_failcnt` | counter | Memory limit hit count |
| `container_memory_failures_total` | counter | Cumulative memory allocation failures |
| `machine_memory_bytes` | gauge | Total memory installed on the machine |

#### Network Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `container_network_receive_bytes_total` | counter | Cumulative bytes received |
| `container_network_receive_errors_total` | counter | Cumulative receive errors |
| `container_network_receive_packets_total` | counter | Cumulative packets received |
| `container_network_receive_packets_dropped_total` | counter | Cumulative packets dropped on receive |
| `container_network_transmit_bytes_total` | counter | Cumulative bytes transmitted |
| `container_network_transmit_errors_total` | counter | Cumulative transmit errors |
| `container_network_transmit_packets_total` | counter | Cumulative packets transmitted |
| `container_network_transmit_packets_dropped_total` | counter | Cumulative packets dropped on transmit |

#### Filesystem Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `container_fs_usage_bytes` | gauge | Current filesystem consumption |
| `container_fs_limit_bytes` | gauge | Maximum filesystem capacity |
| `container_fs_reads_total` | counter | Cumulative reads completed |
| `container_fs_writes_total` | counter | Cumulative writes completed |
| `container_fs_io_current` | gauge | Number of I/Os currently in progress |
| `container_fs_io_time_seconds_total` | counter | Total time spent on I/O operations |
| `container_fs_io_time_weighted_seconds_total` | counter | Cumulative weighted I/O time |

#### cgroup v1 vs v2 Differences

| Aspect | cgroup v1 | cgroup v2 |
|--------|-----------|-----------|
| **Hierarchy** | Multiple hierarchies per subsystem | Single unified hierarchy |
| **Memory root** | `memory.usage_in_bytes` exists for root | `memory.current` does not exist for root |
| **CPU throttling** | `container_cpu_cfs_throttled_*` available | Not available |
| **Process metrics** | Full set available | Some metrics missing |

### 6.2 Fluent Bit — Log Aggregation

Fluent Bit is a lightweight, high-performance log processor and forwarder. It runs as a DaemonSet on every Kubernetes node.

#### Architecture

```
Container stdout/stderr
  └─ containerd writes to /var/log/containers/*.log
      │
      └─ Fluent Bit Tail Input Plugin
          ├─ Reads log files
          ├─ Applies CRI parser (timestamp, stream, flags, log)
          └─ Handles multiline (F=Full, P=Partial)
              │
              └─ Kubernetes Filter Plugin
                  ├─ Extracts pod_name, namespace from file path
                  ├─ Queries K8s API for metadata
                  │   ├─ Pod labels
                  │   ├─ Pod annotations
                  │   ├─ Container name
                  │   ├─ Container ID
                  │   └─ Namespace labels
                  ├─ Caches API responses (configurable TTL)
                  └─ Enriches log record with metadata
                      │
                      └─ Output Plugin
                          ├─ Elasticsearch / OpenSearch
                          ├─ Grafana Loki
                          ├─ Kafka
                          ├─ HTTP / HTTPS
                          ├─ S3 / Cloud storage
                          └─ stdout (debug)
```

#### Pipeline Components

| Component | Role |
|-----------|------|
| **Input** | Data sources: `tail` (file), `systemd` (journal), `tcp`, `http`, `forward` |
| **Parser** | Line-level parsing: `json`, `regex`, `logfmt`, `docker`, `cri` |
| **Filter** | Record transformation: `kubernetes` (metadata), `modify`, `grep`, `lua`, `multiline` |
| **Output** | Destinations: `es`, `loki`, `kafka`, `http`, `s3`, `forward`, `stdout` |
| **Buffer** | In-memory or filesystem buffering for backpressure handling |

#### CRI Log Format

```
2026-03-24T10:15:30.123456789Z stdout F This is a complete log line
2026-03-24T10:15:30.123456789Z stderr P This is a partial
2026-03-24T10:15:30.223456789Z stderr F log line continued
```

| Field | Description |
|-------|-------------|
| Timestamp | RFC3339Nano format |
| Stream | `stdout` or `stderr` |
| Flag | `F` (full/final line) or `P` (partial, more to follow) |
| Log | The actual log content |

#### Kubernetes Metadata Enrichment

The Kubernetes filter enriches records with:

```json
{
  "kubernetes": {
    "pod_name": "fizzbuzz-api-7b5c4d6e8f-x2k9m",
    "namespace_name": "production",
    "pod_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "container_name": "fizzbuzz",
    "container_image": "fizzbuzz:1.0.0",
    "container_hash": "sha256:abc123...",
    "host": "node-01",
    "labels": {
      "app": "fizzbuzz",
      "version": "1.0.0"
    },
    "annotations": {
      "prometheus.io/scrape": "true"
    }
  }
}
```

### 6.3 Distributed Tracing Across Container Boundaries

#### OpenTelemetry Context Propagation

Distributed tracing requires trace context to flow across process boundaries, including container-to-container and service-to-service calls.

#### W3C Trace Context Standard

The W3C Trace Context specification defines two HTTP headers for propagation:

**traceparent header:**
```
traceparent: {version}-{trace-id}-{parent-span-id}-{trace-flags}
             00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01

version:        2 hex digits (00)
trace-id:       32 hex characters (globally unique trace identifier)
parent-span-id: 16 hex characters (immediate parent span)
trace-flags:    2 hex digits (01 = sampled)
```

**tracestate header:**
```
tracestate: vendor1=value1,vendor2=value2
```
Carries vendor-specific trace data alongside the standard context.

#### Context Propagation Flow Across Containers

```
Container A (Service 1)                Container B (Service 2)
┌─────────────────────┐                ┌─────────────────────┐
│ Create root span     │                │                     │
│ spanId: aaa111       │                │                     │
│                      │  HTTP request  │                     │
│ Inject context ──────┼──────────────►│ Extract context      │
│ traceparent:         │  Headers:      │ Create child span   │
│   00-trace1-aaa111-01│  traceparent   │ parentId: aaa111    │
│                      │  tracestate    │ spanId: bbb222      │
│                      │                │                     │
│                      │  HTTP response │                     │
│ Record response ◄────┼───────────────│ End child span      │
│ End root span        │                │                     │
└─────────────────────┘                └─────────────────────┘
```

#### Propagation Across Messaging Systems

For asynchronous communication (Kafka, RabbitMQ, etc.), trace context is injected into message headers rather than HTTP headers, maintaining the trace chain across container boundaries even in event-driven architectures.

#### Observability Stack Integration

| Component | Role | Tool Examples |
|-----------|------|---------------|
| **Metrics** | Numeric time-series data | Prometheus, cAdvisor |
| **Logs** | Structured event records | Fluent Bit → Loki/Elasticsearch |
| **Traces** | Request flow across services | OpenTelemetry → Jaeger/Tempo |
| **Correlation** | Links metrics, logs, traces via trace ID | OpenTelemetry Collector, Grafana |

### 6.4 Container Diagnostics

#### kubectl exec — Remote Command Execution

```bash
# Execute command in running container
kubectl exec -it pod-name -- /bin/sh

# Execute in specific container within multi-container pod
kubectl exec -it pod-name -c container-name -- /bin/sh

# Non-interactive command execution
kubectl exec pod-name -- ps aux
kubectl exec pod-name -- cat /proc/1/status
```

**CRI flow for exec:**
1. kubelet receives exec request via API server
2. kubelet calls `RuntimeService.Exec()` or `RuntimeService.ExecSync()` on CRI
3. CRI runtime (containerd) enters container's namespaces
4. Command is executed within the container's PID/mount/network namespace
5. stdout/stderr streamed back to client

#### Ephemeral Debug Containers

Kubernetes ephemeral containers (stable since 1.25) allow adding a debug container to a running pod without modifying its spec or restarting it.

```bash
# Add debug container to running pod
kubectl debug -it pod-name --image=busybox --target=app-container

# Debug with process namespace sharing
kubectl debug -it pod-name --image=nicolaka/netshoot --target=app-container

# Create a copy of the pod with modified command
kubectl debug pod-name -it --copy-to=debug-pod --container=app -- sh
```

**Key capabilities:**
- Access to pod's network namespace (same IP, same ports)
- Process namespace sharing via `--target` flag (see processes in other containers)
- Full diagnostic toolkit (netshoot, busybox) without modifying production images
- Cannot be removed once added; persist until pod deletion
- No resource guarantees; use already-allocated pod resources

#### Container Diff and Snapshot

```bash
# Compare container filesystem to its image
docker diff container-id
# Output:
# A /tmp/new-file          (Added)
# C /etc/config            (Changed)
# D /var/log/old.log       (Deleted)

# Export container filesystem
docker export container-id > snapshot.tar

# Inspect container metadata
docker inspect container-id
kubectl describe pod pod-name

# View container process tree
docker top container-id
kubectl exec pod-name -- ps -efH
```

#### Container Resource Inspection

```bash
# View container resource usage
kubectl top pod pod-name --containers

# View pod events and conditions
kubectl describe pod pod-name

# View container logs
kubectl logs pod-name -c container-name --previous  # Previous instance
kubectl logs pod-name -c container-name --since=1h  # Last hour
kubectl logs pod-name -c container-name -f           # Follow/stream
```

---

## Implementation Implications for Enterprise FizzBuzz

### Deployment Pipeline Module (FizzDeploy)

The research identifies the following data structures and patterns for a deployment pipeline implementation:

1. **Pipeline Stage Model**: Sequential stage execution with pass/fail gates, matching Spinnaker's stage catalog
2. **Strategy Abstraction**: Rolling, Blue-Green, Canary, Recreate as pluggable strategy implementations
3. **Analysis Framework**: AnalysisTemplate/AnalysisRun pattern from Argo Rollouts for automated deployment validation
4. **GitOps Reconciliation Loop**: Continuous desired-vs-live state comparison with drift detection

### Compose Orchestration Module (FizzCompose)

1. **Dependency Graph**: `depends_on` with health-aware conditions (`service_started`, `service_healthy`, `service_completed_successfully`)
2. **Network Topology**: Multi-network configuration with aliases, static IPs, and gateway priority
3. **Volume Management**: Bind mounts, named volumes, tmpfs with access mode controls
4. **Variable Interpolation Engine**: Shell-style `${VAR:-default}` syntax with precedence chain

### Container Orchestrator Upgrade (FizzKubeV2)

1. **CRI gRPC Protocol**: Full RuntimeService and ImageService method sets
2. **Pod Lifecycle**: RunPodSandbox → Init containers → Sidecar containers → Regular containers
3. **Probe System**: HTTP, TCP, Exec, gRPC probes with startup/liveness/readiness semantics
4. **Image Pull Policies**: Always/IfNotPresent/Never with registry authentication

### Chaos Engineering Module (FizzContainerChaos)

1. **Fault Type Catalog**: PodChaos, NetworkChaos, StressChaos, IOChaos, TimeChaos, DNSChaos, HTTPChaos, KernelChaos
2. **Targeting Modes**: one, all, fixed, fixed-percent, random-max-percent
3. **Workflow Engine**: Serial and Parallel composition of chaos experiments
4. **Steady-State Hypothesis**: Probe-based validation (HTTP, cmd, k8s, Prometheus)
5. **Blast Radius Controls**: Namespace isolation, label selectors, mode limits, duration caps, RBAC

### Observability Module (FizzContainerOps)

1. **Metrics Collection**: cAdvisor-style cgroup reading for CPU, memory, network, filesystem
2. **Log Pipeline**: Input → Parser → Filter → Buffer → Output architecture
3. **Trace Propagation**: W3C traceparent/tracestate injection and extraction
4. **Diagnostics**: Exec, ephemeral debug containers, diff, process tree, resource inspection
