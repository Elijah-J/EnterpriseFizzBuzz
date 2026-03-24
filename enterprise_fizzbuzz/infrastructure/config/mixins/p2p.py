"""Peer-to-Peer Gossip Network properties"""

from __future__ import annotations

from typing import Any


class P2pConfigMixin:
    """Configuration properties for the p2p subsystem."""

    # ------------------------------------------------------------------
    # Peer-to-Peer Gossip Network properties
    # ------------------------------------------------------------------

    @property
    def p2p_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("p2p", {}).get("enabled", False)

    @property
    def p2p_num_nodes(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("p2p", {}).get("num_nodes", 7)

    @property
    def p2p_k_bucket_size(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("p2p", {}).get("k_bucket_size", 3)

    @property
    def p2p_gossip_fanout(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("p2p", {}).get("gossip_fanout", 3)

    @property
    def p2p_suspect_timeout_rounds(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("p2p", {}).get("suspect_timeout_rounds", 3)

    @property
    def p2p_max_gossip_rounds(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("p2p", {}).get("max_gossip_rounds", 20)

    @property
    def p2p_dashboard_width(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("p2p", {}).get("dashboard", {}).get("width", 60)

