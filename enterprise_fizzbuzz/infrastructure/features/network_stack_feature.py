"""Feature descriptor for the FizzNet TCP/IP protocol stack."""

from __future__ import annotations

import time
from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class NetworkStackFeature(FeatureDescriptor):
    name = "network_stack"
    description = "Full TCP/IP protocol stack with Ethernet II, IPv4, TCP Reno, and FizzBuzz Protocol"
    middleware_priority = 200
    cli_flags = [
        ("--fizznet", {"action": "store_true", "default": False,
                       "help": "Enable FizzNet: full TCP/IP protocol stack for reliable FizzBuzz classification delivery"}),
        ("--fizznet-ping", {"type": int, "metavar": "N", "default": None,
                            "help": "Send N ICMP echo requests through the FizzNet stack and display results"}),
        ("--fizznet-dashboard", {"action": "store_true", "default": False,
                                 "help": "Display the FizzNet ASCII dashboard with packet counters, TCP state, and congestion window"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizznet", False),
            getattr(args, "fizznet_ping", None) is not None,
            getattr(args, "fizznet_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.network_stack import (
            FizzBuzzProtocol,
            NetworkInterface,
            NetworkMiddleware,
            NetworkStack,
        )

        stack = NetworkStack()
        server_ip = config.fizznet_server_ip
        client_ip = config.fizznet_client_ip
        server_port = config.fizznet_server_port

        server_iface = NetworkInterface(
            name="fizz0",
            mac_address="02:fb:00:00:00:01",
            ip_address=server_ip,
        )
        client_iface = NetworkInterface(
            name="fizz1",
            mac_address="02:fb:00:00:00:02",
            ip_address=client_ip,
        )
        stack.add_interface(server_iface)
        stack.add_interface(client_iface)

        protocol = FizzBuzzProtocol(stack)
        protocol.start_server(server_ip, server_port)

        middleware = None
        if getattr(args, "fizznet", False):
            middleware = NetworkMiddleware(
                stack=stack,
                server_ip=server_ip,
                client_ip=client_ip,
                server_port=server_port,
                enable_dashboard=getattr(args, "fizznet_dashboard", False),
            )

        service = {"stack": stack, "protocol": protocol}
        return service, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        server_ip = config.fizznet_server_ip
        client_ip = config.fizznet_client_ip
        server_port = config.fizznet_server_port
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZNET: TCP/IP PROTOCOL STACK ENABLED                  |\n"
            f"  |   Server: {server_ip}:{server_port}                            |\n"
            f"  |   Client: {client_ip}                                  |\n"
            "  |   Stack: Ethernet II / IPv4 / TCP (Reno) / FBZP        |\n"
            "  |   Every evaluation traverses the full OSI model.        |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "fizznet_dashboard", False):
            return None
        from enterprise_fizzbuzz.infrastructure.network_stack import NetworkDashboard
        from enterprise_fizzbuzz.infrastructure.config import ConfigurationManager
        config = ConfigurationManager()
        # Dashboard rendering requires the stack and protocol from service
        return None
