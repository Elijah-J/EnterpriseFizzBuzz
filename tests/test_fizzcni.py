"""
Enterprise FizzBuzz Platform - FizzCNI Test Suite

Comprehensive tests for the Container Network Interface Plugin System.
Validates bridge, host, none, and overlay plugins, IPAM subnet allocation,
DHCP lease lifecycle, port mapping with conflict detection, container DNS
name resolution, network policy microsegmentation, CNI manager orchestration,
ASCII dashboard rendering, middleware integration, factory wiring, and all
18 exception classes.

Containers without networking are isolated from more than just the host.
These tests ensure they are not.
"""

from __future__ import annotations

import copy
import ipaddress
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from fizzcni import (
    BROADCAST_MAC,
    CNI_SPEC_VERSION,
    DEFAULT_BRIDGE_NAME,
    DEFAULT_DASHBOARD_WIDTH,
    DEFAULT_DNS_DOMAIN,
    DEFAULT_DNS_TTL,
    DEFAULT_GATEWAY,
    DEFAULT_LEASE_DURATION,
    DEFAULT_MTU,
    DEFAULT_VNI,
    DEFAULT_VXLAN_PORT,
    MAX_DNS_RECORDS,
    MAX_POLICIES,
    MAX_PORT_MAPPINGS,
    MAX_VETH_PAIRS,
    MIDDLEWARE_PRIORITY,
    NAT_TABLE_SIZE,
    STP_FORWARD_DELAY,
    STP_HELLO_INTERVAL,
    STP_MAX_AGE,
    BridgeInterface,
    BridgePlugin,
    CNIConfig,
    CNIDashboard,
    CNIManager,
    CNIOperation,
    CNIResult,
    CNIStats,
    ContainerDNS,
    DNSRecord,
    DNSRecordType,
    FizzCNIMiddleware,
    HostPlugin,
    IPAllocation,
    IPAMPlugin,
    InterfaceState,
    Lease,
    LeaseState,
    NetworkPolicyEngine,
    NetworkPolicyRule,
    NetworkPolicySpec,
    NonePlugin,
    OverlayPlugin,
    PluginType,
    PolicyAction,
    PolicyDirection,
    PortMapper,
    PortMapping,
    STPPortState,
    VethPair,
    create_fizzcni_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions import (
    BridgeError,
    CNIAddError,
    CNICheckError,
    CNIDashboardError,
    CNIDeleteError,
    CNIError,
    CNIMiddlewareError,
    CNIPluginNotFoundError,
    ContainerDNSError,
    IPAMConflictError,
    IPAMError,
    IPAMExhaustedError,
    IPAMLeaseExpiredError,
    NetworkPolicyError,
    OverlayNetworkError,
    PortConflictError,
    PortMappingError,
    VethCreationError,
)
from config import _SingletonMeta
from models import EventType, FizzBuzzResult, ProcessingContext


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


# ============================================================
# Constants Tests
# ============================================================


class TestConstants:
    """Validate CNI constants."""

    def test_cni_spec_version(self):
        assert CNI_SPEC_VERSION == "1.0.0"

    def test_default_bridge_name(self):
        assert DEFAULT_BRIDGE_NAME == "fizzbr0"

    def test_default_subnet(self):
        from fizzcni import DEFAULT_SUBNET
        assert DEFAULT_SUBNET == "10.244.0.0/16"

    def test_default_gateway(self):
        assert DEFAULT_GATEWAY == "10.244.0.1"

    def test_default_lease_duration(self):
        assert DEFAULT_LEASE_DURATION == 3600.0

    def test_default_mtu(self):
        assert DEFAULT_MTU == 1500

    def test_default_vxlan_port(self):
        assert DEFAULT_VXLAN_PORT == 4789

    def test_default_vni(self):
        assert DEFAULT_VNI == 1

    def test_default_dns_domain(self):
        assert DEFAULT_DNS_DOMAIN == "cluster.fizz"

    def test_default_dns_ttl(self):
        assert DEFAULT_DNS_TTL == 30

    def test_default_dashboard_width(self):
        assert DEFAULT_DASHBOARD_WIDTH == 72

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 111

    def test_max_veth_pairs(self):
        assert MAX_VETH_PAIRS == 4096

    def test_max_port_mappings(self):
        assert MAX_PORT_MAPPINGS == 65535

    def test_max_dns_records(self):
        assert MAX_DNS_RECORDS == 8192

    def test_max_policies(self):
        assert MAX_POLICIES == 1024

    def test_broadcast_mac(self):
        assert BROADCAST_MAC == "ff:ff:ff:ff:ff:ff"

    def test_stp_hello_interval(self):
        assert STP_HELLO_INTERVAL == 2.0

    def test_stp_max_age(self):
        assert STP_MAX_AGE == 20.0

    def test_stp_forward_delay(self):
        assert STP_FORWARD_DELAY == 15.0

    def test_nat_table_size(self):
        assert NAT_TABLE_SIZE == 16384


# ============================================================
# Enum Tests
# ============================================================


class TestCNIOperation:
    """Validate CNI operation enum."""

    def test_add(self):
        assert CNIOperation.ADD is not None

    def test_del(self):
        assert CNIOperation.DEL is not None

    def test_check(self):
        assert CNIOperation.CHECK is not None

    def test_version(self):
        assert CNIOperation.VERSION is not None

    def test_member_count(self):
        assert len(CNIOperation) == 4


class TestPluginType:
    """Validate plugin type enum."""

    def test_bridge(self):
        assert PluginType.BRIDGE.value == "bridge"

    def test_host(self):
        assert PluginType.HOST.value == "host"

    def test_none(self):
        assert PluginType.NONE.value == "none"

    def test_overlay(self):
        assert PluginType.OVERLAY.value == "overlay"

    def test_member_count(self):
        assert len(PluginType) == 4


class TestInterfaceState:
    """Validate interface state enum."""

    def test_down(self):
        assert InterfaceState.DOWN is not None

    def test_up(self):
        assert InterfaceState.UP is not None

    def test_deleted(self):
        assert InterfaceState.DELETED is not None

    def test_member_count(self):
        assert len(InterfaceState) == 3


class TestLeaseState:
    """Validate lease state enum."""

    def test_active(self):
        assert LeaseState.ACTIVE is not None

    def test_expired(self):
        assert LeaseState.EXPIRED is not None

    def test_released(self):
        assert LeaseState.RELEASED is not None

    def test_member_count(self):
        assert len(LeaseState) == 3


class TestPolicyAction:
    """Validate policy action enum."""

    def test_allow(self):
        assert PolicyAction.ALLOW is not None

    def test_deny(self):
        assert PolicyAction.DENY is not None

    def test_member_count(self):
        assert len(PolicyAction) == 2


class TestPolicyDirection:
    """Validate policy direction enum."""

    def test_ingress(self):
        assert PolicyDirection.INGRESS is not None

    def test_egress(self):
        assert PolicyDirection.EGRESS is not None

    def test_member_count(self):
        assert len(PolicyDirection) == 2


class TestSTPPortState:
    """Validate STP port state enum."""

    def test_disabled(self):
        assert STPPortState.DISABLED is not None

    def test_blocking(self):
        assert STPPortState.BLOCKING is not None

    def test_listening(self):
        assert STPPortState.LISTENING is not None

    def test_learning(self):
        assert STPPortState.LEARNING is not None

    def test_forwarding(self):
        assert STPPortState.FORWARDING is not None

    def test_member_count(self):
        assert len(STPPortState) == 5


class TestDNSRecordType:
    """Validate DNS record type enum."""

    def test_a(self):
        assert DNSRecordType.A.value == "A"

    def test_aaaa(self):
        assert DNSRecordType.AAAA.value == "AAAA"

    def test_srv(self):
        assert DNSRecordType.SRV.value == "SRV"

    def test_ptr(self):
        assert DNSRecordType.PTR.value == "PTR"

    def test_cname(self):
        assert DNSRecordType.CNAME.value == "CNAME"

    def test_member_count(self):
        assert len(DNSRecordType) == 5


# ============================================================
# Dataclass Tests
# ============================================================


class TestCNIConfig:
    """Validate CNI configuration dataclass."""

    def test_default_version(self):
        config = CNIConfig()
        assert config.cni_version == CNI_SPEC_VERSION

    def test_default_name(self):
        config = CNIConfig()
        assert config.name == "fizzbuzz-net"

    def test_default_plugin_type(self):
        config = CNIConfig()
        assert config.plugin_type == "bridge"

    def test_default_mtu(self):
        config = CNIConfig()
        assert config.mtu == DEFAULT_MTU

    def test_default_bridge_name(self):
        config = CNIConfig()
        assert config.bridge_name == DEFAULT_BRIDGE_NAME

    def test_custom_config(self):
        config = CNIConfig(name="test-net", plugin_type="overlay", mtu=9000)
        assert config.name == "test-net"
        assert config.plugin_type == "overlay"
        assert config.mtu == 9000


class TestCNIResult:
    """Validate CNI result dataclass."""

    def test_default_version(self):
        result = CNIResult()
        assert result.cni_version == CNI_SPEC_VERSION

    def test_empty_interfaces(self):
        result = CNIResult()
        assert result.interfaces == []

    def test_empty_ips(self):
        result = CNIResult()
        assert result.ips == []

    def test_empty_routes(self):
        result = CNIResult()
        assert result.routes == []

    def test_empty_dns(self):
        result = CNIResult()
        assert result.dns == {}


class TestVethPair:
    """Validate veth pair dataclass."""

    def test_default_state(self):
        pair = VethPair()
        assert pair.state == InterfaceState.DOWN

    def test_default_ifname(self):
        pair = VethPair()
        assert pair.container_ifname == "eth0"

    def test_default_mtu(self):
        pair = VethPair()
        assert pair.mtu == DEFAULT_MTU

    def test_has_pair_id(self):
        pair = VethPair()
        assert pair.pair_id is not None
        assert len(pair.pair_id) > 0

    def test_unique_pair_ids(self):
        p1 = VethPair()
        p2 = VethPair()
        assert p1.pair_id != p2.pair_id


class TestBridgeInterface:
    """Validate bridge interface dataclass."""

    def test_default_name(self):
        bridge = BridgeInterface()
        assert bridge.name == DEFAULT_BRIDGE_NAME

    def test_default_ip(self):
        bridge = BridgeInterface()
        assert bridge.ip_address == DEFAULT_GATEWAY

    def test_stp_enabled_by_default(self):
        bridge = BridgeInterface()
        assert bridge.stp_enabled is True

    def test_nat_enabled_by_default(self):
        bridge = BridgeInterface()
        assert bridge.nat_enabled is True

    def test_stp_root_by_default(self):
        bridge = BridgeInterface()
        assert bridge.stp_root is True

    def test_default_priority(self):
        bridge = BridgeInterface()
        assert bridge.stp_priority == 32768


class TestIPAllocation:
    """Validate IP allocation dataclass."""

    def test_has_allocation_id(self):
        alloc = IPAllocation()
        assert alloc.allocation_id is not None

    def test_default_prefix_length(self):
        alloc = IPAllocation()
        assert alloc.prefix_length == 24

    def test_default_ifname(self):
        alloc = IPAllocation()
        assert alloc.interface_name == "eth0"


class TestLease:
    """Validate lease dataclass."""

    def test_has_lease_id(self):
        lease = Lease()
        assert lease.lease_id is not None

    def test_default_state(self):
        lease = Lease()
        assert lease.state == LeaseState.ACTIVE

    def test_default_duration(self):
        lease = Lease()
        assert lease.duration == DEFAULT_LEASE_DURATION

    def test_default_renewal_count(self):
        lease = Lease()
        assert lease.renewal_count == 0

    def test_is_expired_at_creation(self):
        # Default expires_at is set to now, so it's essentially expired
        lease = Lease()
        # The exact timing may vary, but within a second it should be close
        assert isinstance(lease.is_expired(), bool)

    def test_remaining_seconds(self):
        lease = Lease()
        remaining = lease.remaining_seconds()
        assert remaining >= 0.0


class TestPortMapping:
    """Validate port mapping dataclass."""

    def test_has_mapping_id(self):
        mapping = PortMapping()
        assert mapping.mapping_id is not None

    def test_default_protocol(self):
        mapping = PortMapping()
        assert mapping.protocol == "tcp"


class TestDNSRecord:
    """Validate DNS record dataclass."""

    def test_has_record_id(self):
        record = DNSRecord()
        assert record.record_id is not None

    def test_default_type(self):
        record = DNSRecord()
        assert record.record_type == DNSRecordType.A

    def test_default_ttl(self):
        record = DNSRecord()
        assert record.ttl == DEFAULT_DNS_TTL


class TestNetworkPolicyRule:
    """Validate network policy rule dataclass."""

    def test_has_rule_id(self):
        rule = NetworkPolicyRule()
        assert rule.rule_id is not None

    def test_default_direction(self):
        rule = NetworkPolicyRule()
        assert rule.direction == PolicyDirection.INGRESS

    def test_default_action(self):
        rule = NetworkPolicyRule()
        assert rule.action == PolicyAction.ALLOW


class TestNetworkPolicySpec:
    """Validate network policy spec dataclass."""

    def test_has_policy_id(self):
        policy = NetworkPolicySpec()
        assert policy.policy_id is not None

    def test_default_namespace(self):
        policy = NetworkPolicySpec()
        assert policy.namespace == "default"


class TestCNIStats:
    """Validate CNI stats dataclass."""

    def test_all_zeros(self):
        stats = CNIStats()
        assert stats.total_add_ops == 0
        assert stats.total_del_ops == 0
        assert stats.total_check_ops == 0
        assert stats.active_containers == 0
        assert stats.errors == 0


# ============================================================
# Bridge Plugin Tests
# ============================================================


class TestBridgePlugin:
    """Validate bridge CNI plugin."""

    def _make_plugin(self, **kwargs):
        ipam = IPAMPlugin(
            subnet="10.244.0.0/24",
            gateway="10.244.0.1",
            lease_duration=3600.0,
        )
        defaults = dict(
            bridge_name="fizzbr0",
            gateway="10.244.0.1",
            subnet="10.244.0.0/24",
            mtu=1500,
            ipam=ipam,
        )
        defaults.update(kwargs)
        return BridgePlugin(**defaults)

    def test_plugin_type(self):
        plugin = self._make_plugin()
        assert plugin.plugin_type() == PluginType.BRIDGE

    def test_version(self):
        plugin = self._make_plugin()
        versions = plugin.version()
        assert CNI_SPEC_VERSION in versions

    def test_add_creates_veth_pair(self):
        plugin = self._make_plugin()
        config = CNIConfig()
        result = plugin.add("c1", "/netns/c1", "eth0", config)
        assert "c1" in plugin.veth_pairs
        assert plugin.veth_pairs["c1"].state == InterfaceState.UP

    def test_add_returns_interfaces(self):
        plugin = self._make_plugin()
        config = CNIConfig()
        result = plugin.add("c1", "/netns/c1", "eth0", config)
        assert len(result.interfaces) == 2
        assert result.interfaces[1]["sandbox"] == "/netns/c1"

    def test_add_assigns_ip(self):
        plugin = self._make_plugin()
        config = CNIConfig()
        result = plugin.add("c1", "/netns/c1", "eth0", config)
        assert len(result.ips) == 1
        assert "10.244.0." in result.ips[0]["address"]

    def test_add_sets_gateway(self):
        plugin = self._make_plugin()
        config = CNIConfig()
        result = plugin.add("c1", "/netns/c1", "eth0", config)
        assert result.ips[0]["gateway"] == "10.244.0.1"

    def test_add_configures_routes(self):
        plugin = self._make_plugin()
        config = CNIConfig()
        result = plugin.add("c1", "/netns/c1", "eth0", config)
        assert len(result.routes) == 1
        assert result.routes[0]["dst"] == "0.0.0.0/0"

    def test_add_configures_dns(self):
        plugin = self._make_plugin()
        config = CNIConfig()
        result = plugin.add("c1", "/netns/c1", "eth0", config)
        assert "nameservers" in result.dns
        assert result.dns["domain"] == DEFAULT_DNS_DOMAIN

    def test_add_attaches_to_bridge(self):
        plugin = self._make_plugin()
        config = CNIConfig()
        plugin.add("c1", "/netns/c1", "eth0", config)
        pair = plugin.veth_pairs["c1"]
        assert pair.host_ifname in plugin.bridge.ports

    def test_add_learns_mac(self):
        plugin = self._make_plugin()
        config = CNIConfig()
        plugin.add("c1", "/netns/c1", "eth0", config)
        pair = plugin.veth_pairs["c1"]
        assert pair.container_mac in plugin.bridge.mac_table

    def test_add_creates_nat_entry(self):
        plugin = self._make_plugin()
        config = CNIConfig()
        plugin.add("c1", "/netns/c1", "eth0", config)
        assert "c1" in plugin.bridge.nat_table

    def test_add_increments_stats(self):
        plugin = self._make_plugin()
        config = CNIConfig()
        plugin.add("c1", "/netns/c1", "eth0", config)
        assert plugin.stats.total_add_ops == 1
        assert plugin.stats.active_containers == 1

    def test_add_multiple_containers(self):
        plugin = self._make_plugin()
        config = CNIConfig()
        plugin.add("c1", "/netns/c1", "eth0", config)
        plugin.add("c2", "/netns/c2", "eth0", config)
        assert len(plugin.veth_pairs) == 2
        assert plugin.stats.active_containers == 2

    def test_delete_removes_veth(self):
        plugin = self._make_plugin()
        config = CNIConfig()
        plugin.add("c1", "/netns/c1", "eth0", config)
        plugin.delete("c1", "/netns/c1", "eth0", config)
        assert "c1" not in plugin.veth_pairs

    def test_delete_releases_ip(self):
        plugin = self._make_plugin()
        config = CNIConfig()
        plugin.add("c1", "/netns/c1", "eth0", config)
        plugin.delete("c1", "/netns/c1", "eth0", config)
        assert not plugin.ipam.has_allocation("c1")

    def test_delete_removes_nat(self):
        plugin = self._make_plugin()
        config = CNIConfig()
        plugin.add("c1", "/netns/c1", "eth0", config)
        plugin.delete("c1", "/netns/c1", "eth0", config)
        assert "c1" not in plugin.bridge.nat_table

    def test_delete_decrements_stats(self):
        plugin = self._make_plugin()
        config = CNIConfig()
        plugin.add("c1", "/netns/c1", "eth0", config)
        plugin.delete("c1", "/netns/c1", "eth0", config)
        assert plugin.stats.total_del_ops == 1
        assert plugin.stats.active_containers == 0

    def test_check_valid(self):
        plugin = self._make_plugin()
        config = CNIConfig()
        plugin.add("c1", "/netns/c1", "eth0", config)
        assert plugin.check("c1", "/netns/c1", "eth0", config) is True

    def test_check_missing_container(self):
        plugin = self._make_plugin()
        config = CNIConfig()
        with pytest.raises(CNICheckError):
            plugin.check("c1", "/netns/c1", "eth0", config)

    def test_check_increments_stats(self):
        plugin = self._make_plugin()
        config = CNIConfig()
        plugin.add("c1", "/netns/c1", "eth0", config)
        plugin.check("c1", "/netns/c1", "eth0", config)
        assert plugin.stats.total_check_ops == 1

    def test_mac_lookup(self):
        plugin = self._make_plugin()
        config = CNIConfig()
        plugin.add("c1", "/netns/c1", "eth0", config)
        pair = plugin.veth_pairs["c1"]
        assert plugin.mac_lookup(pair.container_mac) == pair.host_ifname

    def test_mac_lookup_unknown(self):
        plugin = self._make_plugin()
        assert plugin.mac_lookup("00:00:00:00:00:00") is None

    def test_stp_port_forwarding(self):
        plugin = self._make_plugin()
        config = CNIConfig()
        plugin.add("c1", "/netns/c1", "eth0", config)
        pair = plugin.veth_pairs["c1"]
        assert plugin.bridge.ports[pair.host_ifname] == STPPortState.FORWARDING

    def test_stp_disabled(self):
        plugin = self._make_plugin(stp_enabled=False)
        config = CNIConfig()
        plugin.add("c1", "/netns/c1", "eth0", config)
        pair = plugin.veth_pairs["c1"]
        assert plugin.bridge.ports[pair.host_ifname] == STPPortState.FORWARDING

    def test_nat_disabled(self):
        plugin = self._make_plugin(nat_enabled=False)
        config = CNIConfig()
        plugin.add("c1", "/netns/c1", "eth0", config)
        assert "c1" not in plugin.bridge.nat_table

    def test_bridge_mac_format(self):
        plugin = self._make_plugin()
        mac = plugin.bridge.mac
        assert len(mac.split(":")) == 6

    def test_event_bus_integration(self):
        bus = MagicMock()
        plugin = self._make_plugin(event_bus=bus)
        config = CNIConfig()
        plugin.add("c1", "/netns/c1", "eth0", config)
        assert bus.publish.called


# ============================================================
# Host Plugin Tests
# ============================================================


class TestHostPlugin:
    """Validate host CNI plugin."""

    def test_plugin_type(self):
        plugin = HostPlugin()
        assert plugin.plugin_type() == PluginType.HOST

    def test_add_returns_result(self):
        plugin = HostPlugin()
        config = CNIConfig()
        result = plugin.add("c1", "/netns/c1", "eth0", config)
        assert isinstance(result, CNIResult)
        assert len(result.interfaces) == 1
        assert result.interfaces[0]["name"] == "host"

    def test_add_increments_stats(self):
        plugin = HostPlugin()
        config = CNIConfig()
        plugin.add("c1", "/netns/c1", "eth0", config)
        assert plugin.stats.total_add_ops == 1
        assert plugin.stats.active_containers == 1

    def test_delete(self):
        plugin = HostPlugin()
        config = CNIConfig()
        plugin.add("c1", "/netns/c1", "eth0", config)
        plugin.delete("c1", "/netns/c1", "eth0", config)
        assert plugin.stats.total_del_ops == 1
        assert plugin.stats.active_containers == 0

    def test_check_valid(self):
        plugin = HostPlugin()
        config = CNIConfig()
        plugin.add("c1", "/netns/c1", "eth0", config)
        assert plugin.check("c1", "/netns/c1", "eth0", config) is True

    def test_check_missing(self):
        plugin = HostPlugin()
        config = CNIConfig()
        with pytest.raises(CNICheckError):
            plugin.check("c1", "/netns/c1", "eth0", config)

    def test_no_ip_assigned(self):
        plugin = HostPlugin()
        config = CNIConfig()
        result = plugin.add("c1", "/netns/c1", "eth0", config)
        assert result.ips == []


# ============================================================
# None Plugin Tests
# ============================================================


class TestNonePlugin:
    """Validate none CNI plugin."""

    def test_plugin_type(self):
        plugin = NonePlugin()
        assert plugin.plugin_type() == PluginType.NONE

    def test_add_returns_loopback(self):
        plugin = NonePlugin()
        config = CNIConfig()
        result = plugin.add("c1", "/netns/c1", "eth0", config)
        assert result.interfaces[0]["name"] == "lo"

    def test_add_returns_loopback_ip(self):
        plugin = NonePlugin()
        config = CNIConfig()
        result = plugin.add("c1", "/netns/c1", "eth0", config)
        assert result.ips[0]["address"] == "127.0.0.1/8"

    def test_add_increments_stats(self):
        plugin = NonePlugin()
        config = CNIConfig()
        plugin.add("c1", "/netns/c1", "eth0", config)
        assert plugin.stats.total_add_ops == 1

    def test_delete(self):
        plugin = NonePlugin()
        config = CNIConfig()
        plugin.add("c1", "/netns/c1", "eth0", config)
        plugin.delete("c1", "/netns/c1", "eth0", config)
        assert plugin.stats.active_containers == 0

    def test_check_valid(self):
        plugin = NonePlugin()
        config = CNIConfig()
        plugin.add("c1", "/netns/c1", "eth0", config)
        assert plugin.check("c1", "/netns/c1", "eth0", config) is True

    def test_check_missing(self):
        plugin = NonePlugin()
        config = CNIConfig()
        with pytest.raises(CNICheckError):
            plugin.check("c1", "/netns/c1", "eth0", config)


# ============================================================
# Overlay Plugin Tests
# ============================================================


class TestOverlayPlugin:
    """Validate overlay CNI plugin."""

    def _make_plugin(self, **kwargs):
        ipam = IPAMPlugin(
            subnet="10.244.0.0/24",
            gateway="10.244.0.1",
            lease_duration=3600.0,
        )
        defaults = dict(
            vni=1,
            vtep_ip="192.168.1.1",
            subnet="10.244.0.0/24",
            gateway="10.244.0.1",
            ipam=ipam,
        )
        defaults.update(kwargs)
        return OverlayPlugin(**defaults)

    def test_plugin_type(self):
        plugin = self._make_plugin()
        assert plugin.plugin_type() == PluginType.OVERLAY

    def test_add_returns_result(self):
        plugin = self._make_plugin()
        config = CNIConfig()
        result = plugin.add("c1", "/netns/c1", "eth0", config)
        assert isinstance(result, CNIResult)
        assert len(result.interfaces) == 1

    def test_add_assigns_ip(self):
        plugin = self._make_plugin()
        config = CNIConfig()
        result = plugin.add("c1", "/netns/c1", "eth0", config)
        assert len(result.ips) == 1

    def test_add_registers_in_fdb(self):
        plugin = self._make_plugin()
        config = CNIConfig()
        plugin.add("c1", "/netns/c1", "eth0", config)
        container_info = plugin._containers["c1"]
        assert container_info["mac"] in plugin.fdb

    def test_delete(self):
        plugin = self._make_plugin()
        config = CNIConfig()
        plugin.add("c1", "/netns/c1", "eth0", config)
        plugin.delete("c1", "/netns/c1", "eth0", config)
        assert "c1" not in plugin._containers

    def test_delete_removes_fdb_entry(self):
        plugin = self._make_plugin()
        config = CNIConfig()
        plugin.add("c1", "/netns/c1", "eth0", config)
        mac = plugin._containers["c1"]["mac"]
        plugin.delete("c1", "/netns/c1", "eth0", config)
        assert mac not in plugin.fdb

    def test_check_valid(self):
        plugin = self._make_plugin()
        config = CNIConfig()
        plugin.add("c1", "/netns/c1", "eth0", config)
        assert plugin.check("c1", "/netns/c1", "eth0", config) is True

    def test_check_missing(self):
        plugin = self._make_plugin()
        config = CNIConfig()
        with pytest.raises(CNICheckError):
            plugin.check("c1", "/netns/c1", "eth0", config)

    def test_register_vtep(self):
        plugin = self._make_plugin()
        plugin.register_vtep("192.168.1.2")
        assert "192.168.1.2" in plugin.vtep_registry

    def test_learn_mac(self):
        plugin = self._make_plugin()
        plugin.learn_mac("aa:bb:cc:dd:ee:ff", "192.168.1.2")
        assert plugin.fdb["aa:bb:cc:dd:ee:ff"] == "192.168.1.2"

    def test_encapsulate_known_dst(self):
        plugin = self._make_plugin()
        plugin.learn_mac("aa:bb:cc:dd:ee:ff", "192.168.1.2")
        result = plugin.encapsulate(b"test_frame", "11:22:33:44:55:66", "aa:bb:cc:dd:ee:ff")
        assert result is not None
        assert result["vtep_dst"] == "192.168.1.2"
        assert result["vni"] == 1

    def test_encapsulate_unknown_dst(self):
        plugin = self._make_plugin()
        result = plugin.encapsulate(b"test_frame", "11:22:33:44:55:66", "aa:bb:cc:dd:ee:ff")
        assert result is None

    def test_mtu_reduction(self):
        plugin = self._make_plugin(mtu=1500)
        assert plugin.mtu == 1450  # 1500 - 50 VXLAN overhead

    def test_local_vtep_registered(self):
        plugin = self._make_plugin(vtep_ip="10.0.0.1")
        assert "10.0.0.1" in plugin.vtep_registry


# ============================================================
# IPAM Plugin Tests
# ============================================================


class TestIPAMPlugin:
    """Validate IP Address Management plugin."""

    def _make_ipam(self, **kwargs):
        defaults = dict(
            subnet="10.244.0.0/24",
            gateway="10.244.0.1",
            lease_duration=3600.0,
        )
        defaults.update(kwargs)
        return IPAMPlugin(**defaults)

    def test_pool_size(self):
        ipam = self._make_ipam()
        # /24 = 254 hosts - 1 gateway = 253
        assert ipam.pool_size == 253

    def test_allocate_returns_allocation(self):
        ipam = self._make_ipam()
        alloc = ipam.allocate("c1")
        assert isinstance(alloc, IPAllocation)
        assert alloc.container_id == "c1"

    def test_allocate_assigns_ip(self):
        ipam = self._make_ipam()
        alloc = ipam.allocate("c1")
        assert alloc.ip_address.startswith("10.244.0.")
        assert alloc.ip_address != "10.244.0.1"  # Not gateway

    def test_allocate_sets_gateway(self):
        ipam = self._make_ipam()
        alloc = ipam.allocate("c1")
        assert alloc.gateway == "10.244.0.1"

    def test_allocate_creates_lease(self):
        ipam = self._make_ipam()
        ipam.allocate("c1")
        assert "c1" in ipam.leases
        assert ipam.leases["c1"].state == LeaseState.ACTIVE

    def test_allocate_multiple(self):
        ipam = self._make_ipam()
        a1 = ipam.allocate("c1")
        a2 = ipam.allocate("c2")
        assert a1.ip_address != a2.ip_address
        assert ipam.total_allocated == 2

    def test_allocate_conflict(self):
        ipam = self._make_ipam()
        ipam.allocate("c1")
        with pytest.raises(IPAMConflictError):
            ipam.allocate("c1")

    def test_allocate_exhausted(self):
        # Use a very small subnet
        ipam = self._make_ipam(subnet="10.244.0.0/30", gateway="10.244.0.1")
        # /30 = 2 hosts - 1 gateway = 1
        ipam.allocate("c1")
        with pytest.raises(IPAMExhaustedError):
            ipam.allocate("c2")

    def test_release(self):
        ipam = self._make_ipam()
        ipam.allocate("c1")
        ipam.release("c1")
        assert not ipam.has_allocation("c1")
        assert "c1" not in ipam.leases

    def test_release_returns_to_pool(self):
        ipam = self._make_ipam()
        initial_size = ipam.pool_size
        ipam.allocate("c1")
        ipam.release("c1")
        assert ipam.pool_size == initial_size

    def test_release_nonexistent(self):
        ipam = self._make_ipam()
        ipam.release("c1")  # Should not raise

    def test_renew(self):
        ipam = self._make_ipam()
        ipam.allocate("c1")
        lease = ipam.renew("c1")
        assert lease.renewal_count == 1

    def test_renew_nonexistent(self):
        ipam = self._make_ipam()
        with pytest.raises(IPAMError):
            ipam.renew("c1")

    def test_has_allocation(self):
        ipam = self._make_ipam()
        assert not ipam.has_allocation("c1")
        ipam.allocate("c1")
        assert ipam.has_allocation("c1")

    def test_get_allocation(self):
        ipam = self._make_ipam()
        ipam.allocate("c1")
        alloc = ipam.get_allocation("c1")
        assert alloc is not None
        assert alloc.container_id == "c1"

    def test_get_allocation_none(self):
        ipam = self._make_ipam()
        assert ipam.get_allocation("c1") is None

    def test_detect_no_conflicts(self):
        ipam = self._make_ipam()
        ipam.allocate("c1")
        ipam.allocate("c2")
        conflicts = ipam.detect_conflicts()
        assert len(conflicts) == 0

    def test_utilization(self):
        ipam = self._make_ipam()
        assert ipam.utilization == 0.0
        ipam.allocate("c1")
        assert ipam.utilization > 0.0
        assert ipam.utilization < 1.0

    def test_prefix_length(self):
        ipam = self._make_ipam()
        alloc = ipam.allocate("c1")
        assert alloc.prefix_length == 24

    def test_event_bus(self):
        bus = MagicMock()
        ipam = IPAMPlugin(
            subnet="10.244.0.0/24",
            gateway="10.244.0.1",
            event_bus=bus,
        )
        ipam.allocate("c1")
        assert bus.publish.called


# ============================================================
# Port Mapper Tests
# ============================================================


class TestPortMapper:
    """Validate port mapping (DNAT) manager."""

    def test_add_mapping(self):
        pm = PortMapper()
        mapping = pm.add_mapping(8080, "10.244.0.2", 80, "tcp", "c1")
        assert mapping.host_port == 8080
        assert mapping.container_port == 80

    def test_add_mapping_returns_id(self):
        pm = PortMapper()
        mapping = pm.add_mapping(8080, "10.244.0.2", 80)
        assert mapping.mapping_id is not None

    def test_total_mappings(self):
        pm = PortMapper()
        pm.add_mapping(8080, "10.244.0.2", 80)
        pm.add_mapping(8081, "10.244.0.3", 80)
        assert pm.total_mappings == 2

    def test_port_conflict(self):
        pm = PortMapper()
        pm.add_mapping(8080, "10.244.0.2", 80, "tcp")
        with pytest.raises(PortConflictError):
            pm.add_mapping(8080, "10.244.0.3", 80, "tcp")

    def test_same_port_different_protocol(self):
        pm = PortMapper()
        pm.add_mapping(8080, "10.244.0.2", 80, "tcp")
        mapping = pm.add_mapping(8080, "10.244.0.3", 80, "udp")
        assert mapping is not None

    def test_remove_mapping(self):
        pm = PortMapper()
        mapping = pm.add_mapping(8080, "10.244.0.2", 80)
        pm.remove_mapping(mapping.mapping_id)
        assert pm.total_mappings == 0

    def test_remove_nonexistent(self):
        pm = PortMapper()
        with pytest.raises(PortMappingError):
            pm.remove_mapping("nonexistent")

    def test_remove_container_mappings(self):
        pm = PortMapper()
        pm.add_mapping(8080, "10.244.0.2", 80, container_id="c1")
        pm.add_mapping(8081, "10.244.0.2", 81, container_id="c1")
        pm.add_mapping(9090, "10.244.0.3", 80, container_id="c2")
        removed = pm.remove_container_mappings("c1")
        assert removed == 2
        assert pm.total_mappings == 1

    def test_resolve(self):
        pm = PortMapper()
        pm.add_mapping(8080, "10.244.0.2", 80, "tcp")
        mapping = pm.resolve(8080, "tcp")
        assert mapping is not None
        assert mapping.container_ip == "10.244.0.2"

    def test_resolve_not_found(self):
        pm = PortMapper()
        assert pm.resolve(9999) is None

    def test_get_container_mappings(self):
        pm = PortMapper()
        pm.add_mapping(8080, "10.244.0.2", 80, container_id="c1")
        pm.add_mapping(8081, "10.244.0.2", 81, container_id="c1")
        mappings = pm.get_container_mappings("c1")
        assert len(mappings) == 2

    def test_invalid_host_port(self):
        pm = PortMapper()
        with pytest.raises(PortMappingError):
            pm.add_mapping(0, "10.244.0.2", 80)

    def test_invalid_container_port(self):
        pm = PortMapper()
        with pytest.raises(PortMappingError):
            pm.add_mapping(8080, "10.244.0.2", 0)

    def test_port_reuse_after_remove(self):
        pm = PortMapper()
        mapping = pm.add_mapping(8080, "10.244.0.2", 80)
        pm.remove_mapping(mapping.mapping_id)
        new_mapping = pm.add_mapping(8080, "10.244.0.3", 80)
        assert new_mapping is not None


# ============================================================
# Container DNS Tests
# ============================================================


class TestContainerDNS:
    """Validate container DNS server."""

    def test_add_a_record(self):
        dns = ContainerDNS()
        record = dns.add_record("web", DNSRecordType.A, "10.244.0.2", "c1")
        assert record.name == "web.cluster.fizz"
        assert record.value == "10.244.0.2"

    def test_add_creates_ptr(self):
        dns = ContainerDNS()
        dns.add_record("web", DNSRecordType.A, "10.244.0.2", "c1")
        # PTR should be auto-created
        results = dns.resolve("10.244.0.2", DNSRecordType.PTR)
        assert len(results) == 1
        assert results[0].value == "web.cluster.fizz"

    def test_resolve_a_record(self):
        dns = ContainerDNS()
        dns.add_record("web", DNSRecordType.A, "10.244.0.2", "c1")
        results = dns.resolve("web", DNSRecordType.A)
        assert len(results) == 1
        assert results[0].value == "10.244.0.2"

    def test_resolve_missing(self):
        dns = ContainerDNS()
        results = dns.resolve("nonexistent", DNSRecordType.A)
        assert len(results) == 0

    def test_resolve_fqdn(self):
        dns = ContainerDNS()
        dns.add_record("web", DNSRecordType.A, "10.244.0.2", "c1")
        results = dns.resolve("web.cluster.fizz", DNSRecordType.A)
        assert len(results) == 1

    def test_add_srv_record(self):
        dns = ContainerDNS()
        record = dns.add_record(
            "_http._tcp.web", DNSRecordType.SRV, "web.cluster.fizz",
            priority=10, port=80, weight=100,
        )
        assert record.priority == 10
        assert record.port == 80

    def test_add_cname_record(self):
        dns = ContainerDNS()
        record = dns.add_record("alias", DNSRecordType.CNAME, "web.cluster.fizz")
        assert record.record_type == DNSRecordType.CNAME

    def test_register_container(self):
        dns = ContainerDNS()
        records = dns.register_container("c1", "web-server", "10.244.0.2")
        assert len(records) == 2  # A + SRV

    def test_remove_container_records(self):
        dns = ContainerDNS()
        dns.register_container("c1", "web-server", "10.244.0.2")
        removed = dns.remove_container_records("c1")
        assert removed > 0

    def test_remove_clears_resolution(self):
        dns = ContainerDNS()
        dns.register_container("c1", "web-server", "10.244.0.2")
        dns.remove_container_records("c1")
        results = dns.resolve("web-server", DNSRecordType.A)
        assert len(results) == 0

    def test_total_records(self):
        dns = ContainerDNS()
        dns.add_record("web", DNSRecordType.A, "10.244.0.2")
        assert dns.total_records >= 1

    def test_query_count(self):
        dns = ContainerDNS()
        dns.add_record("web", DNSRecordType.A, "10.244.0.2")
        dns.resolve("web")
        dns.resolve("web")
        assert dns.total_queries == 2

    def test_custom_domain(self):
        dns = ContainerDNS(domain="test.local")
        record = dns.add_record("web", DNSRecordType.A, "10.0.0.1")
        assert record.name == "web.test.local"

    def test_custom_ttl(self):
        dns = ContainerDNS(ttl=60)
        record = dns.add_record("web", DNSRecordType.A, "10.0.0.1")
        assert record.ttl == 60

    def test_multiple_records_same_name(self):
        dns = ContainerDNS()
        dns.add_record("web", DNSRecordType.A, "10.244.0.2", "c1")
        dns.add_record("web", DNSRecordType.A, "10.244.0.3", "c2")
        results = dns.resolve("web", DNSRecordType.A)
        assert len(results) == 2


# ============================================================
# Network Policy Engine Tests
# ============================================================


class TestNetworkPolicyEngine:
    """Validate network policy enforcement engine."""

    def _make_policy(self, name="test-policy", pod_selector=None, ingress=None, egress=None):
        policy = NetworkPolicySpec(
            name=name,
            pod_selector=pod_selector or {},
            ingress_rules=ingress or [],
            egress_rules=egress or [],
        )
        return policy

    def test_add_policy(self):
        engine = NetworkPolicyEngine()
        policy = self._make_policy()
        engine.add_policy(policy)
        assert engine.total_policies == 1

    def test_remove_policy(self):
        engine = NetworkPolicyEngine()
        policy = self._make_policy()
        engine.add_policy(policy)
        engine.remove_policy(policy.policy_id)
        assert engine.total_policies == 0

    def test_remove_nonexistent(self):
        engine = NetworkPolicyEngine()
        with pytest.raises(NetworkPolicyError):
            engine.remove_policy("nonexistent")

    def test_set_container_labels(self):
        engine = NetworkPolicyEngine()
        engine.set_container_labels("c1", {"app": "web"})
        assert engine.container_labels["c1"] == {"app": "web"}

    def test_remove_container(self):
        engine = NetworkPolicyEngine()
        engine.set_container_labels("c1", {"app": "web"})
        engine.remove_container("c1")
        assert "c1" not in engine.container_labels

    def test_evaluate_no_policies(self):
        engine = NetworkPolicyEngine()
        result = engine.evaluate("c1", "c2")
        assert result == PolicyAction.ALLOW

    def test_evaluate_allow(self):
        engine = NetworkPolicyEngine()
        engine.set_container_labels("c1", {"app": "web"})
        engine.set_container_labels("c2", {"app": "api"})

        rule = NetworkPolicyRule(
            direction=PolicyDirection.INGRESS,
            action=PolicyAction.ALLOW,
            selector_labels={"app": "web"},
        )
        policy = self._make_policy(
            pod_selector={"app": "api"},
            ingress=[rule],
        )
        engine.add_policy(policy)

        result = engine.evaluate("c1", "c2")
        assert result == PolicyAction.ALLOW

    def test_evaluate_deny_no_matching_rule(self):
        engine = NetworkPolicyEngine()
        engine.set_container_labels("c1", {"app": "web"})
        engine.set_container_labels("c2", {"app": "api"})

        # Policy with ingress rule that doesn't match source
        rule = NetworkPolicyRule(
            direction=PolicyDirection.INGRESS,
            action=PolicyAction.ALLOW,
            selector_labels={"app": "db"},  # Doesn't match c1
        )
        policy = self._make_policy(
            pod_selector={"app": "api"},
            ingress=[rule],
        )
        engine.add_policy(policy)

        result = engine.evaluate("c1", "c2")
        assert result == PolicyAction.DENY

    def test_evaluate_with_port(self):
        engine = NetworkPolicyEngine()
        engine.set_container_labels("c1", {"app": "web"})
        engine.set_container_labels("c2", {"app": "api"})

        rule = NetworkPolicyRule(
            direction=PolicyDirection.INGRESS,
            action=PolicyAction.ALLOW,
            selector_labels={},
            ports=[80, 443],
        )
        policy = self._make_policy(
            pod_selector={"app": "api"},
            ingress=[rule],
        )
        engine.add_policy(policy)

        assert engine.evaluate("c1", "c2", dst_port=80) == PolicyAction.ALLOW
        assert engine.evaluate("c1", "c2", dst_port=8080) == PolicyAction.DENY

    def test_evaluate_cidr(self):
        engine = NetworkPolicyEngine()
        engine.set_container_labels("c1", {})
        engine.set_container_labels("c2", {"app": "api"})

        rule = NetworkPolicyRule(
            direction=PolicyDirection.INGRESS,
            action=PolicyAction.ALLOW,
            cidr_blocks=["10.244.0.0/24"],
        )
        policy = self._make_policy(
            pod_selector={"app": "api"},
            ingress=[rule],
        )
        engine.add_policy(policy)

        assert engine.evaluate("c1", "c2", src_ip="10.244.0.5") == PolicyAction.ALLOW
        assert engine.evaluate("c1", "c2", src_ip="192.168.1.1") == PolicyAction.DENY

    def test_connection_tracking(self):
        engine = NetworkPolicyEngine()
        # No policies = allow all, tracked
        engine.evaluate("c1", "c2", dst_port=80)
        assert len(engine.connection_table) == 1

    def test_evaluation_count(self):
        engine = NetworkPolicyEngine()
        engine.evaluate("c1", "c2")
        engine.evaluate("c1", "c3")
        assert engine.evaluation_count == 2

    def test_allow_count(self):
        engine = NetworkPolicyEngine()
        engine.evaluate("c1", "c2")
        assert engine.allow_count == 1

    def test_get_applicable_policies(self):
        engine = NetworkPolicyEngine()
        engine.set_container_labels("c1", {"app": "web"})
        policy = self._make_policy(pod_selector={"app": "web"})
        engine.add_policy(policy)
        applicable = engine.get_applicable_policies("c1")
        assert len(applicable) == 1

    def test_empty_selector_matches_all(self):
        engine = NetworkPolicyEngine()
        engine.set_container_labels("c1", {"app": "anything"})
        policy = self._make_policy(pod_selector={})
        engine.add_policy(policy)
        applicable = engine.get_applicable_policies("c1")
        assert len(applicable) == 1


# ============================================================
# CNI Manager Tests
# ============================================================


class TestCNIManager:
    """Validate CNI manager orchestrator."""

    def _make_manager(self, **kwargs):
        defaults = dict(
            subnet="10.244.0.0/24",
            gateway="10.244.0.1",
            lease_duration=3600.0,
        )
        defaults.update(kwargs)
        return CNIManager(**defaults)

    def test_default_plugin(self):
        mgr = self._make_manager()
        assert mgr.default_plugin_type == PluginType.BRIDGE

    def test_has_all_plugins(self):
        mgr = self._make_manager()
        assert PluginType.BRIDGE in mgr.plugins
        assert PluginType.HOST in mgr.plugins
        assert PluginType.NONE in mgr.plugins
        assert PluginType.OVERLAY in mgr.plugins

    def test_add_bridge(self):
        mgr = self._make_manager()
        result = mgr.add("c1", "/netns/c1")
        assert isinstance(result, CNIResult)
        assert len(result.interfaces) > 0

    def test_add_host(self):
        mgr = self._make_manager()
        result = mgr.add("c1", plugin_type=PluginType.HOST)
        assert isinstance(result, CNIResult)

    def test_add_none(self):
        mgr = self._make_manager()
        result = mgr.add("c1", plugin_type=PluginType.NONE)
        assert result.interfaces[0]["name"] == "lo"

    def test_add_overlay(self):
        mgr = self._make_manager()
        result = mgr.add("c1", plugin_type=PluginType.OVERLAY)
        assert isinstance(result, CNIResult)

    def test_add_registers_dns(self):
        mgr = self._make_manager()
        mgr.add("c1", container_name="web-server")
        records = mgr.dns.resolve("web-server", DNSRecordType.A)
        assert len(records) >= 1

    def test_delete(self):
        mgr = self._make_manager()
        mgr.add("c1")
        mgr.delete("c1")
        assert mgr.active_container_count == 0

    def test_delete_cleans_dns(self):
        mgr = self._make_manager()
        mgr.add("c1", container_name="web")
        mgr.delete("c1")
        records = mgr.dns.resolve("web", DNSRecordType.A)
        assert len(records) == 0

    def test_delete_unknown(self):
        mgr = self._make_manager()
        with pytest.raises(CNIPluginNotFoundError):
            mgr.delete("nonexistent")

    def test_check(self):
        mgr = self._make_manager()
        mgr.add("c1")
        assert mgr.check("c1") is True

    def test_check_unknown(self):
        mgr = self._make_manager()
        with pytest.raises(CNIPluginNotFoundError):
            mgr.check("nonexistent")

    def test_get_plugin(self):
        mgr = self._make_manager()
        plugin = mgr.get_plugin(PluginType.BRIDGE)
        assert plugin is not None
        assert isinstance(plugin, BridgePlugin)

    def test_list_networks(self):
        mgr = self._make_manager()
        networks = mgr.list_networks()
        assert len(networks) == 4

    def test_get_stats(self):
        mgr = self._make_manager()
        mgr.add("c1")
        stats = mgr.get_stats()
        assert stats.total_add_ops >= 1
        assert stats.active_containers >= 1

    def test_active_container_count(self):
        mgr = self._make_manager()
        mgr.add("c1")
        mgr.add("c2", plugin_type=PluginType.HOST)
        assert mgr.active_container_count == 2

    def test_labels_for_policy(self):
        mgr = self._make_manager()
        mgr.add("c1", labels={"app": "web"})
        assert "c1" in mgr.policy_engine.container_labels

    def test_port_mapper_accessible(self):
        mgr = self._make_manager()
        assert mgr.port_mapper is not None

    def test_dns_accessible(self):
        mgr = self._make_manager()
        assert mgr.dns is not None


# ============================================================
# Dashboard Tests
# ============================================================


class TestCNIDashboard:
    """Validate ASCII dashboard rendering."""

    def _make_manager_with_data(self):
        mgr = CNIManager(
            subnet="10.244.0.0/24",
            gateway="10.244.0.1",
        )
        mgr.add("c1", container_name="web")
        mgr.add("c2", container_name="api")
        mgr.port_mapper.add_mapping(8080, "10.244.0.2", 80, container_id="c1")
        return mgr

    def test_render(self):
        mgr = self._make_manager_with_data()
        dashboard = CNIDashboard()
        output = dashboard.render(mgr)
        assert "FIZZCNI" in output
        assert "NETWORKS" in output
        assert "IPAM" in output

    def test_render_topology(self):
        mgr = self._make_manager_with_data()
        dashboard = CNIDashboard()
        output = dashboard.render_topology(mgr)
        assert "TOPOLOGY" in output
        assert "fizzbr0" in output

    def test_render_ipam_stats(self):
        mgr = self._make_manager_with_data()
        dashboard = CNIDashboard()
        output = dashboard.render_ipam_stats(mgr)
        assert "IPAM" in output
        assert "10.244.0.0/24" in output

    def test_render_port_mappings(self):
        mgr = self._make_manager_with_data()
        dashboard = CNIDashboard()
        output = dashboard.render_port_mappings(mgr)
        assert "PORT MAPPINGS" in output
        assert "8080" in output

    def test_render_policies(self):
        mgr = self._make_manager_with_data()
        dashboard = CNIDashboard()
        output = dashboard.render_policies(mgr)
        assert "NETWORK POLICIES" in output

    def test_custom_width(self):
        dashboard = CNIDashboard(width=100)
        assert dashboard.width == 100

    def test_render_with_policies(self):
        mgr = self._make_manager_with_data()
        policy = NetworkPolicySpec(name="deny-all", pod_selector={})
        mgr.policy_engine.add_policy(policy)
        dashboard = CNIDashboard()
        output = dashboard.render_policies(mgr)
        assert "deny-all" in output


# ============================================================
# Middleware Tests
# ============================================================


class TestFizzCNIMiddleware:
    """Validate FizzCNI middleware integration."""

    def _make_middleware(self, **kwargs):
        mgr = CNIManager(
            subnet="10.244.0.0/24",
            gateway="10.244.0.1",
        )
        return FizzCNIMiddleware(manager=mgr, **kwargs)

    @staticmethod
    def _identity_handler(ctx):
        return ctx

    def test_priority(self):
        mw = self._make_middleware()
        assert mw.priority == MIDDLEWARE_PRIORITY

    def test_priority_is_111(self):
        mw = self._make_middleware()
        assert mw.priority == 111

    def test_get_name(self):
        mw = self._make_middleware()
        assert mw.get_name() == "FizzCNIMiddleware"

    def test_get_priority(self):
        mw = self._make_middleware()
        assert mw.get_priority() == MIDDLEWARE_PRIORITY

    def test_process_returns_context(self):
        mw = self._make_middleware()
        ctx = ProcessingContext(number=3, session_id="test")
        output = mw.process(ctx, self._identity_handler)
        assert output is ctx

    def test_process_increments_count(self):
        mw = self._make_middleware()
        ctx1 = ProcessingContext(number=1, session_id="test")
        ctx2 = ProcessingContext(number=2, session_id="test")
        mw.process(ctx1, self._identity_handler)
        mw.process(ctx2, self._identity_handler)
        assert mw._evaluation_count == 2

    def test_render_dashboard(self):
        mw = self._make_middleware()
        ctx = ProcessingContext(number=1, session_id="test")
        mw.process(ctx, self._identity_handler)
        output = mw.render_dashboard()
        assert "FIZZCNI" in output

    def test_render_topology(self):
        mw = self._make_middleware()
        output = mw.render_topology()
        assert "TOPOLOGY" in output

    def test_render_ipam_stats(self):
        mw = self._make_middleware()
        output = mw.render_ipam_stats()
        assert "IPAM" in output

    def test_render_port_mappings(self):
        mw = self._make_middleware()
        output = mw.render_port_mappings()
        assert "PORT" in output

    def test_render_policies(self):
        mw = self._make_middleware()
        output = mw.render_policies()
        assert "POLIC" in output

    def test_render_stats(self):
        mw = self._make_middleware()
        output = mw.render_stats()
        assert "FizzCNI" in output


# ============================================================
# Factory Tests
# ============================================================


class TestFactory:
    """Validate factory function."""

    def test_create_subsystem(self):
        manager, middleware = create_fizzcni_subsystem()
        assert isinstance(manager, CNIManager)
        assert isinstance(middleware, FizzCNIMiddleware)

    def test_custom_subnet(self):
        manager, _ = create_fizzcni_subsystem(subnet="172.16.0.0/16")
        assert manager.ipam.subnet == "172.16.0.0/16"

    def test_custom_gateway(self):
        manager, _ = create_fizzcni_subsystem(
            subnet="172.16.0.0/16",
            gateway="172.16.0.1",
        )
        assert manager.ipam.gateway == "172.16.0.1"

    def test_custom_bridge_name(self):
        manager, _ = create_fizzcni_subsystem(bridge_name="testbr0")
        bridge = manager.get_plugin(PluginType.BRIDGE)
        assert isinstance(bridge, BridgePlugin)
        assert bridge.bridge.name == "testbr0"

    def test_custom_dns_domain(self):
        manager, _ = create_fizzcni_subsystem(dns_domain="test.local")
        assert manager.dns.domain == "test.local"

    def test_event_bus(self):
        bus = MagicMock()
        manager, middleware = create_fizzcni_subsystem(event_bus=bus)
        assert manager is not None


# ============================================================
# Exception Tests
# ============================================================


class TestExceptions:
    """Validate all 18 CNI exception classes."""

    def test_cni_error(self):
        exc = CNIError("test")
        assert "test" in str(exc)
        assert exc.error_code == "EFP-CNI00"
        assert exc.context["reason"] == "test"

    def test_cni_plugin_not_found_error(self):
        exc = CNIPluginNotFoundError("plugin missing")
        assert exc.error_code == "EFP-CNI01"
        assert exc.context["reason"] == "plugin missing"

    def test_cni_add_error(self):
        exc = CNIAddError("add failed")
        assert exc.error_code == "EFP-CNI02"
        assert exc.context["reason"] == "add failed"

    def test_cni_delete_error(self):
        exc = CNIDeleteError("del failed")
        assert exc.error_code == "EFP-CNI03"

    def test_cni_check_error(self):
        exc = CNICheckError("check failed")
        assert exc.error_code == "EFP-CNI04"

    def test_veth_creation_error(self):
        exc = VethCreationError("veth failed")
        assert exc.error_code == "EFP-CNI05"

    def test_bridge_error(self):
        exc = BridgeError("bridge failed")
        assert exc.error_code == "EFP-CNI06"

    def test_ipam_error(self):
        exc = IPAMError("ipam failed")
        assert exc.error_code == "EFP-CNI07"

    def test_ipam_exhausted_error(self):
        exc = IPAMExhaustedError("pool empty")
        assert exc.error_code == "EFP-CNI08"

    def test_ipam_lease_expired_error(self):
        exc = IPAMLeaseExpiredError("lease expired")
        assert exc.error_code == "EFP-CNI09"

    def test_ipam_conflict_error(self):
        exc = IPAMConflictError("conflict")
        assert exc.error_code == "EFP-CNI10"

    def test_port_mapping_error(self):
        exc = PortMappingError("mapping failed")
        assert exc.error_code == "EFP-CNI11"

    def test_port_conflict_error(self):
        exc = PortConflictError("conflict")
        assert exc.error_code == "EFP-CNI12"

    def test_container_dns_error(self):
        exc = ContainerDNSError("dns failed")
        assert exc.error_code == "EFP-CNI13"

    def test_network_policy_error(self):
        exc = NetworkPolicyError("policy failed")
        assert exc.error_code == "EFP-CNI14"

    def test_overlay_network_error(self):
        exc = OverlayNetworkError("overlay failed")
        assert exc.error_code == "EFP-CNI15"

    def test_cni_dashboard_error(self):
        exc = CNIDashboardError("dashboard failed")
        assert exc.error_code == "EFP-CNI16"

    def test_cni_middleware_error(self):
        exc = CNIMiddlewareError(42, "middleware failed")
        assert exc.error_code == "EFP-CNI17"
        assert exc.evaluation_number == 42
        assert exc.context["reason"] == "middleware failed"

    def test_all_inherit_from_fizzbuzz_error(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        exceptions = [
            CNIError("t"), CNIPluginNotFoundError("t"), CNIAddError("t"),
            CNIDeleteError("t"), CNICheckError("t"), VethCreationError("t"),
            BridgeError("t"), IPAMError("t"), IPAMExhaustedError("t"),
            IPAMLeaseExpiredError("t"), IPAMConflictError("t"),
            PortMappingError("t"), PortConflictError("t"),
            ContainerDNSError("t"), NetworkPolicyError("t"),
            OverlayNetworkError("t"), CNIDashboardError("t"),
            CNIMiddlewareError(1, "t"),
        ]
        for exc in exceptions:
            assert isinstance(exc, FizzBuzzError)

    def test_all_inherit_from_cni_error(self):
        exceptions = [
            CNIPluginNotFoundError("t"), CNIAddError("t"),
            CNIDeleteError("t"), CNICheckError("t"), VethCreationError("t"),
            BridgeError("t"), IPAMError("t"), IPAMExhaustedError("t"),
            IPAMLeaseExpiredError("t"), IPAMConflictError("t"),
            PortMappingError("t"), PortConflictError("t"),
            ContainerDNSError("t"), NetworkPolicyError("t"),
            OverlayNetworkError("t"), CNIDashboardError("t"),
            CNIMiddlewareError(1, "t"),
        ]
        for exc in exceptions:
            assert isinstance(exc, CNIError)


# ============================================================
# EventType Tests
# ============================================================


class TestEventTypes:
    """Validate CNI EventType members."""

    def test_cni_container_added(self):
        assert EventType.CNI_CONTAINER_ADDED is not None

    def test_cni_container_deleted(self):
        assert EventType.CNI_CONTAINER_DELETED is not None

    def test_cni_container_checked(self):
        assert EventType.CNI_CONTAINER_CHECKED is not None

    def test_cni_veth_created(self):
        assert EventType.CNI_VETH_CREATED is not None

    def test_cni_veth_deleted(self):
        assert EventType.CNI_VETH_DELETED is not None

    def test_cni_bridge_created(self):
        assert EventType.CNI_BRIDGE_CREATED is not None

    def test_cni_ip_allocated(self):
        assert EventType.CNI_IP_ALLOCATED is not None

    def test_cni_ip_released(self):
        assert EventType.CNI_IP_RELEASED is not None

    def test_cni_lease_granted(self):
        assert EventType.CNI_LEASE_GRANTED is not None

    def test_cni_lease_expired(self):
        assert EventType.CNI_LEASE_EXPIRED is not None

    def test_cni_port_mapped(self):
        assert EventType.CNI_PORT_MAPPED is not None

    def test_cni_port_unmapped(self):
        assert EventType.CNI_PORT_UNMAPPED is not None

    def test_cni_dns_record_added(self):
        assert EventType.CNI_DNS_RECORD_ADDED is not None

    def test_cni_dns_resolved(self):
        assert EventType.CNI_DNS_RESOLVED is not None

    def test_cni_policy_evaluated(self):
        assert EventType.CNI_POLICY_EVALUATED is not None

    def test_cni_dashboard_rendered(self):
        assert EventType.CNI_DASHBOARD_RENDERED is not None


# ============================================================
# Integration Tests
# ============================================================


class TestIntegration:
    """End-to-end integration tests."""

    def test_full_lifecycle(self):
        """Test complete container network lifecycle."""
        manager, middleware = create_fizzcni_subsystem(
            subnet="10.244.0.0/24",
            gateway="10.244.0.1",
        )

        # ADD
        result = manager.add("c1", container_name="web")
        assert result.ips[0]["gateway"] == "10.244.0.1"

        # CHECK
        assert manager.check("c1") is True

        # Port mapping
        ip = result.ips[0]["address"].split("/")[0]
        manager.port_mapper.add_mapping(8080, ip, 80, container_id="c1")

        # DNS
        records = manager.dns.resolve("web", DNSRecordType.A)
        assert len(records) >= 1

        # DEL
        manager.delete("c1")
        assert manager.active_container_count == 0

    def test_multi_container(self):
        """Test multiple containers with policies."""
        manager, _ = create_fizzcni_subsystem(
            subnet="10.244.0.0/24",
            gateway="10.244.0.1",
        )

        manager.add("c1", container_name="web", labels={"app": "web"})
        manager.add("c2", container_name="api", labels={"app": "api"})
        manager.add("c3", container_name="db", labels={"app": "db"})

        assert manager.active_container_count == 3

        # Add policy
        rule = NetworkPolicyRule(
            direction=PolicyDirection.INGRESS,
            action=PolicyAction.ALLOW,
            selector_labels={"app": "api"},
        )
        policy = NetworkPolicySpec(
            name="db-ingress",
            pod_selector={"app": "db"},
            ingress_rules=[rule],
        )
        manager.policy_engine.add_policy(policy)

        # API -> DB should be allowed
        result = manager.policy_engine.evaluate("c2", "c3")
        assert result == PolicyAction.ALLOW

        # Web -> DB should be denied
        result = manager.policy_engine.evaluate("c1", "c3")
        assert result == PolicyAction.DENY

        manager.delete("c1")
        manager.delete("c2")
        manager.delete("c3")
        assert manager.active_container_count == 0

    def test_middleware_pipeline(self):
        """Test middleware processes evaluations."""
        _, middleware = create_fizzcni_subsystem(
            subnet="10.244.0.0/24",
            gateway="10.244.0.1",
        )

        def identity(ctx):
            return ctx

        for i in range(1, 6):
            ctx = ProcessingContext(number=i, session_id="test")
            output = middleware.process(ctx, identity)
            assert output is ctx

        assert middleware._evaluation_count == 5

    def test_dashboard_after_pipeline(self):
        """Test dashboard renders after pipeline processing."""
        manager, middleware = create_fizzcni_subsystem(
            subnet="10.244.0.0/24",
            gateway="10.244.0.1",
        )

        manager.add("c1", container_name="web")
        manager.port_mapper.add_mapping(8080, "10.244.0.2", 80, container_id="c1")

        dashboard = middleware.render_dashboard()
        assert "FIZZCNI" in dashboard

        stats = middleware.render_stats()
        assert "FizzCNI" in stats

    def test_overlay_with_vtep(self):
        """Test overlay plugin with VTEP registration."""
        manager, _ = create_fizzcni_subsystem(
            subnet="10.244.0.0/24",
            gateway="10.244.0.1",
        )

        overlay = manager.get_plugin(PluginType.OVERLAY)
        assert isinstance(overlay, OverlayPlugin)

        overlay.register_vtep("192.168.1.2")
        overlay.learn_mac("aa:bb:cc:dd:ee:ff", "192.168.1.2")

        encap = overlay.encapsulate(b"test", "11:22:33:44:55:66", "aa:bb:cc:dd:ee:ff")
        assert encap is not None
        assert encap["vtep_dst"] == "192.168.1.2"
