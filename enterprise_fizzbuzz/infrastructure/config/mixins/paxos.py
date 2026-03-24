"""Distributed Paxos Consensus properties"""

from __future__ import annotations

from typing import Any


class PaxosConfigMixin:
    """Configuration properties for the paxos subsystem."""

    # ----------------------------------------------------------------
    # Distributed Paxos Consensus properties
    # ----------------------------------------------------------------

    @property
    def paxos_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("paxos", {}).get("enabled", False)

    @property
    def paxos_num_nodes(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("paxos", {}).get("num_nodes", 5)

    @property
    def paxos_message_delay_ms(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("paxos", {}).get("message_delay_ms", 0)

    @property
    def paxos_message_drop_rate(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("paxos", {}).get("message_drop_rate", 0.0)

    @property
    def paxos_byzantine_mode(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("paxos", {}).get("byzantine_mode", False)

    @property
    def paxos_byzantine_lie_probability(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("paxos", {}).get("byzantine_lie_probability", 1.0)

    @property
    def paxos_partition_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("paxos", {}).get("partition_enabled", False)

    @property
    def paxos_partition_groups(self) -> list[list[int]]:
        self._ensure_loaded()
        return self._raw_config.get("paxos", {}).get("partition_groups", [[0, 1, 2], [3, 4]])

    @property
    def paxos_dashboard_width(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("paxos", {}).get("dashboard", {}).get("width", 60)

