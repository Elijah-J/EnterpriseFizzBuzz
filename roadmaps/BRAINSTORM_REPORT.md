# Enterprise FizzBuzz Platform -- Brainstorm Report v16

**Date:** 2026-03-23
**Status:** COMPLETE -- All 7 Ideas Implemented

> *"The Enterprise FizzBuzz Platform has 109 infrastructure modules. They are orchestrated by FizzKube -- a container orchestrator modeled after Kubernetes, with pods, deployments, replica sets, horizontal pod autoscalers, and a scheduler that evaluates node affinity, resource requests, and anti-affinity constraints. FizzKube schedules workloads into pods. Those pods are Python dataclass instances. They have no process isolation. They share the host's PID namespace, network stack, mount table, IPC channels, and user credentials. They have no resource limits -- a pod that consumes unbounded memory will consume the host's memory, because there are no cgroups. They have no filesystem isolation -- a pod that writes to `/tmp` writes to the host's `/tmp`, because there is no overlay filesystem. They have no container images -- a pod's 'image' is a string that resolves to a Python import path. There is no registry, no image pull, no layer caching, no content-addressable storage. FizzKube is a meticulous simulation of container orchestration semantics applied to bare function calls. It schedules nothing into isolation. It orchestrates nothing into containers. Every pod in the cluster runs in the same process, the same namespace, the same address space. The platform has built a TCP/IP stack, a DNS server, a virtual filesystem, a memory allocator, a capability security model, a process migration system, an IPC framework, a bootloader, and a reverse proxy. It has everything a container runtime needs except the container runtime. FizzKube is an orchestrator for containers that do not exist. Round 16 builds the containers."*

---

## Previously Completed

For context, the following brainstorm rounds have been fully implemented and shipped:

- **Round 1**: Formal Verification & Proof System, FizzBuzz-as-a-Service (FBaaS), Time-Travel Debugger, Custom Bytecode VM, Cost-Based Query Optimizer, Distributed Paxos Consensus
- **Round 2**: Load Testing Framework, Audit Dashboard, GitOps Configuration-as-Code, Graph Database, Natural Language Query Interface, Genetic Algorithm
- **Round 3**: Quantum Computing Simulator, Cross-Compiler (Wasm/C/Rust), Federated Learning, Knowledge Graph & Domain Ontology, Self-Modifying Code, Compliance Chatbot
- **Round 4**: OS Kernel (process scheduling, virtual memory, interrupts), Peer-to-Peer Gossip Network (SWIM, Kademlia DHT, Merkle anti-entropy), Digital Twin, FizzLang DSL, Recommendation Engine, Archaeological Recovery
- **Round 5**: Dependent Type System & Curry-Howard Proof Engine, FizzKube Container Orchestration, FizzPM Package Manager, FizzDAP Debug Adapter Protocol Server, FizzSQL Relational Query Engine, FizzBuzz IP Office & Trademark Registry
- **Round 6**: FizzLock Distributed Lock Manager, FizzCDC Change Data Capture, FizzBill API Monetization, FizzNAS Neural Architecture Search, FizzCorr Observability Correlation Engine, FizzJIT Runtime Code Generation
- **Round 7**: FizzCap Capability-Based Security, FizzOTel OpenTelemetry Tracing, FizzWAL Write-Ahead Intent Log, FizzCRDT Conflict-Free Replicated Data Types, FizzGrammar Formal Grammar & Parser Generator, FizzAlloc Memory Allocator & Garbage Collector
- **Round 8**: FizzColumn Columnar Storage Engine, FizzReduce MapReduce Framework, FizzSchema Schema Evolution, FizzSLI Service Level Indicators, FizzCheck Formal Model Checking, FizzProxy Reverse Proxy & Load Balancer
- **Round 9**: FizzTrace Ray Tracer, FizzFold Protein Folding, FizzNet TCP/IP Stack, FizzSynth Audio Synthesizer, FizzVFS Virtual File System, FizzVCS Version Control System
- **Round 10**: FizzELF Binary Generator, FizzReplica Database Replication, FizzZ Z Notation Specification, FizzMigrate Live Process Migration, FizzFlame Flame Graph Generator, FizzProve Automated Theorem Prover
- **Round 11**: FizzShader GPU Shader Compiler, FizzContract Smart Contract VM, FizzDNS Authoritative DNS Server, FizzSheet Spreadsheet Engine, FizzTPU Neural Network Accelerator, FizzRegex Regular Expression Engine
- **Round 12**: (6 features implemented)
- **Round 13**: FizzGIS Spatial Database, FizzClock Clock Synchronization, FizzCPU Pipeline Simulator, FizzBoot x86 Bootloader, FizzCodec Video Codec, FizzPrint Typesetting Engine
- **Round 14**: FizzGC Garbage Collector, FizzIPC Microkernel IPC, FizzGate Digital Logic Simulator, FizzPDF PDF Document Generator, FizzASM Two-Pass Assembler, FizzHTTP2 HTTP/2 Protocol
- **Round 15**: FizzBob Operator Cognitive Load Engine, FizzApproval Multi-Party Approval Workflow, FizzPager Incident Paging & Escalation, FizzSuccession Operator Succession Planning, FizzPerf Operator Performance Review, FizzOrg Organizational Hierarchy Engine

The platform now stands at 300,000+ lines across 289 files with ~11,400 tests. Every subsystem is technically faithful and production-grade. Round 16 is THE CONTAINER RUNTIME SUPERCYCLE. FizzKube has been orchestrating dataclass instances since Round 5. It schedules pods that share every resource with their host. It enforces resource quotas that no cgroup accounting validates. It manages replica sets of Python objects that could not be isolated from each other even if isolation were attempted. The orchestrator exists. The containers do not. This round builds them.

---

## Theme: The Container Runtime Supercycle

FizzKube was introduced in Round 5 as a container orchestration platform inspired by Kubernetes. It implements the full control plane: an API server, an etcd-backed state store, a scheduler with predicate/priority scoring, a controller manager running reconciliation loops for Deployments, ReplicaSets, and HPAs, and a kubelet agent that manages pod lifecycle. It is a faithful implementation of Kubernetes semantics. But those semantics terminate at the pod boundary. When FizzKube "creates a container," it instantiates a Python dataclass. When it "mounts a volume," it sets a dictionary key. When it "isolates a network namespace," it does nothing, because there are no namespaces. The gap between what FizzKube promises and what the runtime delivers is the gap between an orchestrator and the infrastructure it orchestrates.

Real container runtimes are built on a stack of Linux kernel primitives and OCI standards: namespaces provide isolation (PID, NET, MNT, UTS, IPC, USER, CGROUP), cgroups provide resource accounting and limiting, overlay filesystems provide copy-on-write image layers, the OCI runtime spec defines container lifecycle, the OCI image spec defines image format, the OCI distribution spec defines registry APIs, and CNI defines container networking. Above these primitives sits a high-level daemon (containerd) that manages images, snapshots, and container tasks, exposing a CRI (Container Runtime Interface) that the orchestrator calls.

The Enterprise FizzBuzz Platform has the orchestrator. It has the kernel (OS Kernel module with process scheduling and virtual memory). It has the filesystem (FizzVFS). It has the network stack (FizzNet TCP/IP). It has the IPC framework (FizzIPC Mach-style ports). It has the memory allocator (FizzAlloc). It has the capability security model (FizzCap). It has the process migration system (FizzMigrate). It has the reverse proxy (FizzProxy). It has everything a container runtime needs -- scattered across a dozen modules that have never been composed into an actual container runtime. Round 16 composes them.

---

## Idea 1: FizzNS -- Linux Namespace Isolation Engine ✅ DONE

### The Problem

Linux namespaces are the foundational isolation mechanism of every container runtime. Introduced incrementally between Linux 2.4.19 (mount namespaces, 2002) and Linux 4.6 (cgroup namespaces, 2016), namespaces partition kernel resources so that processes inside a namespace see an isolated view of the system. PID namespaces give each container its own process ID space -- PID 1 inside the container is not PID 1 on the host. NET namespaces give each container its own network stack -- interfaces, routing tables, iptables rules, and port bindings. MNT namespaces isolate the mount table so a container's filesystem mounts are invisible to the host. UTS namespaces isolate hostname and domain name. IPC namespaces isolate System V IPC objects and POSIX message queues. USER namespaces map container UIDs to host UIDs, enabling unprivileged container operation. CGROUP namespaces virtualize the cgroup hierarchy so a container sees only its own cgroup subtree.

The Enterprise FizzBuzz Platform has an OS Kernel module that manages processes and virtual memory. It has FizzVFS for filesystem operations. It has FizzNet for TCP/IP networking. It has FizzIPC for inter-process communication. It has FizzCap for capability-based security. But none of these modules provide namespace isolation. When FizzKube schedules two pods on the same node, both pods see the same PID table, the same network interfaces, the same mount table, the same hostname, the same IPC channels, and the same user credentials. There is no isolation boundary. The `clone()` and `unshare()` system calls that real container runtimes use to create namespaces have no equivalent in the platform. Without namespace isolation, containers are indistinguishable from regular processes -- which is precisely what FizzKube's pods currently are.

### The Vision

A comprehensive Linux namespace isolation engine implementing all seven namespace types as first-class primitives, following the semantics of the Linux kernel's `clone(2)` and `unshare(2)` system calls. Each namespace type provides isolated views of the corresponding kernel resource. Namespaces support hierarchical nesting (a namespace can be created inside another namespace), reference counting (namespaces persist as long as at least one process or bind-mount holds a reference), and cross-namespace operations (processes can enter or leave namespaces via `setns(2)` semantics). The engine integrates with the platform's existing kernel, filesystem, network, IPC, and security modules to provide genuine resource partitioning.

### Key Components

