# Round 16 Container Runtime Modules — API Surface Inventory

**Agent**: Roze (domain research specialist)
**Date**: 2026-03-24
**Scope**: Complete public API of all 7 Round 16 infrastructure modules + `__main__.py` wiring pattern

---

## 1. FizzNS — Linux Namespace Isolation Engine

**File**: `enterprise_fizzbuzz/infrastructure/fizzns.py`
**Middleware Priority**: 106

### Constants

| Name | Value | Description |
|------|-------|-------------|
| `CLONE_NEWPID` | `0x20000000` | PID namespace flag |
| `CLONE_NEWNET` | `0x40000000` | Network namespace flag |
| `CLONE_NEWNS` | `0x00020000` | Mount namespace flag |
| `CLONE_NEWUTS` | `0x04000000` | UTS namespace flag |
| `CLONE_NEWIPC` | `0x08000000` | IPC namespace flag |
| `CLONE_NEWUSER` | `0x10000000` | User namespace flag |
| `CLONE_NEWCGROUP` | `0x02000000` | Cgroup namespace flag |
| `DEFAULT_HOSTNAME` | `"fizzbuzz-container"` | Default UTS hostname |
| `DEFAULT_DOMAINNAME` | `"enterprise.local"` | Default UTS domain |
| `MAX_PID` | `32768` | Max PID value |
| `MAX_NAMESPACE_DEPTH` | `32` | Max nesting depth |
| `MAX_UID_MAP_ENTRIES` | `340` | Max UID map entries |
| `MAX_GID_MAP_ENTRIES` | `340` | Max GID map entries |

### Enums

**`NamespaceType(Enum)`** — PID, NET, MNT, UTS, IPC, USER, CGROUP (values are CLONE_NEW* flags)

**`NamespaceState(Enum)`** — ACTIVE, DESTROYING, DESTROYED

### Dataclasses (all frozen)

| Class | Fields |
|-------|--------|
| `VethPair` | `pair_id, host_interface, container_interface, host_ns_id, container_ns_id, created_at` |
| `MountEntry` | (mount table entry with source, target, fs_type, options, propagation) |
| `UIDMapping` | (inner_uid, outer_uid, count) |
| `GIDMapping` | (inner_gid, outer_gid, count) |
| `NetworkInterface` | (name, mac_address, mtu, ipv4_addresses, ipv6_addresses, state) |
| `RoutingEntry` | (destination, gateway, interface, metric) |
| `SocketBinding` | (protocol, address, port, pid) |
| `SHMSegment` | (shm_id, key, size, owner_pid, attached_pids) |
| `SemaphoreSet` | (sem_id, key, num_sems, owner_pid) |
| `MessageQueue` | (msq_id, key, max_bytes, owner_pid, message_count) |
| `CgroupEntry` | (path, controllers, processes) |

### Abstract Base Class: `Namespace(ABC)`

Common interface for all 7 namespace types.

**Properties**: `ns_id -> str`, `ns_type -> NamespaceType`, `parent -> Optional[Namespace]`, `children -> list[Namespace]`, `ref_count -> int`, `state -> NamespaceState`, `member_pids -> set[int]`, `created_at -> float`, `metadata -> dict[str, Any]`, `depth -> int`, `is_root -> bool`

**Methods**:
- `add_ref() -> int`
- `release_ref() -> int`
- `add_member(pid: int) -> None`
- `remove_member(pid: int) -> None`
- `set_metadata(key: str, value: Any) -> None`
- `get_metadata(key: str, default: Any = None) -> Any`
- `isolate(pid: int) -> None` (abstract)
- `enter(pid: int) -> None` (abstract)
- `leave(pid: int) -> None` (abstract)
- `destroy() -> None` (abstract)
- `get_hierarchy() -> list[Namespace]`
- `get_descendants() -> list[Namespace]`

### Concrete Namespace Types

**`PIDNamespace(Namespace)`**
- Props: `init_pid`, `pid_count`, `orphaned_pids`, `killed_pids`, `signal_log`
- `allocate_pid(process_name: str = "process", parent_pid: Optional[int] = None) -> int`
- `deallocate_pid(pid: int) -> None`
- `translate_pid_to_parent(local_pid: int) -> Optional[int]`
- `translate_pid_from_parent(parent_pid: int) -> Optional[int]`
- `get_process_info(pid: int) -> Optional[dict[str, Any]]`
- `get_children_of(pid: int) -> list[int]`
- `get_visible_pids() -> set[int]`
- `send_signal(target_pid: int, signal: str, sender_pid: int = 0) -> bool`
- `get_pid_table_snapshot() -> dict[int, dict[str, Any]]`

**`NETNamespace(Namespace)`**
- Props: `interfaces`, `routing_table`, `socket_bindings`, `veth_pairs`, `arp_table`
- `add_interface(name: str, mac_address: str = "", mtu: int = 1500) -> NetworkInterface`
- `remove_interface(name: str) -> None`
- `set_interface_state(name: str, state: str) -> None`
- `assign_ipv4(interface_name: str, address: str) -> None`
- `assign_ipv6(interface_name: str, address: str) -> None`
- `add_route(destination: str, gateway: str, interface: str, metric: int = 0) -> RoutingEntry`
- `remove_route(destination: str) -> None`
- `bind_socket(protocol: str, address: str, port: int, pid: int = 0) -> SocketBinding`
- `unbind_socket(protocol: str, address: str, port: int) -> None`
- `create_veth_pair(peer_namespace: NETNamespace, host_name: str = "veth0", container_name: str = "eth0") -> VethPair`
- `get_interface_count() -> int`
- `get_binding_count() -> int`

**`MNTNamespace(Namespace)`**
- Props: `mount_table`, `root_path`, `old_root_path`, `mount_count`
- `mount(source: str, target: str, fs_type: str, options: str = "rw", propagation: Optional[str] = None) -> MountEntry`
- `umount(target: str) -> None`
- `pivot_root(new_root: str, put_old: str) -> None`
- `find_mount(target: str) -> Optional[MountEntry]`
- `get_mounts_by_type(fs_type: str) -> list[MountEntry]`
- `set_propagation(target: str, propagation: str) -> None`

**`UTSNamespace(Namespace)`**
- Props: `hostname`, `domainname`, `hostname_history`
- `sethostname(hostname: str) -> None`
- `setdomainname(domainname: str) -> None`
- `gethostname() -> str`
- `getdomainname() -> str`

**`IPCNamespace(Namespace)`**
- Props: `shm_segments`, `semaphore_sets`, `message_queues`, `shm_count`, `sem_count`, `msq_count`
- `shmget(key: int, size: int, owner_pid: int = 0) -> int`
- `shmctl_rm(shm_id: int) -> None`
- `shmat(shm_id: int, pid: int) -> None`
- `shmdt(shm_id: int, pid: int) -> None`
- `semget(key: int, num_sems: int, owner_pid: int = 0) -> int`
- `semctl_rm(sem_id: int) -> None`
- `msgget(key: int, max_bytes: int = 16384, owner_pid: int = 0) -> int`
- `msgctl_rm(msq_id: int) -> None`
- `msgsnd(msq_id: int) -> None`
- `msgrcv(msq_id: int) -> None`
- `get_total_ipc_objects() -> int`

**`USERNamespace(Namespace)`**
- Props: `uid_map`, `gid_map`, `capabilities`, `is_rootless`, `owner_uid`, `owner_gid`
- `translate_uid_to_host(inner_uid: int) -> int`
- `translate_uid_from_host(outer_uid: int) -> int`
- `translate_gid_to_host(inner_gid: int) -> int`
- `translate_gid_from_host(outer_gid: int) -> int`
- `has_capability(capability: str) -> bool`
- `drop_capability(capability: str) -> None`
- `add_capability(capability: str) -> None`
- `set_rootless() -> None`
- `get_effective_uid(inner_uid: int) -> dict[str, Any]`

