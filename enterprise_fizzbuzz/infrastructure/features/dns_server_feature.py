"""Feature descriptor for the FizzDNS authoritative DNS server."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class DNSServerFeature(FeatureDescriptor):
    name = "dns_server"
    description = "Authoritative DNS server for fizzbuzz.local zone with BIND-style zone files and query resolution"
    middleware_priority = 130
    cli_flags = [
        ("--dns", {"action": "store_true", "default": False,
                   "help": "Enable the FizzDNS Authoritative DNS Server for fizzbuzz.local zone"}),
        ("--dns-query", {"type": str, "default": None, "metavar": "QUERY",
                         "help": "Execute a DNS query (e.g. --dns-query \"15.fizzbuzz.local TXT\")"}),
        ("--dns-zone", {"action": "store_true", "default": False,
                        "help": "Print the BIND-style zone file for fizzbuzz.local and exit"}),
        ("--dns-dashboard", {"action": "store_true", "default": False,
                             "help": "Display the FizzDNS ASCII dashboard with query stats, zone inventory, and cache stats"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "dns", False),
            bool(getattr(args, "dns_query", None)),
            getattr(args, "dns_zone", False),
            getattr(args, "dns_dashboard", False),
        ])

    def has_early_exit(self, args: Any) -> bool:
        return any([
            getattr(args, "dns_zone", False),
            bool(getattr(args, "dns_query", None)),
        ])

    def run_early_exit(self, args: Any, config: Any) -> int:
        if getattr(args, "dns_zone", False):
            from enterprise_fizzbuzz.infrastructure.dns_server import FizzBuzzZone
            print(FizzBuzzZone.generate_zone_file(
                range_start=getattr(config, "range_start", 1),
                range_end=getattr(config, "range_end", 100),
            ))
            return 0

        if getattr(args, "dns_query", None):
            import time as _dns_time
            from enterprise_fizzbuzz.infrastructure.dns_server import (
                DNSHeader,
                DNSMessage,
                DNSQueryFormatter,
                DNSQuestion,
                create_dns_subsystem,
            )

            parts = args.dns_query.strip().split()
            qname = parts[0] if parts else "fizzbuzz.local."
            qtype_str = parts[1] if len(parts) > 1 else "TXT"

            dns_zone, dns_resolver, dns_neg_cache, _ = create_dns_subsystem()

            _dns_start = _dns_time.monotonic()
            _type_map = {
                "A": 1, "NS": 2, "CNAME": 5, "SOA": 6, "PTR": 12,
                "MX": 15, "TXT": 16, "AAAA": 28, "SRV": 33, "ANY": 255,
            }
            query = DNSMessage()
            query.header = DNSHeader(id=0xFB15, qr=0, rd=1, qdcount=1)
            query.questions = [DNSQuestion(
                qname=qname,
                qtype=_type_map.get(qtype_str.upper(), 16),
            )]
            response = dns_resolver.resolve(query)
            _dns_elapsed = (_dns_time.monotonic() - _dns_start) * 1_000_000

            print()
            print(DNSQueryFormatter.format_response(response, query_time_us=_dns_elapsed))
            print()
            return 0

        return 0

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.dns_server import (
            create_dns_subsystem,
        )

        dns_zone, dns_resolver, dns_neg_cache, dns_middleware = create_dns_subsystem()
        return (dns_resolver, dns_neg_cache), dns_middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "dns_dashboard", False):
            return None
        if middleware is None:
            return "\n  FizzDNS not enabled. Use --dns to enable.\n"

        from enterprise_fizzbuzz.infrastructure.dns_server import DNSDashboard

        # middleware is the DNSMiddleware; the service tuple has (resolver, neg_cache)
        # For rendering we need the resolver — access it from the middleware
        resolver = middleware.resolver if hasattr(middleware, "resolver") else None
        neg_cache = middleware.negative_cache if hasattr(middleware, "negative_cache") else None
        if resolver is not None:
            return DNSDashboard.render(resolver, negative_cache=neg_cache)
        return None