- **`fizzns.py`** (~3,000 lines): FizzNS Linux Namespace Isolation Engine
- **Namespace Type System**: An enum and abstract base for all seven namespace types:
  - **`NamespaceType` enum**: `PID`, `NET`, `MNT`, `UTS`, `IPC`, `USER`, `CGROUP` -- the seven Linux namespace types, each mapping to the corresponding `CLONE_NEW*` flag (`CLONE_NEWPID`, `CLONE_NEWNET`, `CLONE_NEWNS`, `CLONE_NEWUTS`, `CLONE_NEWIPC`, `CLONE_NEWUSER`, `CLONE_NEWCGROUP`)
  - **`Namespace` ABC**: abstract base with `ns_id` (unique identifier), `ns_type` (NamespaceType), `parent` (enclosing namespace or None for root), `children` (nested namespaces), `ref_count` (number of processes and bind-mounts referencing this namespace), `created_at` timestamp, and abstract methods `isolate(process)`, `enter(process)`, `leave(process)`, `destroy()`
  - **`NamespaceSet`**: a frozenset of namespaces (one per type) that collectively define a container's isolation boundary. Containers are created with a `NamespaceSet` specifying which namespace types to isolate and which to share with the parent
- **PID Namespace**: Isolated process ID spaces:
  - **`PIDNamespace`**: maintains its own PID allocation table, starting from PID 1. The first process in a new PID namespace becomes the init process (PID 1) for that namespace. PID 1 inherits orphaned processes within the namespace. If PID 1 exits, all processes in the namespace receive SIGKILL. PIDs are visible hierarchically: a parent PID namespace can see child PIDs (mapped to the parent's PID space), but child namespaces cannot see parent PIDs
  - **Integration with OS Kernel**: the kernel's process scheduler is extended to support PID namespace-scoped process tables. `getpid()` returns the namespace-relative PID. `getppid()` returns the namespace-relative parent PID. Process signals are namespace-aware
- **NET Namespace**: Isolated network stacks:
  - **`NETNamespace`**: each network namespace has its own set of network interfaces, IP addresses, routing table, iptables rules, and socket bindings. A new NET namespace starts with only a loopback interface. Connectivity to external networks requires a virtual ethernet (veth) pair bridging the namespace to the host or another namespace
  - **Integration with FizzNet**: the TCP/IP stack is extended to scope socket operations to the active network namespace. `bind()`, `listen()`, `connect()`, and `accept()` operate within the calling process's NET namespace. Two processes in different NET namespaces can both bind to port 80 without conflict
- **MNT Namespace**: Isolated mount tables:
  - **`MNTNamespace`**: each mount namespace has its own mount table. Mounts performed inside a MNT namespace are invisible to the parent. The initial mount table is a copy of the parent's mount table at creation time. `pivot_root()` semantics allow replacing the namespace's root filesystem entirely -- the mechanism containers use to switch from the host root to the container's rootfs
  - **Integration with FizzVFS**: the virtual filesystem dispatches mount operations through the active MNT namespace. `mount()`, `umount()`, and `pivot_root()` are namespace-scoped
- **UTS Namespace**: Isolated hostname and domain name:
  - **`UTSNamespace`**: each UTS namespace has its own `hostname` and `domainname`. Containers can set their hostname without affecting the host or other containers. The `sethostname()` and `setdomainname()` calls are namespace-scoped
- **IPC Namespace**: Isolated IPC resources:
  - **`IPCNamespace`**: isolates System V IPC objects (shared memory segments, semaphore sets, message queues) and POSIX message queues. Each IPC namespace has its own IPC identifier space
  - **Integration with FizzIPC**: Mach-style port operations are scoped to the active IPC namespace. Ports created in one IPC namespace are invisible to processes in other IPC namespaces
- **USER Namespace**: UID/GID mapping:
  - **`USERNamespace`**: maps UIDs and GIDs between the namespace and its parent. A process can be root (UID 0) inside a USER namespace while being an unprivileged user on the host. The mapping is defined by `uid_map` and `gid_map` entries. USER namespaces are the foundation of rootless containers
  - **Integration with FizzCap**: capability bounding sets are namespace-scoped. A process gains full capabilities inside its USER namespace but retains only mapped capabilities in the parent namespace
- **CGROUP Namespace**: Virtualized cgroup view:
  - **`CGROUPNamespace`**: virtualizes the cgroup hierarchy so that a process in a CGROUP namespace sees its own cgroup as the root. This prevents containers from discovering or manipulating the host's cgroup tree
  - **Integration with FizzCgroup** (Feature 2): the cgroup controller's hierarchy is filtered through the active CGROUP namespace
- **Namespace Manager**: Lifecycle management for all namespace types:
  - **`NamespaceManager`**: singleton managing the global namespace registry. Creates namespaces (`clone` semantics -- create with new child process), shares namespaces (`unshare` semantics -- move calling process into a new namespace), and enters namespaces (`setns` semantics -- move calling process into an existing namespace). Tracks reference counts and garbage-collects unreferenced namespaces. Provides namespace-to-process mapping for the `/proc` equivalent
- **FizzNS Middleware**: `FizzNSMiddleware` integrates with the middleware pipeline, ensuring that each FizzBuzz evaluation is associated with the correct namespace set for the container it runs in
- **CLI Flags**: `--fizzns`, `--fizzns-list` (list all active namespaces), `--fizzns-inspect <ns_id>` (show namespace details and member processes), `--fizzns-hierarchy` (ASCII tree of nested namespaces), `--fizzns-type <type>` (filter by namespace type)

### Why This Is Necessary

Because namespace isolation is the defining characteristic that separates a container from a process. Without namespaces, FizzKube's pods are processes that happen to have metadata attached. With namespaces, they become isolated execution environments with their own PID space, network stack, mount table, hostname, IPC channels, user mapping, and cgroup view. Every container runtime -- Docker, containerd, CRI-O, Podman, LXC -- depends on Linux namespaces as the primary isolation mechanism. The OCI runtime specification (v1.0.2, Section 4) requires namespace configuration in `config.json`. A container runtime without namespace support is not a container runtime. It is a process launcher with aspirations.

### Estimated Scale

~3,000 lines of namespace isolation engine, ~400 lines of namespace type system (enum, abstract base, NamespaceSet), ~400 lines of PID namespace (PID table, init process, hierarchical visibility, signal scoping), ~350 lines of NET namespace (interface isolation, routing table, socket scoping, veth placeholder), ~300 lines of MNT namespace (mount table copy, pivot_root, mount propagation), ~150 lines of UTS namespace (hostname/domainname isolation), ~200 lines of IPC namespace (IPC ID space isolation, FizzIPC integration), ~250 lines of USER namespace (UID/GID mapping, capability scoping), ~200 lines of CGROUP namespace (hierarchy virtualization), ~350 lines of NamespaceManager (lifecycle, reference counting, GC, registry), ~200 lines of middleware and CLI integration, ~400 tests. Total: ~5,200 lines.

---

## Idea 2: FizzCgroup -- Control Group Resource Accounting & Limiting ✅ DONE

### The Problem

Linux control groups (cgroups) are the resource accounting and limiting mechanism used by every container runtime to enforce resource boundaries. Introduced in Linux 2.6.24 (2008) and redesigned as cgroups v2 in Linux 4.5 (2016), cgroups organize processes into hierarchical groups and apply controllers that track and limit resource usage -- CPU time, memory, I/O bandwidth, process count, and more. Without cgroups, a container has no resource boundaries. A containerized process that enters an infinite loop will consume 100% of a CPU core indefinitely. A containerized process that allocates memory without bound will exhaust the host's RAM and trigger the host OOM killer, potentially terminating unrelated containers. A containerized process that spawns thousands of child processes will exhaust the host's PID table.

FizzKube models resource requests and limits in its PodSpec. The scheduler considers resource requests when placing pods on nodes. The HPA (Horizontal Pod Autoscaler) reads resource utilization to make scaling decisions. But these resource values are advisory metadata. Nothing enforces them. A pod that declares `resources.limits.cpu: "500m"` can consume any amount of CPU, because there is no cgroup controller backing the limit. A pod that declares `resources.limits.memory: "256Mi"` can allocate any amount of memory, because there is no memory controller enforcing the cap. FizzKube's resource model is a type system without a runtime -- it describes constraints that nothing checks.

### The Vision

A complete cgroups v2 implementation following the Linux kernel's unified hierarchy model. Every container gets a cgroup node in a hierarchical tree. Controllers are attached at each node to account for and limit resource consumption. The CPU controller implements CFS bandwidth throttling (quota/period) and relative shares. The memory controller tracks RSS, cache, and swap usage with configurable limits and a per-cgroup OOM killer. The I/O controller throttles read/write bandwidth per device. The PIDs controller caps the number of processes. All controllers feed real-time metrics that FizzKube's HPA consumes for autoscaling decisions, replacing the simulated utilization values currently used.

### Key Components

- **`fizzcgroup.py`** (~2,800 lines): FizzCgroup Control Group Resource Accounting & Limiting Engine
- **Cgroup Hierarchy**: The unified v2 hierarchy tree:
  - **`CgroupNode`**: a node in the cgroup tree with `cgroup_id`, `name`, `path` (slash-separated from root, e.g., `/fizzkube/pod-abc/container-main`), `parent`, `children`, `controllers` (set of enabled controllers), `processes` (set of process IDs assigned to this cgroup), `subtree_control` (controllers delegated to children), and `events` (notification channel for resource limit breaches). Nodes form a single rooted tree following the cgroups v2 "unified hierarchy" model -- no multiple hierarchies, no per-controller trees
  - **`CgroupHierarchy`**: manages the tree. Operations: `create(path)`, `remove(path)`, `attach(process, path)`, `migrate(process, from_path, to_path)`. Removal requires that the cgroup has no child cgroups and no attached processes. Process attachment moves the process from its current cgroup to the target cgroup. The root cgroup (`/`) always exists and cannot be removed
  - **Delegation**: parent cgroups control which controllers are available to children via the `subtree_control` file equivalent. A controller must be enabled in `subtree_control` before children can use it. This prevents leaf cgroups from enabling controllers that their ancestors have not authorized
- **CPU Controller**: Processor time accounting and throttling:
  - **`CPUController`**: implements two complementary mechanisms:
    - **CPU shares** (`cpu.weight`): relative weight (1-10000, default 100) determining the proportion of CPU time a cgroup receives under contention. A cgroup with weight 200 gets twice the CPU time of a cgroup with weight 100 when both are competing for the same core. Non-contended cgroups can use all available CPU regardless of weight
    - **CPU bandwidth** (`cpu.max`): absolute limit specified as `quota` (microseconds of CPU time) per `period` (microseconds). A quota of 50000 per period of 100000 limits the cgroup to 50% of one CPU core. A quota of 200000 per period of 100000 allows up to 2 cores. Setting quota to "max" (unbounded) disables bandwidth limiting
  - **CPU accounting**: tracks `usage_usec` (total CPU time consumed), `user_usec` (user-mode time), `system_usec` (kernel-mode time), `nr_periods` (number of elapsed periods), `nr_throttled` (periods where the cgroup was throttled), `throttled_usec` (total time spent throttled). These metrics are exposed to the SLA monitoring subsystem and FizzKube HPA
  - **Integration with OS Kernel**: the kernel's CFS (Completely Fair Scheduler) consults cgroup CPU weights and bandwidth limits when scheduling processes. Throttled processes are placed in a throttled runqueue until the next period begins
- **Memory Controller**: Memory accounting, limiting, and OOM management:
  - **`MemoryController`**: tracks and limits memory usage:
    - **Accounting**: `current` (total memory usage), `rss` (anonymous memory), `cache` (page cache), `swap` (swap usage), `kernel` (kernel memory charged to this cgroup). Accounting is recursive -- a parent cgroup's usage includes all descendants
    - **Limits**: `memory.max` (hard limit -- allocations beyond this trigger OOM), `memory.high` (throttle threshold -- processes are throttled when usage exceeds this, encouraging reclaim), `memory.low` (best-effort protection -- memory below this threshold is protected from reclaim under host memory pressure), `memory.min` (hard protection -- memory below this is never reclaimed)
    - **Swap**: `swap.max` limits swap usage independently of memory limits. `swap.current` tracks current swap consumption
  - **`OOMKiller`**: triggered when a cgroup's memory usage reaches `memory.max` and cannot be reduced by reclaim. The OOM killer selects a process within the cgroup (using an `oom_score` heuristic based on memory usage, process age, and priority) and terminates it. OOM events are recorded in the cgroup's event log and propagated to FizzPager for alerting. The OOM killer operates within cgroup scope -- it only considers processes in the offending cgroup, never spilling to the host or other cgroups
  - **Integration with FizzAlloc**: the memory allocator's `malloc`/`free` operations are cgroup-aware. Each allocation is charged to the calling process's cgroup. Allocations that would exceed the cgroup's `memory.max` fail with ENOMEM (or trigger OOM, depending on configuration)
- **I/O Controller**: Block device bandwidth throttling:
  - **`IOController`**: throttles read and write bandwidth per block device:
    - **Bandwidth limits**: `io.max` specifies per-device limits as `rbps` (read bytes/sec), `wbps` (write bytes/sec), `riops` (read ops/sec), `wiops` (write ops/sec). Processes exceeding limits are throttled (I/O calls sleep until bandwidth is available)
    - **Weight-based allocation**: `io.weight` (1-10000) determines proportional I/O bandwidth under contention, analogous to CPU weights
    - **Accounting**: `io.stat` tracks per-device `rbytes`, `wbytes`, `rios`, `wios` for monitoring and capacity planning
  - **Integration with FizzVFS**: filesystem I/O operations pass through the I/O controller for throttling and accounting before reaching the virtual block device layer
- **PIDs Controller**: Process count limiting:
  - **`PIDsController`**: limits the number of processes (including threads) in a cgroup via `pids.max`. Prevents fork bombs from exhausting the host's PID table. `pids.current` tracks the current count. Attempts to exceed the limit fail with EAGAIN
  - **Integration with OS Kernel**: `fork()` and `clone()` calls consult the PIDs controller before creating new processes
- **Resource Accountant**: Aggregated resource reporting:
  - **`ResourceAccountant`**: reads all controller metrics for a cgroup and produces a `ResourceReport` summarizing CPU utilization (percentage of quota), memory utilization (percentage of limit), I/O throughput, and process count. Reports are generated on demand and at configurable intervals for time-series monitoring
  - **Integration with FizzKube HPA**: the HPA's metrics source is updated to read from `ResourceAccountant` instead of simulated values, enabling autoscaling decisions based on actual cgroup-reported resource utilization
  - **Integration with SLA Monitoring**: cgroup resource metrics are exposed as SLIs. Error budgets can be defined against cgroup utilization thresholds (e.g., "container memory utilization must not exceed 90% for more than 5 minutes in a 30-day window")
- **FizzCgroup Middleware**: `FizzCgroupMiddleware` integrates with the middleware pipeline. Each FizzBuzz evaluation's resource consumption (CPU time, memory allocated) is charged to the cgroup of the container executing it
- **CLI Flags**: `--fizzcgroup`, `--fizzcgroup-tree` (display cgroup hierarchy), `--fizzcgroup-stats <path>` (resource stats for a cgroup), `--fizzcgroup-limit <path>:<controller>:<param>=<value>` (set resource limits), `--fizzcgroup-top` (real-time resource usage by cgroup, sorted by CPU or memory)

### Why This Is Necessary

Because resource limits without enforcement are suggestions, and suggestions do not prevent outages. FizzKube already defines resource requests and limits in its PodSpec -- this is the contract between the workload and the orchestrator. But a contract without enforcement is a gentleman's agreement. Cgroups provide the enforcement mechanism that transforms FizzKube's resource specifications from advisory metadata into hard guarantees. Without cgroups, a single misbehaving container can consume all available CPU, memory, or I/O bandwidth, starving every other container on the node. The Kubernetes documentation states: "If you do not specify a memory limit for a container, the container has no upper bound on the amount of memory it can use." FizzKube has been operating in this unbounded mode since Round 5. Every container on the platform runs without resource limits. FizzCgroup closes this gap.

### Estimated Scale

~2,800 lines of cgroup engine, ~350 lines of hierarchy management (CgroupNode, CgroupHierarchy, delegation, subtree_control), ~500 lines of CPU controller (shares, bandwidth, CFS integration, accounting, throttling), ~500 lines of memory controller (accounting, limits, high/low/min thresholds, swap), ~300 lines of OOM killer (process selection, scoped OOM, event propagation), ~300 lines of I/O controller (bandwidth limits, weight, accounting, FizzVFS integration), ~200 lines of PIDs controller (process counting, fork gating), ~350 lines of ResourceAccountant and integrations (HPA, SLA monitoring, metrics), ~200 lines of middleware and CLI, ~400 tests. Total: ~5,400 lines.

---

## Idea 3: FizzOCI -- OCI-Compliant Container Runtime ✅ DONE

### The Problem

The Open Container Initiative (OCI) runtime specification (v1.0.2) defines a standard interface for container runtimes. It specifies the container lifecycle (Creating -> Created -> Running -> Stopped), the bundle format (a directory containing `config.json` and a root filesystem), the configuration schema (process parameters, root filesystem, mounts, Linux-specific settings including namespaces, cgroups, seccomp, and capabilities), and the operations a runtime must support (`create`, `start`, `kill`, `delete`, `state`). Every major container runtime implements this specification: runc (the reference implementation), crun, youki, gVisor's runsc, and Kata Containers' runtime-rs. The OCI runtime spec is the contract between the high-level container manager (containerd, CRI-O) and the low-level runtime that actually creates containers.

The Enterprise FizzBuzz Platform has namespace isolation (FizzNS, Feature 1) and resource limiting (FizzCgroup, Feature 2), but no component that composes these primitives into a container according to the OCI specification. There is no `config.json` parser. There is no bundle format. There is no container lifecycle state machine. There is no container creation procedure that sets up namespaces, configures cgroups, mounts filesystems, drops capabilities, applies seccomp filters, and executes the container's entrypoint process. FizzNS and FizzCgroup are raw building materials. FizzOCI is the construction foreman that assembles them into a container.

### The Vision

A low-level OCI-compliant container runtime -- the platform's equivalent of runc. Given an OCI runtime bundle (config.json + rootfs directory), FizzOCI creates a container by parsing the configuration, setting up the specified namespaces, configuring cgroup limits, preparing the root filesystem, mounting specified paths, configuring seccomp syscall filters, dropping capabilities to the specified bounding set, executing lifecycle hooks (prestart, createRuntime, createContainer, startContainer, poststart, poststop), and launching the container's entrypoint process. The runtime implements the five OCI operations and maintains container state across transitions.

### Key Components

- **`fizzoci.py`** (~3,200 lines): FizzOCI OCI-Compliant Container Runtime
- **OCI Configuration Parser**: Full parsing of the OCI runtime spec `config.json`:
  - **`OCIConfig`**: dataclass representing the complete OCI configuration with fields for:
    - `oci_version` (semver string, e.g., "1.0.2")
    - `root` (`OCIRoot` -- `path` to rootfs, `readonly` flag)
    - `mounts` (list of `MountSpec` -- `destination`, `type`, `source`, `options`)
    - `process` (`ContainerProcess` -- `terminal`, `user` (UID/GID/additional GIDs), `args` (entrypoint command), `env` (environment variables), `cwd`, `capabilities` (bounding/effective/inheritable/permitted/ambient sets), `rlimits` (list of resource limits: RLIMIT_NOFILE, RLIMIT_NPROC, etc.), `noNewPrivileges` flag, `apparmor_profile`, `selinux_label`)
    - `hostname` (string -- sets the UTS namespace hostname)
    - `linux` (`LinuxConfig` -- `namespaces` (list of namespace types to create or join), `cgroup_path`, `resources` (CPU/memory/IO/PIDs limits mapped to FizzCgroup controllers), `seccomp` (syscall filter profile), `rootfs_propagation` (mount propagation mode), `masked_paths` (paths nullified inside the container), `readonly_paths` (paths made read-only), `devices` (device allowlist))
    - `hooks` (`ContainerHooks` -- see below)
    - `annotations` (arbitrary key-value metadata)
  - **Schema validation**: the parser validates the configuration against the OCI runtime spec JSON schema, reporting detailed errors for missing required fields, type mismatches, and constraint violations
- **Container Lifecycle State Machine**: The four OCI states and transitions:
  - **`OCIState` enum**: `CREATING`, `CREATED`, `RUNNING`, `STOPPED`
  - **`OCIContainer`**: the runtime representation of a container, with `container_id` (unique string), `state` (OCIState), `pid` (process ID of the container's init process, namespace-relative), `bundle_path` (path to the OCI bundle), `config` (parsed OCIConfig), `namespace_set` (NamespaceSet from FizzNS), `cgroup_path` (FizzCgroup node path), `created_at`, `started_at`, `stopped_at`, `exit_code`, and `annotations`
  - **State transitions**:
    - `create(bundle_path, container_id)`: parses config.json, creates namespaces (per `linux.namespaces`), creates cgroup node (per `linux.cgroup_path`), configures cgroup resource limits (per `linux.resources`), prepares root filesystem (per `root`), processes mounts (per `mounts`), masks and read-only-ifies specified paths, applies device allowlist, executes `createRuntime` and `createContainer` hooks, creates the container process in the new namespaces (but does not start user code). State: CREATING -> CREATED
    - `start(container_id)`: executes `startContainer` hook, then starts the container's entrypoint process (per `process.args`). The entrypoint runs inside the configured namespaces with the specified UID/GID, capabilities, environment, working directory, and rlimits. Executes `poststart` hook. State: CREATED -> RUNNING
    - `kill(container_id, signal)`: sends the specified signal to the container's init process. If the signal is SIGKILL or SIGTERM, the runtime waits for the process to exit and collects the exit code. State: RUNNING -> STOPPED (after process exit)
    - `delete(container_id)`: cleans up container resources -- destroys namespaces, removes cgroup node, unmounts filesystems, deletes bundle state. Executes `poststop` hook. Only permitted when state is STOPPED. After deletion, the container ID is released
    - `state(container_id)`: returns the container's current state as a JSON-serializable `OCIStateReport` with `oci_version`, `id`, `status`, `pid`, `bundle`, `annotations`, and `created` timestamp
- **Seccomp Profiles**: Syscall filtering for container security:
  - **`SeccompProfile`**: defines a syscall allowlist/denylist using the Linux seccomp-bpf framework semantics. The profile specifies a `default_action` (SCMP_ACT_ALLOW, SCMP_ACT_ERRNO, SCMP_ACT_KILL, etc.) and a list of `rules`, each matching syscall names with optional argument conditions. The default profile for FizzBuzz containers allows the syscalls required for FizzBuzz evaluation and denies everything else. The platform's seccomp implementation validates profiles against the OCI seccomp schema and applies them at container creation time
  - **Predefined profiles**: `DEFAULT` (permissive -- blocks dangerous syscalls like `reboot`, `kexec_load`, `mount`), `STRICT` (minimal -- allows only read/write/exit/sigreturn and the FizzBuzz evaluation syscalls), `UNCONFINED` (no filtering)
- **Lifecycle Hooks**: Extensible container lifecycle callbacks:
  - **`ContainerHooks`**: six hook points defined by the OCI spec: `prestart` (deprecated but supported), `createRuntime` (after runtime creates container but before `pivot_root`), `createContainer` (after `pivot_root` but before user process), `startContainer` (before starting user process inside container), `poststart` (after user process starts), `poststop` (after container stops and before `delete` completes). Each hook specifies a `path` (executable), `args`, `env`, and `timeout`. Hooks execute in the runtime's namespace (not the container's), except `startContainer` which executes inside the container
- **Rlimit Configuration**: Per-container resource limits:
  - **`RlimitConfig`**: maps POSIX rlimit types (RLIMIT_NOFILE, RLIMIT_NPROC, RLIMIT_AS, RLIMIT_CORE, RLIMIT_STACK, etc.) to soft and hard limits. Applied to the container's init process before executing the entrypoint
- **OCIRuntime Manager**: Top-level runtime interface:
  - **`OCIRuntime`**: implements the five OCI operations as a clean interface. Maintains a registry of active containers indexed by container_id. Thread-safe for concurrent container operations. Provides container listing, filtering by state, and event emission for lifecycle transitions
- **FizzOCI Middleware**: `OCIRuntimeMiddleware` integrates with the middleware pipeline. When a FizzBuzz evaluation is requested in a containerized context, the middleware ensures the evaluation runs inside a properly configured OCI container
- **CLI Flags**: `--fizzoci`, `--fizzoci-create <bundle_path> <container_id>`, `--fizzoci-start <container_id>`, `--fizzoci-kill <container_id> <signal>`, `--fizzoci-delete <container_id>`, `--fizzoci-state <container_id>`, `--fizzoci-list` (list all containers with state), `--fizzoci-spec` (generate a default config.json template for FizzBuzz containers)

### Why This Is Necessary

Because the OCI runtime specification is the industry standard interface between container managers and container runtimes, and a platform that claims to run containers must implement this interface. The specification exists precisely so that higher-level tools (containerd, CRI-O, Podman) can delegate container creation to any compliant runtime without knowledge of the runtime's implementation details. FizzContainerd (Feature 7) will call FizzOCI through this interface. FizzKube will call FizzContainerd, which calls FizzOCI, which calls FizzNS and FizzCgroup. This is the standard container stack: orchestrator -> high-level daemon -> low-level runtime -> kernel primitives. FizzOCI is the low-level runtime layer. Without it, the stack has a gap between the kernel primitives (Features 1 and 2) and the high-level daemon (Feature 7) that no amount of orchestrator sophistication can bridge.

### Estimated Scale

~3,200 lines of OCI runtime, ~500 lines of configuration parser (OCIConfig, all sub-models, JSON schema validation), ~500 lines of container lifecycle state machine (OCIContainer, state transitions, create/start/kill/delete/state operations), ~350 lines of container creation procedure (namespace setup, cgroup configuration, rootfs preparation, mount processing, path masking, device allowlist), ~300 lines of seccomp profiles (SeccompProfile, predefined profiles, rule matching, action enforcement), ~250 lines of lifecycle hooks (six hook points, execution, timeout management), ~200 lines of rlimit configuration and process setup, ~300 lines of OCIRuntime manager (container registry, concurrency, event emission), ~200 lines of middleware and CLI, ~400 tests. Total: ~5,700 lines.

---

## Idea 4: FizzOverlay -- Copy-on-Write Union Filesystem ✅ DONE

### The Problem

Container images are not monolithic filesystem snapshots. They are ordered stacks of layers, each layer containing only the filesystem differences (additions, modifications, deletions) relative to the layer below it. A base layer might contain an operating system's root filesystem. A second layer adds application binaries. A third layer adds configuration files. At runtime, these layers are union-mounted into a single coherent filesystem view using a copy-on-write (COW) mechanism: reads traverse the layer stack from top to bottom until a file is found; writes are redirected to a writable upper layer, leaving lower layers immutable. This architecture enables image sharing (containers based on the same base image share the base layer's storage), fast startup (no need to copy the entire filesystem), and efficient storage (layers are deduplicated across images by content hash).