**`CGROUPNamespace(Namespace)`**
- Props: `cgroup_root`, `cgroup_entries`, `controllers`, `entry_count`
- `add_cgroup(path: str, controllers: Optional[set[str]] = None) -> CgroupEntry`
- `remove_cgroup(path: str) -> None`
- `add_process_to_cgroup(path: str, pid: int) -> None`
- `remove_process_from_cgroup(path: str, pid: int) -> None`
- `virtualize_path(host_path: str) -> str`
- `is_visible(host_path: str) -> bool`
- `get_controllers_for_path(path: str) -> set[str]`

### `NamespaceSet`

Container for one namespace instance per type.

- Props: `set_id -> str`, `created_at -> float`
- `get(ns_type: NamespaceType) -> Optional[Namespace]`
- `has(ns_type: NamespaceType) -> bool`
- `types() -> set[NamespaceType]`
- `count() -> int`
- `to_dict() -> dict[str, str]`
- `get_all() -> list[Namespace]`
- `get_clone_flags() -> int`

### `NamespaceManager` (singleton)

Central manager for namespace lifecycle.

- Props: `root_namespaces -> NamespaceSet`, `registry -> dict[str, Namespace]`, `process_namespaces -> dict[int, NamespaceSet]`, `total_created -> int`, `total_destroyed -> int`, `active_count -> int`, `gc_count -> int`
- `get_namespace(ns_id: str) -> Optional[Namespace]`
- `get_namespaces_by_type(ns_type: NamespaceType) -> list[Namespace]`
- `clone(pid: int, flags: int, parent_pid: Optional[int] = None) -> NamespaceSet`
- `unshare(pid: int, flags: int) -> NamespaceSet`
- `setns(pid: int, ns_id: str) -> None`
- `destroy_namespace(ns_id: str) -> None`
- `garbage_collect() -> int`
- `remove_process(pid: int) -> None`
- `get_statistics() -> dict[str, Any]`
- `render_hierarchy(ns_type: Optional[NamespaceType] = None) -> str`
- `inspect_namespace(ns_id: str) -> dict[str, Any]`

### `FizzNSDashboard`

ASCII dashboard for namespace state visualization.

### `FizzNSMiddleware(IMiddleware)`

- Props: `manager -> NamespaceManager`, `evaluations_processed -> int`
- `get_name() -> str`
- `get_priority() -> int`  (returns 106)
- `render_dashboard(width: int = 72) -> str`
- `render_hierarchy(ns_type: Optional[NamespaceType] = None) -> str`
- `inspect_namespace(ns_id: str) -> str`

### Factory Function

```python
def create_fizzns_subsystem(
    default_hostname: str = DEFAULT_HOSTNAME,
    default_domainname: str = DEFAULT_DOMAINNAME,
    enable_dashboard: bool = False,
    event_bus: Optional[Any] = None,
) -> tuple[NamespaceManager, FizzNSMiddleware]
```

---

## 2. FizzCgroup — Control Group Resource Accounting & Limiting

**File**: `enterprise_fizzbuzz/infrastructure/fizzcgroup.py`
**Middleware Priority**: 107

### Constants

| Name | Value | Description |
|------|-------|-------------|
| `DEFAULT_CPU_WEIGHT` | `100` | Default CPU weight |
| `MIN_CPU_WEIGHT` / `MAX_CPU_WEIGHT` | `1` / `10000` | Weight range |
| `DEFAULT_CPU_QUOTA` | `-1` | Unbounded CPU quota |
| `DEFAULT_CPU_PERIOD` | `100000` | 100ms period |
| `DEFAULT_MEMORY_MAX` | `-1` | Unlimited memory |
| `DEFAULT_PIDS_MAX` | `-1` | Unlimited PIDs |
| `MAX_CGROUP_DEPTH` | `32` | Max hierarchy depth |

### Enums

**`CgroupControllerType(Enum)`** — CPU, MEMORY, IO, PIDS

**`CgroupState(Enum)`** — ACTIVE, DRAINING, REMOVED

**`OOMPolicy(Enum)`** — KILL_LARGEST, KILL_OLDEST, KILL_LOWEST_PRIORITY

**`ThrottleState(Enum)`** — RUNNING, THROTTLED

### Dataclasses

| Class | Description |
|-------|-------------|
| `CPUStats` | CPU accounting (usage_usec, user_usec, system_usec, throttled_usec, periods, throttled_periods) |
| `MemoryStats` | Memory accounting (current, high_events, max_events, oom_kills, rss, cache, kernel, swap) |
| `IOStats` | I/O accounting (rbytes, wbytes, rios, wios) |
| `PIDsStats` | PIDs accounting (current, limit, events) |
| `CPUConfig` | CPU configuration (weight, quota, period) |
| `MemoryConfig` | Memory configuration (max, high, low, min, swap_max) |
| `IOConfig` | I/O configuration (weight, rbps_max, wbps_max, riops_max, wiops_max) |
| `PIDsConfig` | PIDs configuration (max) |
| `ResourceReport` | Aggregate resource report |
| `OOMEvent` | OOM kill record |

### Controllers

**`CPUController`**
- Props: `config`, `stats`, `throttle_state`, `weight`, `quota`, `period`, `total_charge`
- `set_weight(weight: int) -> None`
- `set_bandwidth(quota: int, period: int = DEFAULT_CPU_PERIOD) -> None`
- `charge(usage_usec: int, user_pct: float = 0.7) -> bool`
- `reset_period() -> None`
- `get_utilization() -> float`
- `get_effective_cpus() -> float`
- `get_weight_share(total_weight: int) -> float`
- `is_throttled() -> bool`
- `get_throttle_ratio() -> float`
- `to_dict() -> dict[str, Any]`

**`MemoryController`**
- Props: `config`, `stats`, `current`, `charges`, `is_throttled`
- `set_max(max_bytes: int) -> None`
- `set_high(high_bytes: int) -> None`
- `set_low(low_bytes: int) -> None`
- `set_min(min_bytes: int) -> None`
- `charge(pid: int, bytes_amount: int, category: str = "rss") -> bool`
- `release(pid: int, bytes_amount: int, category: str = "rss") -> None`
- `release_all_for_pid(pid: int) -> None`
- `get_utilization() -> float`
- `get_available() -> int`
- `is_under_pressure() -> bool`
- `is_protected(amount: int) -> bool`
- `get_process_charge(pid: int) -> int`
- `to_dict() -> dict[str, Any]`

**`IOController`**
- Props: `config`, `stats`, `weight`, `is_throttled`
- `set_weight(weight: int) -> None`
- `set_max(device: str, rbps: int, wbps: int, riops: int, wiops: int) -> None`
- `charge_read(device: str, bytes_count: int, ops: int = 1) -> bool`
- `charge_write(device: str, bytes_count: int, ops: int = 1) -> bool`
- `get_device_stats(device: str) -> Optional[IOStats]`
- `get_devices() -> list[str]`
- `get_weight_share(total_weight: int) -> float`
- `to_dict() -> dict[str, Any]`

**`PIDsController`**
- Props: `config`, `stats`, `current`, `limit`, `processes`
- `set_max(max_pids: int) -> None`
- `can_fork() -> bool`
- `fork(pid: int) -> bool`
- `exit(pid: int) -> None`
- `add_process(pid: int) -> bool`
- `remove_process(pid: int) -> None`
- `to_dict() -> dict[str, Any]`

