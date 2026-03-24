"""Peer-to-Peer Gossip Network events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("P2P_NODE_JOINED")
EventType.register("P2P_GOSSIP_ROUND_COMPLETED")
EventType.register("P2P_NODE_STATE_CHANGED")
EventType.register("P2P_DHT_STORE")
EventType.register("P2P_MERKLE_SYNC")
EventType.register("P2P_DASHBOARD_RENDERED")