The primary union filesystem used by container runtimes is OverlayFS (merged into the Linux kernel in 3.18). OverlayFS composes a `lowerdir` (one or more read-only layers), an `upperdir` (a single read-write layer), and a `workdir` (scratch space for atomic operations) into a `merged` view. Reads from `merged` check `upperdir` first, then `lowerdir` layers in order. Writes go to `upperdir`. File deletion in `upperdir` creates a "whiteout" marker (a character device with 0/0 major/minor) that hides the file in lower layers. Directory deletion creates an "opaque whiteout" that hides the entire directory tree below.

The Enterprise FizzBuzz Platform has FizzVFS, a virtual file system supporting multiple providers (in-memory, on-disk, content-addressable). But FizzVFS has no union mount capability. It cannot layer multiple filesystem trees into a single view. It cannot perform copy-on-write operations. It has no concept of whiteout markers. Without a union filesystem, every container would need a complete copy of its root filesystem -- no layer sharing, no deduplication, no efficient image storage. Container images as defined by the OCI image spec would be impossible to implement efficiently.

### The Vision

An OverlayFS-style union filesystem providing copy-on-write semantics for container image layers. Multiple read-only lower layers are stacked beneath a single read-write upper layer, presenting a merged view where files appear to exist in a single directory tree. Content-addressable storage using SHA-256 digests enables layer deduplication across images. A snapshotter interface supports creating, mounting, and removing layer stacks for container lifecycle management. A diff engine computes the filesystem differences between layers for efficient image building and distribution.