**`OOMKiller`**
- Props: `policy`, `history`, `total_kills`
- `set_policy(policy: OOMPolicy) -> None`
- `add_process_metadata(pid: int, ...) -> None`
- `remove_process_metadata(pid: int) -> None`
- `trigger_oom(cgroup_path: str, process_charges: dict[int, int], ...) -> Optional[OOMEvent]`
- `get_recent_events(count: int = 10) -> list[OOMEvent]`
- `get_statistics() -> dict[str, Any]`
- `to_dict() -> dict[str, Any]`

### `CgroupNode`

- Props: `cgroup_id`, `name`, `path`, `parent`, `children`, `state`, `created_at`, `processes`, `subtree_control`, `oom_killer`, `controller_types`, `depth`, `is_leaf`, `is_root`
- `add_child(child: CgroupNode) -> None`
- `remove_child(child: CgroupNode) -> None`
- `get_controller(controller_type: CgroupControllerType) -> Optional[Any]`
- `has_controller(controller_type: CgroupControllerType) -> bool`
- `attach_process(pid: int) -> None`
- `detach_process(pid: int) -> None`
- `get_recursive_process_count() -> int`
- `get_recursive_memory_usage() -> int`
- `mark_draining() -> None`
- `mark_removed() -> None`
- `to_dict() -> dict[str, Any]`

### `CgroupHierarchy`

- Props: `root`, `total_created`, `total_removed`, `active_count`
- `create(path: str, controllers: Optional[set[CgroupControllerType]] = None) -> CgroupNode`
- `remove(path: str) -> None`
- `get(path: str) -> Optional[CgroupNode]`
- `exists(path: str) -> bool`
- `attach(pid: int, path: str) -> None`
- `migrate(pid: int, from_path: str, to_path: str) -> None`
- `get_all_paths() -> list[str]`
- `get_all_processes() -> dict[str, set[int]]`
- `find_process(pid: int) -> Optional[str]`
- `render_tree(root_path: Optional[str] = None) -> str`
- `get_statistics() -> dict[str, Any]`

### `CgroupManager` (singleton)

- Props: `hierarchy`, `root`, `oom_policy`
- `create_cgroup(path: str, controllers: Optional[set[CgroupControllerType]] = None) -> CgroupNode`
- `remove_cgroup(path: str) -> None`
- `get_cgroup(path: str) -> Optional[CgroupNode]`
- `attach_process(pid: int, path: str) -> None`
- `set_cpu_weight(path: str, weight: int) -> None`
- `set_cpu_bandwidth(path: str, quota: int, period: int = DEFAULT_CPU_PERIOD) -> None`
- `set_memory_max(path: str, max_bytes: int) -> None`
- `set_pids_max(path: str, max_pids: int) -> None`
- `charge_cpu(path: str, usage_usec: int, user_pct: float = 0.7) -> bool`
- `charge_memory(path: str, pid: int, bytes_amount: int, category: str = "rss") -> bool`
- `charge_io_read(path: str, device: str, bytes_count: int) -> bool`
- `charge_io_write(path: str, device: str, bytes_count: int) -> bool`
- `migrate_process(pid: int, from_path: str, to_path: str) -> None`
- `find_process_cgroup(pid: int) -> Optional[str]`
- `render_tree(root_path: Optional[str] = None) -> str`
- `get_statistics() -> dict[str, Any]`
- `to_dict() -> dict[str, Any]`

### `ResourceAccountant`

- Props: `report_count`
- `generate_report(path: str) -> ResourceReport`
- `generate_all_reports() -> dict[str, ResourceReport]`
- `get_hpa_metrics(path: str) -> dict[str, float]`
- `get_top_by_cpu(count: int = 10) -> list[tuple[str, float]]`
- `get_top_by_memory(count: int = 10) -> list[tuple[str, float]]`
- `to_dict() -> dict[str, Any]`

### `FizzCgroupDashboard`, `FizzCgroupMiddleware(IMiddleware)`

Middleware: priority 107
- Props: `manager`, `accountant`, `evaluations_processed`
- `get_name() -> str`, `get_priority() -> int`
- `render_dashboard(width: Optional[int] = None) -> str`
- `render_tree(root_path: Optional[str] = None) -> str`
- `render_stats(path: str) -> str`

### Factory Function

```python
def create_fizzcgroup_subsystem(
    oom_policy: str = "kill_largest",
    default_cpu_weight: int = DEFAULT_CPU_WEIGHT,
    default_memory_max: int = DEFAULT_MEMORY_MAX,
    default_pids_max: int = DEFAULT_PIDS_MAX,
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
    enable_dashboard: bool = False,
    event_bus: Optional[Any] = None,
) -> tuple[CgroupManager, FizzCgroupMiddleware]
```

---

## 3. FizzOCI — OCI-Compliant Container Runtime

**File**: `enterprise_fizzbuzz/infrastructure/fizzoci.py`
**Middleware Priority**: 108

### Constants

| Name | Value |
|------|-------|
| `OCI_SPEC_VERSION` | `"1.0.2"` |
| `DEFAULT_HOOK_TIMEOUT` | `30.0` |
| `DEFAULT_MAX_CONTAINERS` | `256` |
| `DEFAULT_SECCOMP_PROFILE` | `"default"` |
| `SIGNAL_MAP` | dict, SIGHUP..SIGSYS (31 signals) |
| `DEFAULT_CAPABILITIES` | 14 Docker-compatible capabilities |
| `ALL_CAPABILITIES` | 41 Linux capabilities |
| `MASKED_PATHS` | Sensitive /proc paths |

### Enums

| Enum | Values |
|------|--------|
| `OCIState` | CREATING, CREATED, RUNNING, STOPPED |
| `SeccompAction` | SCMP_ACT_KILL, SCMP_ACT_KILL_PROCESS, SCMP_ACT_TRAP, SCMP_ACT_ERRNO, SCMP_ACT_TRACE, SCMP_ACT_ALLOW, SCMP_ACT_LOG |
| `SeccompOperator` | SCMP_CMP_NE, SCMP_CMP_LT, SCMP_CMP_LE, SCMP_CMP_EQ, SCMP_CMP_GE, SCMP_CMP_GT, SCMP_CMP_MASKED_EQ |
| `MountPropagation` | RPRIVATE, PRIVATE, RSLAVE, SLAVE, RSHARED, SHARED |
| `HookType` | PRESTART, CREATE_RUNTIME, CREATE_CONTAINER, START_CONTAINER, POSTSTART, POSTSTOP |

### Dataclasses

`OCIRoot`, `MountSpec`, `RlimitConfig`, `UserSpec`, `CapabilitySet`, `ContainerProcess`, `SeccompArg`, `SeccompRule`, `SeccompProfile`, `HookSpec`, `ContainerHooks`, `LinuxNamespaceConfig`, `LinuxResourcesCPU`, `LinuxResourcesMemory`, `LinuxResourcesPIDs`, `LinuxResourcesIO`, `LinuxResources`, `DeviceRule`, `LinuxConfig`, `OCIConfig`, `OCIBundle`, `OCIStateReport`

### `OCIContainer`

- Props: `container_id`, `state`, `pid`, `config`, `bundle`, `created_at`, `started_at`, `stopped_at`, `exit_code`, `annotations`, `namespace_ids`, `cgroup_path`, `mounts_processed`, `seccomp_applied`, `capabilities_dropped`, `rlimits_applied`, `hooks_executed`, `lifecycle_events`
- `transition_to(target: OCIState) -> None`
- `set_pid(pid: int) -> None`
- `set_namespace_ids(ns_ids: List[str]) -> None`
- `set_cgroup_path(path: str) -> None`
- `add_processed_mount(mount: MountSpec) -> None`
- `mark_seccomp_applied() -> None`
- `mark_capabilities_dropped() -> None`
- `mark_rlimits_applied() -> None`
- `record_hook_execution(hook_type: str, hook_path: str) -> None`
- `set_exit_code(code: int) -> None`
- `get_state_report() -> OCIStateReport`
- `uptime_seconds() -> float`

### `HookExecutor`

- Props: `execution_log`, `default_timeout`
- `execute_hooks(hooks: List[HookSpec], container_id: str, ...) -> None`
- `get_log_for_container(container_id: str) -> List[Dict[str, Any]]`
- `clear_log() -> None`

### `SeccompEngine`

- Props: `profiles`, `evaluation_count`, `denied_count`, `evaluation_log`
- `register_profile(name: str, profile: SeccompProfile) -> None`
- `get_profile(name: str) -> SeccompProfile`
- `validate_profile(profile: SeccompProfile) -> List[str]`
- `evaluate_syscall(profile: SeccompProfile, syscall: str, args: ...) -> SeccompAction`
- `get_stats() -> Dict[str, Any]`

### `MountProcessor`

- Props: `mount_log`
- `process_mounts(container: OCIContainer, ...) -> None`
- `get_masked_paths(container_id: str) -> List[str]`
- `get_readonly_paths(container_id: str) -> List[str]`
- `cleanup_container(container_id: str) -> None`

### `ContainerCreator`

Internal orchestrator for the create lifecycle (hooks, seccomp, mounts, namespaces, cgroups).

### `OCIRuntime` (singleton)

- Props: `containers`, `container_count`, `max_containers`, `hook_executor`, `seccomp_engine`, `mount_processor`, `operation_log`
- `create(bundle_path: str, container_id: Optional[str] = None, config_dict: Optional[Dict[str, Any]] = None) -> OCIContainer`
- `start(container_id: str) -> None`
- `kill(container_id: str, sig: str = "SIGTERM") -> None`
- `delete(container_id: str) -> None`
- `state(container_id: str) -> OCIStateReport`
- `generate_default_spec() -> Dict[str, Any]`
- `get_stats() -> Dict[str, Any]`

### `OCIRuntimeMiddleware(IMiddleware)`

Priority 108
- Props: `runtime`, `evaluation_count`, `containers_created`, `containers_completed`, `dashboard`
- `get_name() -> str`, `get_priority() -> int`
- `render_dashboard() -> str`
- `render_container_list() -> str`
- `render_container_state(container_id: str) -> str`
- `render_default_spec() -> str`
- `render_lifecycle() -> str`

### `OCIDashboard`

- Props: `width`
- `render() -> str`
- `render_container_list() -> str`
- `render_lifecycle() -> str`

### Factory Function

```python
def create_fizzoci_subsystem(
    default_seccomp_profile: str = DEFAULT_SECCOMP_PROFILE,
    default_hook_timeout: float = DEFAULT_HOOK_TIMEOUT,
    max_containers: int = DEFAULT_MAX_CONTAINERS,
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
    enable_dashboard: bool = False,
    namespace_manager: Optional[Any] = None,
    cgroup_manager: Optional[Any] = None,
    event_bus: Optional[Any] = None,
) -> tuple[OCIRuntime, OCIRuntimeMiddleware]
```

---

## 4. FizzOverlay — Copy-on-Write Union Filesystem

**File**: `enterprise_fizzbuzz/infrastructure/fizzoverlay.py`
**Middleware Priority**: 109

### Constants

| Name | Value |
|------|-------|
| `WHITEOUT_PREFIX` | `".wh."` |
| `OPAQUE_WHITEOUT` | `".wh..wh..opq"` |
| `DEFAULT_MAX_LAYERS` | `128` |
| `DEFAULT_LAYER_CACHE_SIZE` | `64` |
| `DEFAULT_COMPRESSION` | `"gzip"` |
| `TAR_BLOCK_SIZE` | `512` |
| `LAYER_MEDIA_TYPE_TAR` | `"application/vnd.oci.image.layer.v1.tar"` |
| `LAYER_MEDIA_TYPE_TAR_GZIP` | `"application/vnd.oci.image.layer.v1.tar+gzip"` |
| `LAYER_MEDIA_TYPE_TAR_ZSTD` | `"application/vnd.oci.image.layer.v1.tar+zstd"` |

### Enums

| Enum | Values |
|------|--------|
| `LayerType` | BASE, DIFF, SCRATCH |
| `MountState` | UNMOUNTED, MOUNTED, FAILED |
| `DiffType` | ADDED, MODIFIED, DELETED |
| `CompressionType` | NONE, GZIP, ZSTD |
| `SnapshotState` | PREPARING, COMMITTED, ABORTED |

### Dataclasses

`LayerDescriptor`, `LayerEntry`, `OverlayMountConfig`, `DiffEntry`, `SnapshotDescriptor`, `TarEntry`, `LayerCacheStats`

### `Layer`

- Props: `entries`, `layer_type`, `parent_digest`, `annotations`, `created_at`, `frozen`, `entry_count`
- `add_entry(entry: LayerEntry) -> None`
- `remove_entry(path: str) -> None`
- `get_entry(path: str) -> Optional[LayerEntry]`
- `has_entry(path: str) -> bool`
- `list_entries(directory: str = "") -> List[LayerEntry]`
- `compute_digest() -> str`
- `compute_diff_id() -> str`
- `freeze() -> str`
- `verify(expected_digest: str) -> bool`
- `total_size() -> int`
- `to_descriptor() -> LayerDescriptor`
- `clone() -> Layer`

### `LayerStore` (singleton)

- Props: `layer_count`, `max_layers`, `total_adds`, `total_removes`, `dedup_saves`
- `add(layer: Layer) -> str`
- `get(digest: str) -> Layer`
- `has(digest: str) -> bool`
- `remove(digest: str) -> None`
- `ref_count(digest: str) -> int`
- `increment_ref(digest: str) -> int`
- `decrement_ref(digest: str) -> int`
- `gc() -> List[str]`
- `list_layers() -> List[LayerDescriptor]`
- `total_size() -> int`
- `utilization() -> float`
- `dedup_ratio() -> float`
- `verify_all() -> List[str]`

### `WhiteoutManager`

- `create_whiteout(layer: Layer, path: str) -> LayerEntry`
- `create_opaque_whiteout(layer: Layer, directory: str) -> LayerEntry`
- `filter_whiteouts(entries: List[LayerEntry]) -> List[LayerEntry]`
- `collect_whiteouts(layer: Layer) -> Dict[str, str]`
- `collect_opaque_dirs(layer: Layer) -> Set[str]`

### `CopyOnWrite`

- Props: `copy_count`, `bytes_copied`
- `copy_up(path: str, lower: Layer, upper: Layer) -> LayerEntry`
- `needs_copy_up(path: str, upper: Layer) -> bool`

### `OverlayMount`

- Props: `mount_point`, `state`, `readonly`, `lower_count`, `upper_layer`, `lower_layers`, `read_count`, `write_count`, `delete_count`
- `mount() -> None`
- `unmount() -> None`
- `lookup(path: str) -> Optional[LayerEntry]`
- `read(path: str) -> Optional[bytes]`
- `write(path: str, data: bytes, permissions: int = 0o644) -> None`
- `mkdir(path: str, permissions: int = 0o755) -> None`
- `delete(path: str) -> None`
- `list_dir(directory: str = "") -> List[LayerEntry]`
- `exists(path: str) -> bool`
- `get_all_paths() -> Set[str]`

### `Snapshotter`