### Key Components

- **`fizzoverlay.py`** (~3,000 lines): FizzOverlay Copy-on-Write Union Filesystem
- **Layer Model**: The fundamental unit of filesystem content:
  - **`Layer`**: an immutable, content-addressable filesystem snapshot identified by its SHA-256 digest. Each layer contains a set of filesystem entries (files, directories, symlinks) representing the differences from the layer below. Layers are stored as tar archives in the content store, unpacked into a directory tree when mounted. A layer's `diff_id` is the SHA-256 of its uncompressed tar archive. A layer's `digest` is the SHA-256 of its compressed (gzip) tar archive. The distinction matters for the OCI image spec: `diff_id` identifies the content, `digest` identifies the distribution artifact
  - **`LayerStore`**: content-addressable storage for layers. Layers are indexed by `diff_id` and `digest`. Duplicate layers (same `diff_id`) are stored once. The store tracks reference counts -- a layer is eligible for garbage collection when no image or container references it. Storage backend delegates to FizzVFS for actual I/O
  - **`LayerChain`**: an ordered sequence of layers representing an image's filesystem history. The first layer is the base (typically an OS rootfs), and each subsequent layer contains the differences applied on top. The chain is immutable once committed to the store
- **Union Mount**: OverlayFS-style merged view:
  - **`OverlayMount`**: the core union mount abstraction. Combines one or more `lowerdir` layers (read-only) with an `upperdir` (read-write) and a `workdir` (scratch space) into a `merged` view. Operations on the merged view:
    - **`lookup(path)`**: resolves a path by checking `upperdir` first, then each `lowerdir` from top to bottom. Returns the first match. If the path has a whiteout marker in a layer above it, the file is treated as non-existent regardless of lower layers
    - **`read(path)`**: delegates to the layer containing the resolved file
    - **`write(path, data)`**: if the file exists in a lower layer, performs copy-up (copies the file to `upperdir` preserving metadata, then writes to the copy). If the file does not exist in any layer, creates it in `upperdir`. Writes never modify lower layers
    - **`delete(path)`**: creates a whiteout marker in `upperdir`. If the path is a directory, creates an opaque whiteout (a directory with a `.wh..wh..opq` entry) that hides the entire subtree in lower layers
    - **`list(directory)`**: merges directory listings from all layers, excluding whited-out entries
  - **`CopyOnWrite`**: the copy-up engine. When a file in a lower layer must be modified, the engine copies the file (and its complete metadata -- permissions, ownership, timestamps, xattrs) to `upperdir` before the modification proceeds. Copy-up is lazy: it occurs on the first write to a file that exists only in lower layers. Subsequent writes to the same file go directly to `upperdir`