- Props: `snapshot_count`
- `prepare(key: str, parent_layers: List[Layer]) -> OverlayMount`
- `commit(key: str) -> str`
- `abort(key: str) -> None`
- `remove(key: str) -> None`
- `get_snapshot(key: str) -> SnapshotDescriptor`
- `get_mount(key: str) -> OverlayMount`
- `list_snapshots() -> List[SnapshotDescriptor]`

### `DiffEngine`

- Props: `diff_count`
- `diff_layers(lower: Layer, upper: Layer) -> List[DiffEntry]`
- `diff_overlay(overlay: OverlayMount) -> List[DiffEntry]`
- `apply_diff(target: Layer, diffs: List[DiffEntry]) -> None`

### `LayerCache`

- Props: `stats`, `size`
- `get(digest: str) -> Optional[Layer]`
- `put(digest: str, layer: Layer) -> None`
- `remove(digest: str) -> bool`
- `clear() -> int`
- `contains(digest: str) -> bool`

### `TarArchiver`

- `archive(layer: Layer, compression: CompressionType = CompressionType.GZIP) -> bytes`
- `unarchive(data: bytes, ...) -> Layer`

### `OverlayFSProvider`

- Props: `name`, `mount_count`
- `mount(layers: List[Layer], mount_point: str, ...) -> OverlayMount`
- `unmount(mount_point: str) -> None`
- `read(mount_point: str, path: str) -> Optional[bytes]`
- `write(mount_point: str, path: str, data: bytes) -> None`
- `list_mounts() -> Dict[str, str]`
- `supports_overlay() -> bool`

### `FizzOverlayMiddleware(IMiddleware)`, `OverlayDashboard`

Priority 109
- `get_name()`, `get_priority()`, `render_layer_list()`, `render_mount_list()`, `render_diff_summary()`, `render_cache_stats()`, `render_dashboard()`, `render_snapshot_list()`

### Factory Function

```python
def create_fizzoverlay_subsystem(
    max_layers: int = DEFAULT_MAX_LAYERS,
    layer_cache_size: int = DEFAULT_LAYER_CACHE_SIZE,
    default_compression: str = DEFAULT_COMPRESSION,
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
    enable_dashboard: bool = False,
    event_bus: Optional[Any] = None,
) -> tuple[LayerStore, FizzOverlayMiddleware]
```

---

## 5. FizzRegistry — OCI Distribution-Compliant Image Registry

**File**: `enterprise_fizzbuzz/infrastructure/fizzregistry.py`
**Middleware Priority**: 110

### Constants

| Name | Value |
|------|-------|
| `OCI_MANIFEST_MEDIA_TYPE` | `"application/vnd.oci.image.manifest.v1+json"` |
| `OCI_INDEX_MEDIA_TYPE` | `"application/vnd.oci.image.index.v1+json"` |
| `OCI_CONFIG_MEDIA_TYPE` | `"application/vnd.oci.image.config.v1+json"` |
| `OCI_SIGNATURE_MEDIA_TYPE` | `"application/vnd.dev.cosign.simplesigning.v1+json"` |
| `DEFAULT_MAX_BLOBS` | `4096` |
| `DEFAULT_MAX_REPOS` | `256` |
| `DEFAULT_MAX_TAGS` | `1024` |
| `DEFAULT_GC_GRACE_PERIOD` | `86400.0` (24h) |
| `DIGEST_PREFIX` | `"sha256:"` |
| `SCRATCH_IMAGE` | `"scratch"` |
| `SCHEMA_VERSION` | `2` |

### Enums

| Enum | Values |
|------|--------|
| `ManifestSchemaVersion` | V1, V2 |
| `ImagePlatformOS` | LINUX, WINDOWS, DARWIN, FREEBSD, FIZZBUZZ_OS |
| `ImagePlatformArch` | AMD64, ARM64, ARM, PPC64LE, S390X, FIZZ_ARCH |
| `TagState` | ACTIVE, DEPRECATED, DELETED |
| `GCPhase` | MARK, SWEEP |
| `SignatureStatus` | SIGNED, UNSIGNED, INVALID |
| `VulnerabilitySeverity` | CRITICAL, HIGH, MEDIUM, LOW, NEGLIGIBLE |
| `FizzFileInstruction` | FROM, RUN, COPY, ADD, ENV, WORKDIR, ENTRYPOINT, CMD, EXPOSE, LABEL, VOLUME, USER, ARG, STOPSIGNAL |
| `BuildPhase` | PARSING, BUILDING, CACHING, COMMITTING, COMPLETE |
| `RegistryOperation` | PUSH_BLOB, PULL_BLOB, DELETE_BLOB, PUSH_MANIFEST, PULL_MANIFEST, DELETE_MANIFEST, LIST_TAGS, CATALOG |

### Dataclasses

`OCIDescriptor`, `OCIPlatform`, `OCIManifest`, `OCIImageIndex`, `RootFS`, `HistoryEntry`, `ContainerConfig`, `OCIImageConfig`, `TagReference`, `FizzFileStep`, `BuildContext`, `ImageSignature`, `VulnerabilityFinding`, `VulnerabilityReport`, `GCReport`, `RegistryStats`

### `BlobStore` (singleton)

- `exists(digest: str) -> bool`
- `get(digest: str) -> bytes`
- `put(data: bytes, media_type: str = OCI_LAYER_MEDIA_TYPE) -> str`
- `delete(digest: str) -> None`
- `stat(digest: str) -> Tuple[int, str]`
- `increment_ref(digest: str) -> None`
- `decrement_ref(digest: str) -> None`
- `get_ref_count(digest: str) -> int`
- `get_unreferenced(grace_period: float = DEFAULT_GC_GRACE_PERIOD) -> List[str]`
- Props: `blob_count`, `total_bytes`, `digests`, `total_pushes`, `total_pulls`

### `Repository`

- Props: `name`, `tag_count`, `manifest_count`, `created_at`
- `put_manifest(reference: str, manifest: OCIManifest) -> str`
- `get_manifest(reference: str) -> OCIManifest`
- `delete_manifest(reference: str) -> str`
- `list_tags() -> List[str]`
- `get_tag(tag_name: str) -> TagReference`
- `has_tag(tag_name: str) -> bool`
- `get_manifest_digests() -> List[str]`
- `tag_history(tag_name: str) -> List[Tuple[str, float]]`

### `RegistryAPI`

- `push_blob(repository: str, data: bytes, media_type: str = ...) -> str`
- `head_blob(repository: str, digest: str) -> Tuple[int, str]`
- `get_blob(repository: str, digest: str) -> bytes`
- `delete_blob(repository: str, digest: str) -> None`
- `put_manifest(repository: str, reference: str, manifest: OCIManifest) -> str`
- `get_manifest(repository: str, reference: str) -> OCIManifest`
- `head_manifest(repository: str, reference: str) -> str`
- `delete_manifest(repository: str, reference: str) -> str`
- `catalog() -> List[str]`
- `list_tags(repository: str) -> List[str]`
- Props: `repo_count`, `op_counts`
- `get_repo(name: str) -> Repository`

### `FizzFileParser`

- `parse(content: str) -> List[FizzFileStep]`

### `ImageBuilder`

- Props: `cache_hits`, `cache_misses`, `builds_completed`, `cache_size`
- `build(fizzfile_content: str, tag: str = DEFAULT_BUILD_TAG, ...) -> OCIManifest`

### `GarbageCollector`

- `collect() -> GCReport`
- Props: `gc_runs`, `total_bytes_reclaimed`
- `get_last_result() -> Optional[GCReport]`
- `get_history(limit: int = 10) -> List[GCReport]`

### `ImageSigner`

- `sign(manifest_digest: str, signer: str = "Bob McFizzington") -> ImageSignature`
- `verify(manifest_digest: str) -> ImageSignature`
- `get_signature(manifest_digest: str) -> Optional[ImageSignature]`
- Props: `signed_count`, `key_id`

### `VulnerabilityScanner`

- `scan(image_ref: str, manifest: OCIManifest) -> VulnerabilityReport`
- `get_report(image_ref: str) -> Optional[VulnerabilityReport]`
- Props: `scanned_count`, `cve_count`

### `FizzRegistryMiddleware(IMiddleware)`, `RegistryDashboard`

Priority 110
- `render_catalog()`, `render_stats()`, `render_gc_report()`, `render_scan_summary()`, `render_build_stats()`

### Factory Function

```python
def create_fizzregistry_subsystem(
    max_blobs: int = DEFAULT_MAX_BLOBS,
    max_repos: int = DEFAULT_MAX_REPOS,
    max_tags: int = DEFAULT_MAX_TAGS,
    gc_grace_period: float = DEFAULT_GC_GRACE_PERIOD,
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
    enable_dashboard: bool = False,
    event_bus: Optional[Any] = None,
) -> tuple[RegistryAPI, FizzRegistryMiddleware]
```

---

## 6. FizzCNI — Container Network Interface Plugin System

**File**: `enterprise_fizzbuzz/infrastructure/fizzcni.py`
**Middleware Priority**: 111

### Constants

| Name | Value |
|------|-------|
| `CNI_SPEC_VERSION` | `"1.0.0"` |
| `DEFAULT_BRIDGE_NAME` | `"fizzbr0"` |
| `DEFAULT_SUBNET` | `"10.244.0.0/16"` |
| `DEFAULT_GATEWAY` | `"10.244.0.1"` |
| `DEFAULT_LEASE_DURATION` | `3600.0` |
| `DEFAULT_MTU` | `1500` |
| `DEFAULT_VXLAN_PORT` | `4789` |
| `DEFAULT_DNS_DOMAIN` | `"cluster.fizz"` |
| `DEFAULT_DNS_TTL` | `30` |
| `MAX_VETH_PAIRS` | `4096` |
| `MAX_PORT_MAPPINGS` | `65535` |
| `MAX_DNS_RECORDS` | `8192` |
| `MAX_POLICIES` | `1024` |
| `NAT_TABLE_SIZE` | `16384` |
| `STP_HELLO_INTERVAL` | `2.0` |

### Enums

| Enum | Values |
|------|--------|
| `CNIOperation` | ADD, DEL, CHECK, VERSION |
| `PluginType` | BRIDGE, HOST, NONE, OVERLAY |
| `InterfaceState` | DOWN, UP, DELETED |
| `LeaseState` | ACTIVE, EXPIRED, RELEASED |
| `PolicyAction` | ALLOW, DENY |
| `PolicyDirection` | INGRESS, EGRESS |
| `STPPortState` | DISABLED, BLOCKING, LISTENING, LEARNING, FORWARDING |
| `DNSRecordType` | A, AAAA, CNAME, PTR, SRV |

### Dataclasses

`CNIConfig`, `CNIResult`, `VethPair`, `BridgeInterface`, `IPAllocation`, `Lease`, `PortMapping`, `DNSRecord`, `NetworkPolicyRule`, `NetworkPolicySpec`, `CNIStats`

### `CNIPlugin(ABC)` — Abstract Base

- `add(container_id: str, netns: str, ifname: str, config: CNIConfig) -> CNIResult` (abstract)
- `delete(container_id: str, netns: str, ifname: str, config: CNIConfig) -> None` (abstract)
- `check(container_id: str, netns: str, ifname: str, config: CNIConfig) -> bool` (abstract)
- `version() -> List[str]`
- `plugin_type() -> PluginType` (abstract property)

### Concrete Plugins

**`BridgePlugin(CNIPlugin)`** — bridge + veth pair + STP. `mac_lookup(mac: str)`, `stats()`, also `plugin_type = BRIDGE`

**`HostPlugin(CNIPlugin)`** — host network namespace sharing. `stats()`, `plugin_type = HOST`

**`NonePlugin(CNIPlugin)`** — loopback only. `stats()`, `plugin_type = NONE`

**`OverlayPlugin(CNIPlugin)`** — VXLAN overlay networking. `register_vtep(vtep_ip, vtep_port)`, `learn_mac(mac, vtep_ip)`, `encapsulate(...)`, `stats()`, `plugin_type = OVERLAY`

### `IPAMPlugin`

- `allocate(container_id: str, ifname: str = "eth0") -> IPAllocation`
- `release(container_id: str) -> None`
- `renew(container_id: str) -> Lease`
- `has_allocation(container_id: str) -> bool`
- `get_allocation(container_id: str) -> Optional[IPAllocation]`
- `detect_conflicts() -> List[Tuple[str, str, str]]`
- Props: `pool_size`, `total_allocated`, `total_expired`, `utilization`

### `PortMapper`

- `add_mapping(host_port: int, container_ip: str, container_port: int, protocol: str = "tcp", container_id: str = "") -> PortMapping`
- `remove_mapping(mapping_id: str) -> None`
- `remove_container_mappings(container_id: str) -> int`
- `resolve(host_port: int, protocol: str = "tcp") -> Optional[PortMapping]`
- `get_container_mappings(container_id: str) -> List[PortMapping]`
- Props: `total_mappings`

### `ContainerDNS`

- `add_record(hostname: str, record_type: DNSRecordType, value: str, container_id: str = "", ttl: int = ...) -> DNSRecord`
- `remove_container_records(container_id: str) -> int`
- `resolve(hostname: str, record_type: DNSRecordType = DNSRecordType.A) -> Optional[DNSRecord]`
- `register_container(container_id: str, container_name: str, ip: str) -> None`
- Props: `total_records`, `total_queries`

### `NetworkPolicyEngine`

- `add_policy(policy: NetworkPolicySpec) -> None`
- `remove_policy(policy_id: str) -> None`
- `set_container_labels(container_id: str, labels: Dict[str, str]) -> None`
- `remove_container(container_id: str) -> None`
- `evaluate(source_id: str, dest_id: str, port: int, protocol: str = "tcp") -> PolicyAction`
- `get_applicable_policies(container_id: str) -> List[NetworkPolicySpec]`
- Props: `total_policies`, `evaluation_count`, `allow_count`, `deny_count`

### `CNIManager`

Central dispatcher for container network operations.

- `add(container_id: str, netns: str = "", ifname: str = "eth0", plugin_type: Optional[PluginType] = None, config: Optional[CNIConfig] = None, container_name: Optional[str] = None, labels: Optional[Dict[str, str]] = None) -> CNIResult`
- `delete(container_id: str, netns: str = "", ifname: str = "eth0", config: Optional[CNIConfig] = None) -> None`
- `check(container_id: str, ...) -> bool`
- `get_plugin(plugin_type: PluginType) -> Optional[CNIPlugin]`
- `list_networks() -> List[Dict[str, Any]]`
- `get_stats() -> CNIStats`
- Props: `active_container_count`
- Sub-systems: `ipam`, `port_mapper`, `dns`, `policy_engine`, `plugins`

### `CNIDashboard`, `FizzCNIMiddleware(IMiddleware)`

Priority 111
- `render_dashboard()`, `render_topology()`, `render_ipam_stats()`, `render_port_mappings()`, `render_policies()`, `render_stats()`

### Factory Function