- **Whiteout Management**: File and directory deletion across layers:
  - **`WhiteoutManager`**: handles whiteout marker creation, detection, and interpretation. Implements both standard whiteouts (`.wh.<filename>` character device with 0/0 major/minor) and opaque whiteouts (`.wh..wh..opq` inside a directory). The manager filters whiteout markers from user-visible directory listings -- they are implementation details invisible to the container
- **Snapshotter**: Container filesystem lifecycle management:
  - **`Snapshotter`**: manages the lifecycle of overlay mounts for containers:
    - **`prepare(key, parent_layers)`**: creates a new overlay mount with the specified lower layers and a fresh upper layer. Returns a mount point. Used when creating a container: the image layers become lowerdirs, and the container gets a clean upperdir for writes
    - **`commit(key)`**: freezes the current upperdir as a new immutable layer and adds it to the LayerStore. Used when building images: the changes made in a build step are committed as a new layer
    - **`remove(key)`**: unmounts the overlay and deletes the upperdir. Used when deleting a container: the container's writable layer is discarded
    - **`view(key, parent_layers)`**: creates a read-only overlay mount (no upperdir) for inspection. Used for image content inspection without risk of modification
  - **Integration with FizzOCI**: when FizzOCI creates a container, it calls the Snapshotter to prepare an overlay mount from the container's image layers. The mounted path becomes the container's rootfs
- **Diff Engine**: Computing layer differences:
  - **`DiffEngine`**: compares two filesystem trees and produces a diff (the set of added, modified, and deleted files). Used when building images: after a build step executes, the diff between the overlay's merged view and the previous committed layer produces the new layer's content. The diff engine understands whiteout markers and converts deletions to whiteout entries in the output layer
- **Layer Cache**: Optimizing layer access:
  - **`LayerCache`**: LRU cache for unpacked layer content. Frequently used base layers (e.g., the FizzBuzz base image layer) are kept unpacked in memory to avoid repeated decompression. Cache size is bounded by a configurable memory limit and respects FizzCgroup memory accounting
- **Tar Archiver**: Layer serialization:
  - **`TarArchiver`**: packs and unpacks layers as tar archives following the OCI layer media types (`application/vnd.oci.image.layer.v1.tar`, `application/vnd.oci.image.layer.v1.tar+gzip`). Handles POSIX tar headers, long filenames, symlinks, hard links, device nodes, and xattr storage. Whiteout markers are serialized as standard tar entries per the OCI image spec
- **FizzOverlay Middleware**: `FizzOverlayMiddleware` integrates with the middleware pipeline, ensuring filesystem operations during FizzBuzz evaluation are routed through the overlay mount if the evaluation is running inside a container
- **Integration with FizzVFS**: FizzOverlay registers as a filesystem provider in FizzVFS, enabling overlay mounts to be accessed through the standard VFS interface. Mount operations in MNT namespaces (FizzNS) can reference overlay mounts
- **CLI Flags**: `--fizzoverlay`, `--fizzoverlay-layers` (list all layers in the store with digest, size, and reference count), `--fizzoverlay-inspect <digest>` (show layer contents), `--fizzoverlay-diff <digest_a> <digest_b>` (show filesystem differences between two layers), `--fizzoverlay-gc` (garbage collect unreferenced layers), `--fizzoverlay-stats` (storage utilization, deduplication ratio, cache hit rate)

### Why This Is Necessary

Because container images are layered, and serving layered images requires a union filesystem. The OCI image specification (v1.0.2) defines images as ordered sets of layers, each identified by a content hash. The specification assumes that the runtime can compose these layers into a single filesystem view at container creation time. Without a union filesystem, this composition is impossible without copying every layer into a flat directory -- destroying the sharing and deduplication that make container images practical. Docker reported that OverlayFS reduced image storage by 60-80% compared to flat copies in production deployments. FizzRegistry (Feature 5) will produce layered images. FizzOCI (Feature 3) will consume them. FizzOverlay is the filesystem layer that makes the image format work.

### Estimated Scale

~3,000 lines of union filesystem, ~350 lines of layer model (Layer, LayerStore, LayerChain, content addressing, reference counting, GC), ~500 lines of union mount (OverlayMount, lookup/read/write/delete/list, path resolution across layers), ~300 lines of copy-on-write engine (copy-up, metadata preservation, lazy semantics), ~250 lines of whiteout management (standard whiteouts, opaque whiteouts, filtering), ~400 lines of snapshotter (prepare/commit/remove/view, overlay lifecycle, FizzOCI integration), ~250 lines of diff engine (tree comparison, whiteout generation, added/modified/deleted classification), ~200 lines of layer cache (LRU, memory-bounded, cgroup-aware), ~250 lines of tar archiver (pack/unpack, OCI media types, POSIX tar), ~200 lines of middleware, VFS integration, and CLI, ~400 tests. Total: ~5,500 lines.

---

## Idea 5: FizzRegistry -- OCI Distribution-Compliant Image Registry ✅ DONE

### The Problem

The OCI Distribution Specification (v1.0.0) defines the API for distributing container images. A registry stores and serves images composed of manifests (describing an image's layers and configuration), image indexes (multi-architecture manifest lists), config blobs (runtime configuration), and layer blobs (filesystem content). The push/pull protocol uses content-addressable storage: clients upload blobs by digest, then upload a manifest referencing those digests. Pulling an image is the reverse: fetch the manifest, then fetch each referenced blob. This architecture enables deduplication (shared layers are stored once), integrity verification (every blob is verified against its digest), and efficient distribution (clients only pull layers they don't already have).

FizzKube's current "image pull" operation is a Python import. When a pod specifies `image: "enterprise_fizzbuzz.infrastructure.cache"`, FizzKube imports that module and calls its entry point. There is no image format. There are no layers. There is no manifest. There is no content-addressable storage. There is no registry. There is no pull protocol. There is no image signing or verification. There is no vulnerability scanning. There is no garbage collection of unused images. FizzKube's image model is a string that happens to be a valid Python module path. This is not an image registry. This is `importlib` with extra steps.

The platform also has no Dockerfile equivalent. Container images in the real world are built using Dockerfiles -- declarative build scripts that specify a base image, copy files, run commands, set environment variables, and define the entrypoint. The build process executes each instruction, captures the filesystem changes as a layer, and produces a final image. Without a build DSL, images cannot be reproducibly constructed.

### The Vision

A complete OCI Distribution-compliant image registry with push, pull, tag, and catalog APIs, backed by content-addressable blob storage and manifest management. Alongside the registry, a **FizzFile** DSL -- the platform's Dockerfile equivalent -- defines a build language with instructions specific to FizzBuzz containers: `FROM` (base image), `FIZZ` (add a Fizz rule), `BUZZ` (add a Buzz rule), `RUN` (execute a command in a build container), `COPY` (add files to the image), `ENV` (set environment variables), `ENTRYPOINT` (define the container's entrypoint), and `LABEL` (add metadata). An image builder executes FizzFile instructions, captures filesystem changes as layers via FizzOverlay, and pushes the resulting image to the registry. Garbage collection, vulnerability scanning, and cosign-style image signing round out the feature.

### Key Components

- **`fizzregistry.py`** (~3,200 lines): FizzRegistry OCI Distribution-Compliant Image Registry
- **Registry Storage Backend**: Content-addressable blob and manifest storage:
  - **`BlobStore`**: stores arbitrary binary blobs (image layers, config blobs) indexed by SHA-256 digest. Operations: `exists(digest)` (check if a blob is present), `get(digest)` (retrieve blob content), `put(data)` (store blob, return computed digest), `delete(digest)` (remove blob, only if no manifest references it), `stat(digest)` (return blob size and media type). The store delegates to FizzVFS for persistence. Deduplication is automatic: uploading a blob with an existing digest is a no-op
  - **`ManifestStore`**: stores OCI manifests and image indexes, indexed by `<repository>:<reference>` (where reference is a tag or digest). Each manifest references config and layer blobs by digest. The store validates that all referenced blobs exist before accepting a manifest (referential integrity)
- **OCI Image Model**: Data structures per the OCI image spec:
  - **`OCIManifest`**: describes a single image with `schemaVersion` (2), `mediaType` (`application/vnd.oci.image.manifest.v1+json`), `config` (descriptor pointing to the image config blob), and `layers` (ordered list of descriptors pointing to layer blobs). Each descriptor has `mediaType`, `digest`, `size`, and optional `annotations`
  - **`OCIImageIndex`**: a multi-architecture manifest list with `schemaVersion`, `mediaType` (`application/vnd.oci.image.index.v1+json`), and `manifests` (list of descriptors, each with a `platform` field specifying `os`, `architecture`, `variant`). Enables a single image reference to resolve to different manifests for different platforms
  - **`OCIImageConfig`**: the runtime configuration blob with `architecture`, `os`, `rootfs` (layer diff_ids), `history` (build steps), and `config` (default process args, env, working dir, exposed ports, volumes, labels, entrypoint, cmd). This is what FizzOCI reads to configure a container
- **Registry API**: OCI Distribution Specification endpoints:
  - **`RegistryAPI`**: implements the six core API operations:
    - `GET /v2/` -- API version check
    - `HEAD /v2/<name>/blobs/<digest>` -- check blob existence
    - `GET /v2/<name>/blobs/<digest>` -- pull blob
    - `POST /v2/<name>/blobs/uploads/` + `PUT /v2/<name>/blobs/uploads/<uuid>` -- push blob (chunked or monolithic)
    - `PUT /v2/<name>/manifests/<reference>` -- push manifest (by tag or digest)
    - `GET /v2/<name>/manifests/<reference>` -- pull manifest
    - `GET /v2/_catalog` -- list repositories
    - `GET /v2/<name>/tags/list` -- list tags for a repository
    - `DELETE /v2/<name>/manifests/<reference>` -- delete manifest
    - `DELETE /v2/<name>/blobs/<digest>` -- delete blob
  - All operations enforce authentication via FizzCap capabilities. Push requires `registry:push` capability. Pull requires `registry:pull` capability. Admin operations (delete, GC) require `registry:admin`