```python
def create_fizzcni_subsystem(
    subnet: str = DEFAULT_SUBNET,
    gateway: str = DEFAULT_GATEWAY,
    bridge_name: str = DEFAULT_BRIDGE_NAME,
    lease_duration: float = DEFAULT_LEASE_DURATION,
    mtu: int = DEFAULT_MTU,
    dns_domain: str = DEFAULT_DNS_DOMAIN,
    dns_ttl: int = DEFAULT_DNS_TTL,
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
    enable_dashboard: bool = False,
    event_bus: Optional[Any] = None,
) -> tuple[CNIManager, FizzCNIMiddleware]
```

---

## 7. FizzContainerd — High-Level Container Daemon & Shim Architecture

**File**: `enterprise_fizzbuzz/infrastructure/fizzcontainerd.py`
**Middleware Priority**: 112

### Constants

| Name | Value |
|------|-------|
| `CONTAINERD_VERSION` | `"1.7.0"` |
| `DEFAULT_SOCKET_PATH` | `"/run/fizzcontainerd/fizzcontainerd.sock"` |
| `DEFAULT_STATE_DIR` | `"/var/lib/fizzcontainerd"` |
| `DEFAULT_SHIM_DIR` | `"/run/fizzcontainerd/shims"` |
| `DEFAULT_CONTENT_DIR` | `"/var/lib/fizzcontainerd/content"` |
| `DEFAULT_GC_INTERVAL` | `300.0` |
| `DEFAULT_GC_POLICY` | `"conservative"` |
| `DEFAULT_MAX_CONTAINERS` | `512` |
| `DEFAULT_MAX_CONTENT_BLOBS` | `8192` |
| `DEFAULT_MAX_IMAGES` | `256` |
| `DEFAULT_SHIM_HEARTBEAT_INTERVAL` | `10.0` |
| `DEFAULT_LOG_RING_BUFFER_SIZE` | `10000` |
| `DEFAULT_CRI_TIMEOUT` | `30.0` |
| `MAX_EXEC_PROCESSES` | `64` |
| `CHECKPOINT_VERSION` | `1` |

### Enums

| Enum | Values |
|------|--------|
| `ContainerStatus` | CREATED, READY, UPDATING, DELETING, DELETED |
| `TaskStatus` | CREATED, RUNNING, PAUSED, STOPPED, UNKNOWN |
| `ShimStatus` | STARTING, RUNNING, STOPPING, STOPPED, CRASHED |
| `ContentType` | LAYER, MANIFEST, CONFIG, INDEX |
| `GCPolicy` | AGGRESSIVE, CONSERVATIVE, MANUAL |
| `CRIAction` | RUN_POD_SANDBOX, STOP_POD_SANDBOX, REMOVE_POD_SANDBOX, POD_SANDBOX_STATUS, LIST_POD_SANDBOXES, CREATE_CONTAINER, START_CONTAINER, STOP_CONTAINER, REMOVE_CONTAINER, LIST_CONTAINERS, CONTAINER_STATUS |
| `LogStream` | STDOUT, STDERR, SYSTEM |

### Dataclasses

`ContentDescriptor`, `ContainerSpec`, `ContainerMetadata`, `TaskInfo`, `ShimInfo`, `LogEntry`, `GCResult`, `CRIRequest`, `CRIResponse`, `ContainerdStats`

### `ContentStore`

- `ingest(ref: str, content_type: ContentType = ContentType.LAYER) -> _IngestWriter`
- `commit(ref: str, expected_digest: Optional[str] = None) -> ContentDescriptor`
- `get(digest: str) -> ContentDescriptor`
- `exists(digest: str) -> bool`
- `delete(digest: str) -> None`
- `add_label(digest: str, key: str, value: str) -> None`
- `remove_label(digest: str, key: str) -> None`
- `increment_ref(digest: str) -> int`
- `decrement_ref(digest: str) -> int`
- `get_unreferenced() -> List[str]`
- Props: `blob_count`, `total_bytes`, `total_ingested`

### `MetadataStore`

- `create(spec: ContainerSpec) -> ContainerMetadata`
- `get(container_id: str) -> ContainerMetadata`
- `update(container_id: str, labels: Dict[str, str]) -> ContainerMetadata`
- `delete(container_id: str) -> ContainerMetadata`
- `list(filters: ...) -> List[ContainerMetadata]`
- `exists(container_id: str) -> bool`
- Props: `container_count`, `total_created`, `total_deleted`

### `ImageService`

- `pull(reference: str, ...) -> _ImageRecord`
- `get(reference: str) -> _ImageRecord`
- `remove(reference: str) -> _ImageRecord`
- `list_images() -> List[_ImageRecord]`
- `exists(reference: str) -> bool`
- Props: `image_count`, `total_pulled`, `total_removed`

### `TaskService`

- `create(container_id: str) -> TaskInfo`
- `start(container_id: str) -> TaskInfo`
- `kill(container_id: str, signal: int = 15) -> TaskInfo`
- `delete(container_id: str) -> TaskInfo`
- `pause(container_id: str) -> TaskInfo`
- `resume(container_id: str) -> TaskInfo`
- `exec(container_id: str, args: List[str], ...) -> str`
- `remove_exec(container_id: str, exec_id: str) -> None`
- `checkpoint(container_id: str, path: str = "") -> str`
- `restore(container_id: str, checkpoint_path: str = "") -> TaskInfo`
- `get(container_id: str) -> TaskInfo`
- `exists(container_id: str) -> bool`
- Props: `task_count`, `running_count`, `paused_count`, `total_created`

### `Shim`

- Props: `info`, `shim_id`, `container_id`, `status`, `connected`, `exit_code`
- `heartbeat() -> None`
- `collect_exit_code(code: int) -> None`
- `hold_namespace(namespace_id: str) -> None`
- `release_namespaces() -> List[str]`
- `connect() -> None`
- `disconnect() -> None`
- `terminate() -> None`
- `crash() -> None`
- `recover() -> None`
- `is_healthy(timeout: float = ...) -> bool`

### `ShimManager`

- `spawn(container_id: str) -> ShimInfo`
- `terminate(shim_id: str) -> None`
- `get(shim_id: str) -> Shim`
- `get_by_container(container_id: str) -> Shim`
- `reconnect(shim_id: str) -> None`
- `health_check() -> Dict[str, bool]`
- `recover_crashed() -> int`
- Props: `shim_count`, `active_count`, `total_spawned`

### `EventService`

- `publish(topic: str, payload: Dict[str, Any]) -> int`
- `subscribe(topic: str, callback: Callable) -> str`
- `unsubscribe(topic: str, callback: Callable) -> None`
- `get_topics() -> List[str]`
- Props: `event_count`, `sequence`

### `ContainerLog`

- `write(container_id: str, stream: LogStream, message: str) -> None`
- `read(container_id: str, ...) -> List[LogEntry]`
- `clear(container_id: str) -> int`
- `container_ids() -> List[str]`
- `export(container_id: str) -> str`
- Props: `total_entries`, `container_count`

### `GarbageCollector`

- `collect() -> GCResult`
- `get_last_result() -> Optional[GCResult]`
- `get_history(limit: int = 10) -> List[GCResult]`
- Props: `gc_policy` (r/w), `total_passes`, `total_bytes_reclaimed`

### `CRIService`

- `handle(request: CRIRequest) -> CRIResponse`
- Props: `sandbox_count`, `total_requests`, `total_errors`

### `ContainerdDaemon`

Main daemon class orchestrating all services.

**Constructor**:
```python
def __init__(
    self,
    socket_path: str = DEFAULT_SOCKET_PATH,
    state_dir: str = DEFAULT_STATE_DIR,
    shim_dir: str = DEFAULT_SHIM_DIR,
    content_dir: str = DEFAULT_CONTENT_DIR,
    gc_interval: float = DEFAULT_GC_INTERVAL,
    gc_policy: str = DEFAULT_GC_POLICY,
    max_containers: int = DEFAULT_MAX_CONTAINERS,
    max_content_blobs: int = DEFAULT_MAX_CONTENT_BLOBS,
    max_images: int = DEFAULT_MAX_IMAGES,
    shim_heartbeat: float = DEFAULT_SHIM_HEARTBEAT_INTERVAL,
    log_buffer_size: int = DEFAULT_LOG_RING_BUFFER_SIZE,
    cri_timeout: float = DEFAULT_CRI_TIMEOUT,
    event_bus: Optional[Any] = None,
) -> None
```

**Public attributes (services)**:
`content_store`, `metadata_store`, `image_service`, `shim_manager`, `task_service`, `event_service`, `container_log`, `garbage_collector`, `cri_service`

**Methods**:
- `start() -> None`
- `stop() -> None`
- `create_container(container_id: str, image: str = "", labels: Optional[Dict] = None, args: Optional[List] = None, env: Optional[List] = None) -> ContainerMetadata`
- `delete_container(container_id: str) -> ContainerMetadata`
- `run_container(container_id: str, image: str = "", labels: Optional[Dict] = None, args: Optional[List] = None) -> TaskInfo`
- `get_stats() -> ContainerdStats`
- Props: `running -> bool`, `uptime -> float`, `version -> str`

### `ContainerdDashboard`, `FizzContainerdMiddleware(IMiddleware)`

Priority 112
- `render_dashboard()`, `render_containers()`, `render_tasks()`, `render_shims()`, `render_images()`, `render_gc()`, `render_stats()`

### Factory Function

```python
def create_fizzcontainerd_subsystem(
    socket_path: str = DEFAULT_SOCKET_PATH,
    state_dir: str = DEFAULT_STATE_DIR,
    gc_interval: float = DEFAULT_GC_INTERVAL,
    gc_policy: str = DEFAULT_GC_POLICY,
    max_containers: int = DEFAULT_MAX_CONTAINERS,
    max_content_blobs: int = DEFAULT_MAX_CONTENT_BLOBS,
    max_images: int = DEFAULT_MAX_IMAGES,
    log_buffer_size: int = DEFAULT_LOG_RING_BUFFER_SIZE,
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
    enable_dashboard: bool = False,
    event_bus: Optional[Any] = None,
) -> tuple[ContainerdDaemon, FizzContainerdMiddleware]
```

---

## `__main__.py` Wiring Pattern (FizzContainerd as Template)

All Round 16 modules follow the same wiring pattern in `__main__.py`. FizzContainerd is the most recent and serves as the canonical template for Round 17.

### 1. Imports (line ~521)

```python
from enterprise_fizzbuzz.infrastructure.fizzcontainerd import (
    ContainerdDaemon,
    ContainerdDashboard,
    FizzContainerdMiddleware,
    create_fizzcontainerd_subsystem,
)
```

### 2. CLI Arguments (line ~3756)

```python
# FizzContainerd — High-Level Container Daemon
parser.add_argument(
    "--containerd",
    action="store_true",
    help="Enable FizzContainerd: containerd-style daemon with content store, metadata, shims, CRI, and garbage collection",
)
parser.add_argument("--containerd-containers", action="store_true", ...)
parser.add_argument("--containerd-tasks", action="store_true", ...)
parser.add_argument("--containerd-shims", action="store_true", ...)
parser.add_argument("--containerd-images", action="store_true", ...)
parser.add_argument("--containerd-gc", action="store_true", ...)
```

Pattern: one `--<feature>` flag to enable the subsystem, then `--<feature>-<view>` flags for each dashboard view.

### 3. Initialization Block (line ~8184)

```python
# FizzContainerd — High-Level Container Daemon
containerd_daemon_instance = None
containerd_middleware_instance = None

if args.containerd or args.containerd_containers or args.containerd_tasks or args.containerd_shims or args.containerd_images or args.containerd_gc:
    containerd_daemon_instance, containerd_middleware_instance = create_fizzcontainerd_subsystem(
        socket_path=config.fizzcontainerd_socket_path,
        state_dir=config.fizzcontainerd_state_dir,
        gc_interval=config.fizzcontainerd_gc_interval,
        gc_policy=config.fizzcontainerd_gc_policy,
        max_containers=config.fizzcontainerd_max_containers,
        max_content_blobs=config.fizzcontainerd_max_content_blobs,
        max_images=config.fizzcontainerd_max_images,
        log_buffer_size=config.fizzcontainerd_log_buffer_size,
        dashboard_width=config.fizzcontainerd_dashboard_width,
        enable_dashboard=args.containerd_containers,
    )

    builder.with_middleware(containerd_middleware_instance)
```

Pattern: guard with OR of all flags, call factory, wire middleware into builder.

### 4. Banner Block (line ~8208)

```python
print(
    "  | FIZZCONTAINERD: HIGH-LEVEL CONTAINER DAEMON             |\n"
    f"  | Socket: {config.fizzcontainerd_socket_path:<47}|\n"
    f"  | Max Containers: {config.fizzcontainerd_max_containers:<8} GC Policy: {config.fizzcontainerd_gc_policy:<14}|\n"
    "  | containerd v1.7 architecture                            |\n"
)
```

### 5. Dashboard Rendering Block (line ~11717)

```python
# FizzContainerd Containers (post-execution)
if args.containerd_containers and containerd_middleware_instance is not None:
    print()
    print(containerd_middleware_instance.render_containers())
elif args.containerd_containers and containerd_middleware_instance is None:
    print("\n  FizzContainerd not enabled. Use --containerd to enable.\n")

# FizzContainerd Tasks (post-execution)
if args.containerd_tasks and containerd_middleware_instance is not None:
    print()
    print(containerd_middleware_instance.render_tasks())
elif args.containerd_tasks and containerd_middleware_instance is None:
    print("\n  FizzContainerd not enabled. Use --containerd to enable.\n")

# ... same pattern for --containerd-shims, --containerd-images, --containerd-gc
```

Pattern: for each `--<feature>-<view>` flag, guard with `is not None`, call `middleware.render_<view>()`, else print fallback message.

---

## Cross-Module Summary

### Middleware Priority Order

| Priority | Module | Middleware Class |
|----------|--------|-----------------|
| 106 | FizzNS | `FizzNSMiddleware` |
| 107 | FizzCgroup | `FizzCgroupMiddleware` |
| 108 | FizzOCI | `OCIRuntimeMiddleware` |
| 109 | FizzOverlay | `FizzOverlayMiddleware` |
| 110 | FizzRegistry | `FizzRegistryMiddleware` |
| 111 | FizzCNI | `FizzCNIMiddleware` |
| 112 | FizzContainerd | `FizzContainerdMiddleware` |

### Common Patterns

1. **Singleton metaclass**: Manager/Store classes (NamespaceManager, CgroupManager, LayerStore, BlobStore, OCIRuntime) use `_XxxMeta(type)` metaclasses.
2. **Factory function**: Every module exports `create_fizz<name>_subsystem(...)` returning `tuple[MainClass, Middleware]`.
3. **Dashboard class**: Every module has a `XxxDashboard` class with `render()` and view-specific `render_xxx()` methods.
4. **Middleware interface**: All implement `IMiddleware` with `get_name()`, `get_priority()`, and `process()`. Each adds `render_xxx()` convenience methods.
5. **Event bus integration**: All accept optional `event_bus` parameter for lifecycle event publishing.
6. **Config integration**: Factory parameters map to `config.fizz<name>_<param>` attributes read from ConfigurationManager.