- **FizzFile DSL**: Container image build language:
  - **`FizzFile`**: parser for the FizzBuzz container build DSL. Instructions:
    - `FROM <image>:<tag>` -- set the base image. Every FizzFile must start with FROM (or `FROM scratch` for empty base)
    - `FIZZ <divisor> <word>` -- add a Fizz rule to the container's rule engine (e.g., `FIZZ 3 "Fizz"`)
    - `BUZZ <divisor> <word>` -- add a Buzz rule (e.g., `BUZZ 5 "Buzz"`)
    - `RUN <command>` -- execute a command in a temporary build container. The filesystem changes are captured as a new layer
    - `COPY <src> <dest>` -- copy files from the build context into the image
    - `ENV <key>=<value>` -- set an environment variable in the image config
    - `ENTRYPOINT [<args>]` -- set the default entrypoint command
    - `LABEL <key>=<value>` -- add metadata to the image
    - `WORKDIR <path>` -- set the working directory for subsequent instructions
    - `EXPOSE <port>` -- document which ports the container listens on
    - `VOLUME <path>` -- declare a mount point for external volumes
    - `USER <uid>:<gid>` -- set the default user for subsequent RUN/ENTRYPOINT instructions
  - **Parser**: tokenizes and parses FizzFile syntax into an instruction list. Supports comments (`#`), line continuation (`\`), and build arguments (`ARG`/`${VAR}` substitution)
- **Image Builder**: Executes FizzFile instructions to produce images:
  - **`ImageBuilder`**: processes a FizzFile and build context to produce an OCI image:
    - Starts from the base image specified by FROM (pulled from the registry if not cached)
    - For each instruction, creates a temporary container (via FizzOCI), executes the instruction, captures the filesystem diff (via FizzOverlay DiffEngine), commits the diff as a new layer, and pushes the layer to the BlobStore
    - **Layer caching**: each instruction is hashed (instruction text + parent layer digest). If the hash matches a previously built layer, the cached layer is reused without re-execution. Cache invalidation occurs when an instruction or any preceding instruction changes. This is the same caching strategy used by Docker BuildKit
    - Produces an OCIManifest, OCIImageConfig, and pushes them to the ManifestStore
    - Build output includes each instruction, whether the cache was used, and the resulting layer digest and size
- **Garbage Collector**: Reclaiming unused storage:
  - **`GarbageCollector`**: identifies and removes unreferenced blobs. A blob is unreferenced if no manifest in any repository references it. GC uses a mark-sweep algorithm: mark all blobs referenced by any manifest, sweep all unmarked blobs. GC respects a configurable grace period (default: 24 hours) to avoid deleting blobs that are part of an in-progress push
- **Image Signing**: Provenance and integrity verification:
  - **`ImageSigner`**: cosign-style image signing. Signs manifest digests using HMAC-SHA256 keys from the Secrets Vault. Signatures are stored as OCI artifacts (referrer manifests) linked to the signed image. Verification checks that the manifest digest matches the signature. The signing key is held by Bob McFizzington (as Secrets Vault Custodian)
  - **Integration with Blockchain**: signatures are anchored to the blockchain audit ledger, providing tamper-evident provenance. An image's signature chain can be verified against the blockchain
- **Vulnerability Scanner**: Image security analysis:
  - **`VulnerabilityScanner`**: scans image layers for known vulnerabilities by analyzing installed packages (from layer metadata) against a vulnerability database. The database is maintained internally (FizzBuzz-specific CVEs, e.g., CVE-2026-FIZZ-001: "Modulo operation returns incorrect result for divisor=0"). Scan results include severity (CRITICAL/HIGH/MEDIUM/LOW), affected package, affected layer, and recommended remediation. Images with CRITICAL vulnerabilities are flagged in the registry catalog
- **FizzRegistry Middleware**: `FizzRegistryMiddleware` integrates with the middleware pipeline, making the registry available for image pull operations during FizzBuzz evaluation startup
- **CLI Flags**: `--fizzregistry`, `--fizzregistry-push <image>:<tag>`, `--fizzregistry-pull <image>:<tag>`, `--fizzregistry-catalog` (list all repositories), `--fizzregistry-tags <image>` (list tags), `--fizzregistry-inspect <image>:<tag>` (show manifest and config), `--fizzregistry-build <fizzfile_path>` (build image from FizzFile), `--fizzregistry-sign <image>:<tag>`, `--fizzregistry-verify <image>:<tag>`, `--fizzregistry-scan <image>:<tag>`, `--fizzregistry-gc`

### Why This Is Necessary

Because container images must be stored somewhere, and that somewhere must implement a standard protocol. The OCI Distribution Specification exists because the industry learned that proprietary image formats and registry APIs create vendor lock-in and interoperability problems. Docker, containerd, CRI-O, Podman, Skopeo, Buildah, and every other container tool speaks the OCI distribution protocol. FizzContainerd (Feature 7) will pull images from FizzRegistry using this protocol. FizzOCI (Feature 3) will consume the pulled images. Without a registry, every container would need its image layers pre-provisioned on disk -- no pulling, no sharing, no versioning, no multi-architecture support. The FizzFile DSL is equally critical: without a declarative build language, image creation is a manual process of modifying filesystems and committing layers. FizzFile brings reproducible image builds to the platform.

### Estimated Scale

~3,200 lines of image registry, ~350 lines of storage backend (BlobStore, ManifestStore, content addressing, referential integrity), ~400 lines of OCI image model (OCIManifest, OCIImageIndex, OCIImageConfig, descriptors, platform resolution), ~450 lines of registry API (OCI distribution endpoints, authentication, error handling), ~450 lines of FizzFile DSL (parser, tokenizer, instruction set, variable substitution, build arguments), ~400 lines of image builder (instruction execution, layer capture, cache, manifest/config generation), ~200 lines of garbage collector (mark-sweep, grace period, reference tracking), ~200 lines of image signing (HMAC signing, verification, blockchain anchoring, artifact storage), ~200 lines of vulnerability scanner (layer analysis, CVE database, severity classification, reporting), ~150 lines of middleware and CLI, ~400 tests. Total: ~5,800 lines.

---

## Idea 6: FizzCNI -- Container Network Interface Plugin System ✅ DONE

### The Problem

The Container Network Interface (CNI) specification (v1.0.0) defines a standard for configuring network interfaces in Linux containers. CNI is used by Kubernetes, CRI-O, containerd, Podman, and every other major container orchestrator and runtime. The specification defines a plugin model: the container runtime calls a CNI plugin with a container's network namespace, and the plugin configures network connectivity -- creating interfaces, assigning IP addresses, configuring routes, and setting up DNS. Different plugins provide different network topologies: bridge plugins create a virtual bridge connecting containers on the same host, overlay plugins create cross-host networks using VXLAN or similar encapsulation, host plugins share the host's network namespace, and none plugins provide no networking at all.

FizzKube assigns IP addresses to pods from a configured CIDR range. The Service Mesh routes traffic between services using service names. FizzDNS resolves names to addresses. FizzNet provides a TCP/IP stack. But none of these systems actually configure container network namespaces, because there are no container network namespaces (until FizzNS, Feature 1). FizzKube's pod IPs are entries in a dictionary. The Service Mesh routes traffic between in-process function calls. FizzDNS resolves names to addresses that nothing binds to. The platform has a complete network stack with no container network plumbing connecting containers to it. A container running in its own NET namespace starts with only a loopback interface -- it has no external connectivity until a CNI plugin creates a virtual ethernet pair, assigns an IP address, configures routes, and connects the container to a bridge or overlay network.

### The Vision

A CNI-specification-compliant plugin system providing container network connectivity. The system implements four network drivers: bridge (connects containers to a virtual bridge on the host), host (shares the host's network namespace -- no isolation), none (no networking), and overlay (connects containers across hosts using encapsulated tunnels). Each driver handles interface creation, IP address assignment, routing, and cleanup. A built-in IPAM (IP Address Management) plugin manages subnet allocation. Port mapping enables external access to container services. A container DNS responder provides name resolution within container networks. Network policies implement microsegmentation -- fine-grained traffic control between containers based on labels, namespaces, and ports.

### Key Components

- **`fizzcni.py`** (~3,000 lines): FizzCNI Container Network Interface Plugin System
- **CNI Plugin Interface**: The standard plugin contract:
  - **`CNIPlugin` ABC**: abstract base defining the three CNI operations:
    - `ADD(container_id, netns, ifname, args, config)` -- configure networking for a container. Creates a network interface in the container's NET namespace, assigns an IP address, configures routes, and returns the interface configuration (IP, gateway, routes, DNS)
    - `DEL(container_id, netns, ifname, args, config)` -- remove networking for a container. Deletes the interface, releases the IP address, and cleans up routes
    - `CHECK(container_id, netns, ifname, args, config)` -- verify that networking is correctly configured for a container. Returns success if the configuration matches expectations, error if it has drifted
  - **`CNIConfig`**: JSON configuration for a CNI plugin invocation, following the CNI spec: `cniVersion`, `name` (network name), `type` (plugin name), `args` (plugin-specific arguments), `ipam` (IPAM configuration), `dns` (DNS configuration). Supports plugin chaining: multiple plugins can be composed in a `plugins` list, each executed in order for ADD and reverse order for DEL
  - **`CNIResult`**: the result returned by a plugin's ADD operation: `interfaces` (list of created interfaces with name, MAC, and sandbox reference), `ips` (list of IP configurations with address, gateway, and interface index), `routes` (list of route entries with destination and gateway), `dns` (nameservers, domain, search domains)
- **Bridge Plugin**: Host-local container networking:
  - **`BridgePlugin`**: the most common CNI plugin in single-host deployments. Creates a virtual bridge (`fizzbr0`) on the host if it doesn't exist. For each container:
    - Creates a veth pair (two virtual ethernet interfaces connected like a pipe)
    - Moves one end of the veth pair into the container's NET namespace (via FizzNS)
    - Attaches the other end to `fizzbr0` on the host
    - Assigns an IP address to the container's interface (via IPAM)
    - Configures the default route to point to the bridge's IP as gateway
    - Enables IP forwarding on the host for container-to-external traffic
  - **`VethPair`**: models a virtual ethernet pair. Each end has a name, MAC address, and the namespace it resides in. Traffic sent to one end emerges from the other. Veth pairs are the standard mechanism for connecting a container's network namespace to the host or a bridge
  - **`BridgeInterface`**: models the `fizzbr0` bridge device. Maintains a list of attached veth endpoints. Forwards frames between attached interfaces (L2 switching). Has its own IP address that serves as the default gateway for connected containers
- **Host Plugin**: Shared network namespace:
  - **`HostPlugin`**: does not create a new NET namespace. The container shares the host's network stack. No interface creation, no IP assignment, no routing changes. Used for containers that need direct access to the host network (e.g., containers running network infrastructure like FizzDNS or the Service Mesh)
- **None Plugin**: No networking:
  - **`NonePlugin`**: creates a NET namespace with only a loopback interface. No external connectivity. Used for containers that do not require network access (batch processing, offline computation)
- **Overlay Plugin**: Cross-host container networking:
  - **`OverlayPlugin`**: creates an overlay network using VXLAN-style encapsulation. Containers on different hosts can communicate as if on the same L2 network. Each host has a VTEP (VXLAN Tunnel Endpoint) that encapsulates container traffic in UDP packets for transit across the host network. The overlay plugin integrates with the FizzNet TCP/IP stack for encapsulation and the peer-to-peer gossip network for host discovery and VTEP registration
- **IPAM Plugin**: IP Address Management:
  - **`IPAMPlugin`**: manages IP address allocation for container networks:
    - **Subnet management**: each network is assigned a CIDR range (e.g., 10.244.0.0/16 for the pod network). The IPAM plugin carves per-host subnets from this range (e.g., 10.244.1.0/24 for host 1, 10.244.2.0/24 for host 2)
    - **Address allocation**: within a host subnet, addresses are allocated sequentially or from a free list. Allocated addresses are tracked in a persistent store. Released addresses are returned to the free list after a configurable cooldown (to prevent rapid reuse that could cause stale connection issues)
    - **Gateway assignment**: the first usable address in each subnet (e.g., 10.244.1.1) is reserved for the bridge gateway
    - **Lease management**: each allocation has a TTL. Containers that fail to renew their lease (because they crashed without cleanup) have their address reclaimed after the TTL expires
- **Port Mapping**: Container port exposure:
  - **`PortMapper`**: maps ports from the host network to container networks. A mapping `hostPort:containerPort` configures the host to forward traffic received on `hostPort` to the container's IP at `containerPort`. Implements DNAT (Destination NAT) rules in the host's packet processing path. Supports TCP and UDP protocols. Port conflicts (two containers requesting the same host port) are detected and rejected
  - **Integration with FizzProxy**: the reverse proxy can route external traffic to port-mapped containers, providing load balancing across replicas of the same service
- **Container DNS**: Name resolution for containers:
  - **`ContainerDNS`**: a DNS responder configured as the nameserver for container networks. Resolves container names and service names to IP addresses:
    - Container names resolve to their assigned IP (e.g., `web-container-1` -> `10.244.1.5`)
    - Service names resolve to the service's cluster IP or load-balanced endpoint IPs (e.g., `fizzbuzz-evaluator` -> `10.96.0.10`)
    - External names are forwarded to the upstream DNS (FizzDNS authoritative server or a configured external resolver)
  - **Integration with FizzDNS**: ContainerDNS registers as a zone in FizzDNS for the cluster domain (e.g., `cluster.fizz`). FizzDNS delegates queries for `*.cluster.fizz` to ContainerDNS
  - **Integration with Service Mesh**: service endpoints are synchronized from the Service Mesh's service registry, ensuring DNS responses reflect current service topology
- **Network Policies**: Container traffic microsegmentation:
  - **`NetworkPolicy`**: Kubernetes-style network policies that control ingress and egress traffic for containers based on labels, namespaces, and port/protocol selectors. Each policy specifies a `pod_selector` (which containers the policy applies to), `ingress` rules (which sources can send traffic to these containers, on which ports), and `egress` rules (which destinations these containers can reach, on which ports). Policies are default-deny when applied: containers with a policy only accept traffic explicitly allowed by a rule
  - **Policy enforcement**: implemented as packet filter rules in each container's NET namespace. The bridge plugin consults the active network policies when forwarding frames, dropping traffic that violates policy
- **FizzCNI Middleware**: `FizzCNIMiddleware` integrates with the middleware pipeline, ensuring that container network configuration is applied before FizzBuzz evaluation begins in a containerized context
- **CLI Flags**: `--fizzcni`, `--fizzcni-list` (list configured networks), `--fizzcni-inspect <network>` (show network configuration and connected containers), `--fizzcni-ipam-stats` (IP allocation statistics by network), `--fizzcni-portmap` (list active port mappings), `--fizzcni-dns-cache` (show ContainerDNS resolution cache), `--fizzcni-policies` (list active network policies), `--fizzcni-driver <bridge|host|none|overlay>` (select network driver for new containers)

### Why This Is Necessary

Because containers without networking are isolated from more than just the host -- they are isolated from each other. A container in its own NET namespace has only a loopback interface. It cannot communicate with other containers, with the host, or with external networks unless a CNI plugin explicitly creates the plumbing. FizzKube's pod networking model assumes that every pod has a routable IP address and that pods can communicate with each other directly. This assumption is currently satisfied trivially (all pods share the host network because there are no namespaces). Once FizzNS introduces NET namespace isolation, this assumption breaks. FizzCNI restores it by providing the network plumbing that connects isolated containers to each other and to the outside world. The CNI specification is the industry standard for this plumbing, and FizzKube's kubelet must call CNI plugins when creating pods -- just as the real Kubernetes kubelet does.

### Estimated Scale

~3,000 lines of CNI plugin system, ~300 lines of CNI plugin interface (CNIPlugin ABC, CNIConfig, CNIResult, plugin chaining), ~500 lines of bridge plugin (VethPair, BridgeInterface, fizzbr0 management, veth creation/teardown, IP forwarding), ~100 lines of host plugin and none plugin, ~300 lines of overlay plugin (VXLAN encapsulation, VTEP management, host discovery), ~350 lines of IPAM plugin (subnet management, address allocation, lease management, gateway assignment), ~250 lines of port mapper (DNAT rules, port conflict detection, TCP/UDP support), ~350 lines of container DNS (name resolution, service endpoint sync, upstream forwarding, FizzDNS integration), ~300 lines of network policies (policy model, pod selector, ingress/egress rules, packet filtering), ~150 lines of middleware and CLI, ~400 tests. Total: ~5,500 lines.

---

## Idea 7: FizzContainerd -- High-Level Container Daemon & Shim Architecture ✅ DONE

### The Problem

In the standard container stack, the orchestrator (Kubernetes) does not call the low-level runtime (runc) directly. Between them sits a high-level container daemon -- containerd or CRI-O -- that manages the complete lifecycle of containers above the runtime layer. containerd manages images (pulling from registries, unpacking layers into snapshots), content (content-addressable storage for image blobs), snapshots (preparing overlay mounts for containers), containers (metadata associating an image with runtime configuration), tasks (the running state of a container -- process, I/O streams, exit code), and shims (per-container lifecycle daemons that survive daemon restarts).

The shim architecture is particularly important. When containerd creates a container, it does not directly manage the container's process. Instead, it launches a shim -- a small daemon that takes ownership of the container's init process. The shim serves three critical functions: (1) it holds the container's namespaces open (namespaces are reference-counted, and the shim's membership keeps them alive), (2) it collects the container's exit code when it terminates, and (3) it allows containerd to restart without killing running containers (because the shim, not containerd, owns the container process).

FizzKube currently manages pods by directly instantiating Python objects. There is no daemon managing container lifecycle. There is no shim holding namespaces open. There is no content store for image blobs. There is no snapshot service preparing overlay mounts. There is no task abstraction separating container metadata from running state. FizzKube goes directly from "schedule pod" to "call function," skipping the entire daemon layer that real container orchestration depends on.

### The Vision

A containerd-style high-level container daemon that manages the full container lifecycle above the FizzOCI runtime. The daemon provides six services: image service (pull, push, list, remove images via FizzRegistry), content service (local content-addressable store for blobs), snapshot service (prepare, commit, remove overlay mounts via FizzOverlay snapshotter), container service (create, update, delete container metadata), task service (create, start, kill, delete tasks -- the running state of containers -- via FizzOCI), and event service (publish/subscribe for container lifecycle events). Per-container shims manage process ownership, namespace retention, and exit code collection. A CRI (Container Runtime Interface) service exposes the gRPC-equivalent API that FizzKube's kubelet calls, translating Kubernetes pod operations into containerd container/task operations.

### Key Components

- **`fizzcontainerd.py`** (~3,200 lines): FizzContainerd High-Level Container Daemon
- **Daemon Core**: The long-running daemon process:
  - **`ContainerdDaemon`**: the main daemon class, initialized at platform startup. Manages service registration, plugin loading, and lifecycle. Exposes a unified API that delegates to specialized services. Maintains an in-memory state that is checkpointed to persistent storage for crash recovery. The daemon runs as a background task in the platform's event loop
  - **Plugin architecture**: each service (image, content, snapshot, container, task, event) is a plugin that registers with the daemon. This follows containerd's real plugin architecture, where services are composable and replaceable. The plugin registry uses a dependency graph with topological sort to ensure services start in the correct order (content before image, snapshot before task, etc.)
- **Content Service**: Local content-addressable storage:
  - **`ContentStore`**: stores and retrieves blobs by SHA-256 digest. Provides `ingest(ref)` (start a write transaction), `writer.write(data)` (stream data into the transaction), `writer.commit(expected_digest)` (finalize the blob, verifying the digest matches), and `get(digest)` (read a blob). Ingestion is atomic: partially written blobs are not visible until committed. The content store is the local cache of image blobs pulled from FizzRegistry
  - **Garbage collection**: unreferenced content (blobs not referenced by any image, container, or snapshot) is collected periodically. References are tracked through a label system: each blob can have labels linking it to images, containers, or other blobs
- **Image Service**: Image lifecycle management:
  - **`ImageService`**: manages the lifecycle of images in the local daemon:
    - `pull(reference)` -- pulls an image from FizzRegistry. Fetches the manifest, then fetches each layer blob into the ContentStore (skipping layers already present). Unpacks layers into the snapshot service for fast container creation
    - `push(reference)` -- pushes a locally built image to FizzRegistry
    - `list()` -- lists all locally available images with their tags, digests, sizes, and creation dates
    - `remove(reference)` -- removes an image and its associated content (if not referenced by other images)
  - **Image unpacking**: when an image is pulled, its layers are unpacked into a snapshot chain via the snapshot service. This pre-computation means container creation does not need to unpack layers at startup, reducing container start latency
- **Snapshot Service**: Overlay filesystem lifecycle:
  - **`SnapshotService`**: wraps FizzOverlay's Snapshotter with daemon-managed lifecycle:
    - `prepare(key, parent)` -- create an active (read-write) snapshot from a parent chain. Used when creating a container: the image's snapshot chain becomes the parent, and a fresh writable layer is added
    - `commit(key, name)` -- commit an active snapshot as a committed (read-only) snapshot. Used when building images: the build step's changes are committed as a new layer
    - `remove(key)` -- remove a snapshot and its associated storage
    - `mounts(key)` -- return the mount specifications for a snapshot (the overlay mount parameters that FizzOCI uses as rootfs)
  - **Snapshot chain**: each image creates a chain of committed snapshots (one per layer). Container snapshots are active snapshots with the image chain as parent. This tree structure enables O(1) container creation (just add a writable layer) and efficient storage (shared image layers are stored once)
- **Container Service**: Container metadata management:
  - **`Container`**: metadata about a container (distinct from the running state). Fields: `container_id`, `image` (reference to the source image), `runtime` (FizzOCI runtime spec), `snapshot_key` (the snapshot providing the rootfs), `spec` (OCI config.json as a structured object), `labels` (key-value metadata), `extensions` (opaque data for plugins), `created_at`, `updated_at`. Containers are metadata -- they describe what a container is. Tasks describe whether it is running
  - **CRUD operations**: `create(container)`, `get(container_id)`, `update(container_id, updates)`, `delete(container_id)`, `list(filters)`. Container creation prepares the snapshot and generates the OCI bundle. Container deletion cleans up the snapshot
- **Task Service**: Running state management:
  - **`Task`**: the running state of a container. Fields: `task_id` (same as container_id), `container_id`, `pid` (the container's init process PID), `status` (CREATED, RUNNING, PAUSED, STOPPED), `exit_code` (set when the task stops), `stdin`/`stdout`/`stderr` (I/O streams), `shim` (reference to the task's shim process)
  - **Task operations**:
    - `create(container_id, opts)` -- create a task for a container. Launches a shim, which calls FizzOCI `create` to set up the container. Returns the task in CREATED state
    - `start(task_id)` -- start the task. The shim calls FizzOCI `start`. Returns the task in RUNNING state
    - `kill(task_id, signal)` -- send a signal to the task's init process
    - `delete(task_id)` -- clean up a stopped task. The shim calls FizzOCI `delete`. Collects exit code and I/O
    - `exec(task_id, exec_id, spec)` -- execute an additional process inside a running container (equivalent to `docker exec`). Creates a new process in the container's namespaces and cgroups
    - `pause(task_id)` / `resume(task_id)` -- freeze/thaw the container's processes using cgroup freezer semantics
  - **`ContainerLog`**: captures stdout/stderr from container tasks. Logs are stored per-container with timestamps and stream labels. Supports streaming (follow) and historical retrieval. Integrates with the event sourcing journal for durability
- **Shim Architecture**: Per-container lifecycle daemons:
  - **`Shim`**: a lightweight daemon spawned for each container task. The shim:
    - Owns the container's init process (is the parent process in the process tree)
    - Holds the container's namespace references open (preventing GC)
    - Captures the container's exit code when the init process terminates
    - Serves as a communication proxy between the daemon and the container
    - Survives daemon restarts: if FizzContainerd restarts, the shims continue running, and the daemon reconnects to them on startup. This enables zero-downtime daemon upgrades
  - **Shim lifecycle**: spawned during `task.create`, runs until `task.delete`. The shim maintains a socket for daemon communication. On daemon restart, the daemon discovers running shims by scanning the shim socket directory and re-establishes connections
  - **Integration with Process Migration**: shims can be checkpointed and restored using the FizzMigrate process migration system, enabling live migration of running containers between hosts
- **Event Service**: Publish/subscribe for lifecycle events:
  - **`EventService`**: publishes events for all container lifecycle transitions: image pull/push/remove, container create/update/delete, task create/start/kill/pause/resume/delete, snapshot prepare/commit/remove. Events include the entity type, entity ID, action, timestamp, and optional payload. Subscribers receive events matching their topic filters
  - **Integration with Event Sourcing**: all events are persisted in the event sourcing journal for audit, replay, and debugging. The CQRS read model is updated from these events
  - **Integration with FizzPager**: critical events (task OOM kill, shim crash, image pull failure) are forwarded to FizzPager for alerting
- **CRI Service**: Kubernetes integration interface:
  - **`CRIService`**: implements the Container Runtime Interface (CRI) that FizzKube's kubelet calls. CRI defines two services:
    - **RuntimeService**: `RunPodSandbox`, `StopPodSandbox`, `RemovePodSandbox`, `PodSandboxStatus`, `ListPodSandbox`, `CreateContainer`, `StartContainer`, `StopContainer`, `RemoveContainer`, `ListContainers`, `ContainerStatus`, `ExecSync`, `Exec`, `Attach`, `PortForward`
    - **ImageService**: `ListImages`, `ImageStatus`, `PullImage`, `RemoveImage`, `ImageFsInfo`
  - CRI translates FizzKube's pod-level operations into containerd's container/task operations. A pod sandbox maps to a set of shared namespaces (NET, IPC, UTS) that all containers in the pod join. Each container in the pod has its own PID and MNT namespace but shares the pod's network namespace -- exactly matching real Kubernetes pod networking semantics
- **FizzContainerd Middleware**: `FizzContainerdMiddleware` integrates with the middleware pipeline. When FizzBuzz evaluation is requested, the middleware resolves the evaluation container through FizzContainerd, ensuring the evaluation runs inside a properly managed container with shim-backed lifecycle management
- **CLI Flags**: `--fizzcontainerd`, `--fizzcontainerd-images` (list local images), `--fizzcontainerd-containers` (list containers with status), `--fizzcontainerd-tasks` (list running tasks), `--fizzcontainerd-shims` (list active shims with PID and socket), `--fizzcontainerd-logs <container_id>` (stream container logs), `--fizzcontainerd-exec <container_id> <command>` (exec into a running container), `--fizzcontainerd-events` (stream lifecycle events), `--fizzcontainerd-content-stats` (content store utilization), `--fizzcontainerd-snapshot-tree` (ASCII tree of snapshot chains)

### Why This Is Necessary

Because the low-level runtime (FizzOCI) manages individual container lifecycles, but a production platform needs a daemon that manages the fleet. FizzOCI creates one container from one bundle. FizzContainerd manages all containers, all images, all snapshots, and all tasks. It is the layer that translates high-level operations ("run this image as a container") into the sequence of low-level operations ("pull image blobs, unpack layers, prepare snapshot, generate OCI bundle, create container via FizzOCI, launch shim, start task"). Without this layer, FizzKube would need to orchestrate these steps directly -- coupling the orchestrator to runtime implementation details that should be abstracted. The CRI interface is the standard abstraction: FizzKube calls CRI, CRI calls containerd, containerd calls the OCI runtime. This is the same architecture used by every Kubernetes cluster in production. The shim architecture ensures that running containers survive daemon restarts -- a critical operational requirement for a platform that Bob McFizzington operates solo, where daemon upgrades must not cause container restarts.

### Estimated Scale

~3,200 lines of container daemon, ~300 lines of daemon core (plugin architecture, service registry, dependency graph, checkpointing), ~300 lines of content service (ContentStore, ingestion, atomic writes, GC, labels), ~350 lines of image service (pull, push, list, remove, layer unpacking), ~250 lines of snapshot service (prepare, commit, remove, mounts, snapshot chains), ~250 lines of container service (Container metadata, CRUD, OCI bundle generation), ~400 lines of task service (Task, create/start/kill/delete/exec/pause/resume, I/O streams, ContainerLog), ~350 lines of shim architecture (Shim lifecycle, namespace retention, exit code collection, daemon reconnection, process migration integration), ~250 lines of event service (publish/subscribe, event sourcing integration, FizzPager integration), ~350 lines of CRI service (RuntimeService, ImageService, pod sandbox, shared namespaces, CRI-to-containerd translation), ~200 lines of middleware and CLI, ~400 tests. Total: ~5,800 lines.

---

## Implementation Priority

| # | Feature | Lines (est.) | Container Stack Layer | Priority |
|---|---------|-------------|----------------------|----------|
| 1 | FizzNS -- Namespace Isolation | ~5,200 | Kernel primitive (isolation) | P0 |
| 2 | FizzCgroup -- Resource Accounting | ~5,400 | Kernel primitive (limits) | P0 |
| 3 | FizzOCI -- OCI Container Runtime | ~5,700 | Low-level runtime (runc) | P0 |
| 4 | FizzOverlay -- Union Filesystem | ~5,500 | Storage (image layers) | P1 |
| 5 | FizzRegistry -- Image Registry | ~5,800 | Distribution (images) | P1 |
| 6 | FizzCNI -- Container Networking | ~5,500 | Networking (CNI) | P1 |
| 7 | FizzContainerd -- Container Daemon | ~5,800 | High-level daemon (containerd) | P2 |

**Total estimated new code:** ~38,900 lines
**Total estimated new tests:** ~2,800

When this round ships, FizzKube's pods will be real containers. Each pod will run in seven isolated namespaces, with cgroup-enforced resource limits, on an overlay filesystem composed from image layers pulled from an OCI-compliant registry, connected to a bridge network configured by a CNI plugin, managed by a containerd-style daemon with per-container shims. The FizzBuzz evaluation path will traverse the full container stack: FizzKube schedules a pod, FizzContainerd creates a container via CRI, the shim calls FizzOCI to set up namespaces and cgroups, FizzOverlay provides the rootfs, FizzCNI configures networking, and the evaluation runs inside a properly isolated, resource-limited, network-connected container. The gap between what FizzKube promises and what the runtime delivers will finally be closed.

---

*This brainstorm report was generated by assessing the architectural gap between the platform's container orchestration semantics and its container runtime reality, and determining that the gap is seven features wide.*
