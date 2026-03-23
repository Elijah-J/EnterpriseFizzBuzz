"""
Enterprise FizzBuzz Platform - FizzDNS Authoritative DNS Server Test Suite

Comprehensive tests for the DNS server module, covering wire format
encoding/decoding, zone management, record lookup, negative caching,
query resolution, and dashboard rendering. The fizzbuzz.local zone
is a critical infrastructure component that enables DNS-based FizzBuzz
classification lookups across the enterprise network.
"""

from __future__ import annotations

import struct
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.dns_server import (
    DEFAULT_TTL,
    DNSClass,
    DNSDashboard,
    DNSHeader,
    DNSMessage,
    DNSMiddleware,
    DNSOpcode,
    DNSQuestion,
    DNSQueryFormatter,
    DNSRCode,
    DNSResolver,
    DNSResourceRecord,
    DNSType,
    DNSWireFormat,
    FizzBuzzZone,
    NegativeCache,
    SOARecordBuilder,
    TXTRecordBuilder,
    Zone,
    ZoneFile,
    _classify_number,
    create_dns_subsystem,
)


# =========================================================================
# DNS Constants & Enums
# =========================================================================

class TestDNSType:
    """Tests for DNS record type enumeration."""

    def test_standard_types_have_correct_values(self):
        assert DNSType.A == 1
        assert DNSType.NS == 2
        assert DNSType.CNAME == 5
        assert DNSType.SOA == 6
        assert DNSType.PTR == 12
        assert DNSType.MX == 15
        assert DNSType.TXT == 16
        assert DNSType.AAAA == 28
        assert DNSType.SRV == 33
        assert DNSType.ANY == 255

    def test_type_names_are_accessible(self):
        assert DNSType.TXT.name == "TXT"
        assert DNSType.A.name == "A"


class TestDNSClass:
    """Tests for DNS class enumeration."""

    def test_internet_class(self):
        assert DNSClass.IN == 1

    def test_any_class(self):
        assert DNSClass.ANY == 255


class TestDNSRCode:
    """Tests for DNS response codes."""

    def test_noerror(self):
        assert DNSRCode.NOERROR == 0

    def test_nxdomain(self):
        assert DNSRCode.NXDOMAIN == 3

    def test_refused(self):
        assert DNSRCode.REFUSED == 5


# =========================================================================
# DNS Header
# =========================================================================

class TestDNSHeader:
    """Tests for DNS message header encoding and decoding."""

    def test_default_header(self):
        header = DNSHeader()
        assert header.id == 0
        assert header.qr == 0
        assert header.opcode == 0
        assert header.aa == 0
        assert header.rcode == 0

    def test_to_flags_query(self):
        header = DNSHeader(qr=0, opcode=0, rd=1)
        flags = header.to_flags()
        assert flags == 0x0100  # RD bit set

    def test_to_flags_response(self):
        header = DNSHeader(qr=1, aa=1, rcode=0)
        flags = header.to_flags()
        assert (flags >> 15) & 1 == 1  # QR
        assert (flags >> 10) & 1 == 1  # AA
        assert flags & 0xF == 0  # RCODE

    def test_to_flags_nxdomain(self):
        header = DNSHeader(qr=1, aa=1, rcode=DNSRCode.NXDOMAIN)
        flags = header.to_flags()
        assert flags & 0xF == 3

    def test_from_flags_roundtrip(self):
        original = DNSHeader(id=0xABCD, qr=1, opcode=0, aa=1, tc=0, rd=1, ra=0, rcode=0,
                             qdcount=1, ancount=2, nscount=0, arcount=1)
        flags = original.to_flags()
        restored = DNSHeader.from_flags(0xABCD, flags, 1, 2, 0, 1)
        assert restored.id == original.id
        assert restored.qr == original.qr
        assert restored.aa == original.aa
        assert restored.rd == original.rd
        assert restored.qdcount == original.qdcount
        assert restored.ancount == original.ancount

    def test_opcode_encoding(self):
        header = DNSHeader(opcode=DNSOpcode.STATUS)
        flags = header.to_flags()
        assert (flags >> 11) & 0xF == 2

    def test_truncation_flag(self):
        header = DNSHeader(tc=1)
        flags = header.to_flags()
        assert (flags >> 9) & 1 == 1


# =========================================================================
# DNS Wire Format — Name Encoding
# =========================================================================

class TestDNSWireFormatNameEncoding:
    """Tests for DNS domain name encoding per RFC 1035."""

    def test_encode_simple_name(self):
        result = DNSWireFormat.encode_name("fizzbuzz.local.")
        assert result == b"\x08fizzbuzz\x05local\x00"

    def test_encode_name_without_trailing_dot(self):
        result = DNSWireFormat.encode_name("fizzbuzz.local")
        assert result == b"\x08fizzbuzz\x05local\x00"

    def test_encode_single_label(self):
        result = DNSWireFormat.encode_name("localhost.")
        assert result == b"\x09localhost\x00"

    def test_encode_root(self):
        result = DNSWireFormat.encode_name(".")
        assert result == b"\x00"

    def test_encode_empty_string(self):
        result = DNSWireFormat.encode_name("")
        assert result == b"\x00"

    def test_encode_subdomain(self):
        result = DNSWireFormat.encode_name("15.fizzbuzz.local.")
        expected = b"\x0215\x08fizzbuzz\x05local\x00"
        assert result == expected

    def test_label_length_in_first_byte(self):
        result = DNSWireFormat.encode_name("ab.cd.")
        assert result[0] == 2  # length of "ab"
        assert result[3] == 2  # length of "cd"

    def test_long_label_raises(self):
        long_label = "a" * 64
        with pytest.raises(ValueError, match="exceeds 63 bytes"):
            DNSWireFormat.encode_name(f"{long_label}.example.com.")


class TestDNSWireFormatNameDecoding:
    """Tests for DNS domain name decoding with compression support."""

    def test_decode_simple_name(self):
        data = b"\x08fizzbuzz\x05local\x00"
        name, offset = DNSWireFormat.decode_name(data, 0)
        assert name == "fizzbuzz.local."
        assert offset == len(data)

    def test_decode_name_with_compression_pointer(self):
        # Build a message with a name at offset 0, then a pointer at offset 16
        name_bytes = b"\x08fizzbuzz\x05local\x00"
        pointer = struct.pack("!H", 0xC000 | 0)  # pointer to offset 0
        data = name_bytes + pointer
        name, offset = DNSWireFormat.decode_name(data, len(name_bytes))
        assert name == "fizzbuzz.local."
        assert offset == len(data)

    def test_decode_returns_correct_offset(self):
        data = b"\x0215\x08fizzbuzz\x05local\x00EXTRADATA"
        name, offset = DNSWireFormat.decode_name(data, 0)
        assert name == "15.fizzbuzz.local."
        assert offset == 19  # past the null terminator

    def test_decode_root(self):
        data = b"\x00"
        name, offset = DNSWireFormat.decode_name(data, 0)
        assert name == "."
        assert offset == 1


class TestDNSWireFormatCompression:
    """Tests for DNS name compression encoding."""

    def test_compressed_name_reuses_suffix(self):
        buf = bytearray()
        table = {}

        # First name: fizzbuzz.local
        first = DNSWireFormat.encode_name_compressed("fizzbuzz.local", buf, table)
        buf += first

        # Second name: 15.fizzbuzz.local — should use pointer for fizzbuzz.local
        second = DNSWireFormat.encode_name_compressed("15.fizzbuzz.local", buf, table)

        # The second encoding should contain a pointer (shorter than full encoding)
        full_second = DNSWireFormat.encode_name("15.fizzbuzz.local")
        assert len(second) < len(full_second)

    def test_compression_table_populated(self):
        buf = bytearray()
        table = {}
        name_bytes = DNSWireFormat.encode_name_compressed("fizzbuzz.local", buf, table)
        buf += name_bytes

        assert "fizzbuzz.local" in table
        assert "local" in table


# =========================================================================
# DNS Wire Format — Full Message Encoding/Decoding
# =========================================================================

class TestDNSWireFormatMessage:
    """Tests for complete DNS message encoding and decoding."""

    def test_encode_decode_query_roundtrip(self):
        query = DNSMessage()
        query.header = DNSHeader(id=0x1234, qr=0, rd=1, qdcount=1)
        query.questions = [DNSQuestion(qname="15.fizzbuzz.local.", qtype=DNSType.TXT, qclass=DNSClass.IN)]

        wire = DNSWireFormat.encode_message(query)
        decoded = DNSWireFormat.decode_message(wire)

        assert decoded.header.id == 0x1234
        assert decoded.header.qr == 0
        assert decoded.header.rd == 1
        assert decoded.header.qdcount == 1
        assert len(decoded.questions) == 1
        assert decoded.questions[0].qname == "15.fizzbuzz.local."
        assert decoded.questions[0].qtype == DNSType.TXT

    def test_encode_decode_response_roundtrip(self):
        txt_rdata = TXTRecordBuilder.build("FizzBuzz")

        response = DNSMessage()
        response.header = DNSHeader(id=0x5678, qr=1, aa=1, qdcount=1, ancount=1)
        response.questions = [DNSQuestion(qname="15.fizzbuzz.local.", qtype=DNSType.TXT)]
        response.answers = [DNSResourceRecord(
            name="15.fizzbuzz.local.",
            rtype=DNSType.TXT,
            rclass=DNSClass.IN,
            ttl=3600,
            rdlength=len(txt_rdata),
            rdata=txt_rdata,
        )]

        wire = DNSWireFormat.encode_message(response)
        decoded = DNSWireFormat.decode_message(wire)

        assert decoded.header.id == 0x5678
        assert decoded.header.qr == 1
        assert decoded.header.aa == 1
        assert len(decoded.answers) == 1
        assert decoded.answers[0].rtype == DNSType.TXT

    def test_header_is_12_bytes(self):
        msg = DNSMessage()
        msg.header = DNSHeader(id=1)
        wire = DNSWireFormat.encode_message(msg)
        assert len(wire) == 12

    def test_decode_too_short_raises(self):
        with pytest.raises(ValueError, match="too short"):
            DNSWireFormat.decode_message(b"\x00" * 11)

    def test_encode_message_with_multiple_answers(self):
        msg = DNSMessage()
        msg.header = DNSHeader(id=42, qr=1, ancount=2)
        msg.answers = [
            DNSResourceRecord(name="1.fizzbuzz.local.", rtype=DNSType.TXT,
                              ttl=3600, rdlength=2, rdata=b"\x011"),
            DNSResourceRecord(name="3.fizzbuzz.local.", rtype=DNSType.TXT,
                              ttl=3600, rdlength=5, rdata=b"\x04Fizz"),
        ]

        wire = DNSWireFormat.encode_message(msg)
        decoded = DNSWireFormat.decode_message(wire)
        assert len(decoded.answers) == 2


# =========================================================================
# TXT Record Builder
# =========================================================================

class TestTXTRecordBuilder:
    """Tests for TXT record RDATA construction."""

    def test_simple_text(self):
        rdata = TXTRecordBuilder.build("FizzBuzz")
        assert rdata[0] == 8  # length prefix
        assert rdata[1:] == b"FizzBuzz"

    def test_empty_text(self):
        rdata = TXTRecordBuilder.build("")
        assert rdata == b"\x00"

    def test_long_text_splits_at_255(self):
        text = "A" * 300
        rdata = TXTRecordBuilder.build(text)
        assert rdata[0] == 255
        assert rdata[256] == 45  # remaining 300 - 255 = 45

    def test_build_multi(self):
        rdata = TXTRecordBuilder.build_multi(["v=spf1", "include:fizzbuzz.local"])
        assert rdata[0] == 6  # len("v=spf1")
        assert b"v=spf1" in rdata
        assert b"include:fizzbuzz.local" in rdata

    def test_build_multi_rejects_oversized_string(self):
        with pytest.raises(ValueError, match="exceeds 255"):
            TXTRecordBuilder.build_multi(["x" * 256])


# =========================================================================
# SOA Record Builder
# =========================================================================

class TestSOARecordBuilder:
    """Tests for SOA record RDATA construction."""

    def test_soa_contains_serial(self):
        rdata = SOARecordBuilder.build(
            "ns1.fizzbuzz.local.",
            "admin.fizzbuzz.local.",
            2024010100,
        )
        # The serial should be packed as a 32-bit unsigned int somewhere in the data
        assert struct.pack("!I", 2024010100) in rdata

    def test_soa_contains_mname(self):
        rdata = SOARecordBuilder.build(
            "ns1.fizzbuzz.local.",
            "admin.fizzbuzz.local.",
            1,
        )
        assert b"ns1" in rdata
        assert b"fizzbuzz" in rdata

    def test_soa_default_timers(self):
        rdata = SOARecordBuilder.build("ns1.", "admin.", 1)
        # Should contain default refresh=3600
        assert struct.pack("!I", 3600) in rdata


# =========================================================================
# Zone
# =========================================================================

class TestZone:
    """Tests for DNS zone record management and lookup."""

    def test_create_zone(self):
        zone = Zone("fizzbuzz.local.")
        assert zone.origin == "fizzbuzz.local."
        assert zone.record_count == 0

    def test_add_and_lookup_record(self):
        zone = Zone("example.com.")
        txt_rdata = TXTRecordBuilder.build("hello")
        zone.add_record(DNSResourceRecord(
            name="test.example.com.",
            rtype=DNSType.TXT,
            rclass=DNSClass.IN,
            ttl=3600,
            rdlength=len(txt_rdata),
            rdata=txt_rdata,
            rdata_parsed="hello",
        ))

        results = zone.lookup("test.example.com.", DNSType.TXT)
        assert len(results) == 1
        assert results[0].rdata_parsed == "hello"

    def test_lookup_case_insensitive(self):
        zone = Zone("example.com.")
        zone.add_record(DNSResourceRecord(
            name="Test.Example.COM.",
            rtype=DNSType.A,
            rdata=b"\x7f\x00\x00\x01",
            rdlength=4,
        ))

        results = zone.lookup("test.example.com.", DNSType.A)
        assert len(results) == 1

    def test_lookup_nonexistent_returns_empty(self):
        zone = Zone("example.com.")
        results = zone.lookup("missing.example.com.", DNSType.A)
        assert results == []

    def test_lookup_wrong_type_returns_empty(self):
        zone = Zone("example.com.")
        zone.add_record(DNSResourceRecord(
            name="test.example.com.",
            rtype=DNSType.TXT,
            rdata=b"\x02hi",
            rdlength=3,
        ))

        results = zone.lookup("test.example.com.", DNSType.A)
        assert results == []

    def test_lookup_any_returns_all_types(self):
        zone = Zone("example.com.")
        zone.add_record(DNSResourceRecord(
            name="test.example.com.", rtype=DNSType.TXT,
            rdata=b"\x02hi", rdlength=3, rdata_parsed="hi"))
        zone.add_record(DNSResourceRecord(
            name="test.example.com.", rtype=DNSType.A,
            rdata=b"\x7f\x00\x00\x01", rdlength=4, rdata_parsed="127.0.0.1"))

        results = zone.lookup("test.example.com.", DNSType.ANY)
        assert len(results) == 2

    def test_wildcard_matching(self):
        zone = Zone("example.com.")
        zone.add_record(DNSResourceRecord(
            name="*.example.com.",
            rtype=DNSType.TXT,
            rdata=b"\x08wildcard",
            rdlength=9,
            rdata_parsed="wildcard",
        ))

        results = zone.lookup("anything.example.com.", DNSType.TXT)
        assert len(results) == 1
        assert results[0].rdata_parsed == "wildcard"
        # Wildcard match returns the queried name, not the wildcard
        assert results[0].name == "anything.example.com."

    def test_exact_match_takes_priority_over_wildcard(self):
        zone = Zone("example.com.")
        zone.add_record(DNSResourceRecord(
            name="*.example.com.", rtype=DNSType.TXT,
            rdata=b"\x08wildcard", rdlength=9, rdata_parsed="wildcard"))
        zone.add_record(DNSResourceRecord(
            name="specific.example.com.", rtype=DNSType.TXT,
            rdata=b"\x08specific", rdlength=9, rdata_parsed="specific"))

        results = zone.lookup("specific.example.com.", DNSType.TXT)
        assert len(results) == 1
        assert results[0].rdata_parsed == "specific"

    def test_is_authoritative_for(self):
        zone = Zone("fizzbuzz.local.")
        assert zone.is_authoritative_for("15.fizzbuzz.local.")
        assert zone.is_authoritative_for("fizzbuzz.local.")
        assert not zone.is_authoritative_for("other.local.")

    def test_record_count(self):
        zone = Zone("example.com.")
        zone.add_record(DNSResourceRecord(name="a.example.com.", rtype=DNSType.A,
                                          rdata=b"\x01\x02\x03\x04", rdlength=4))
        zone.add_record(DNSResourceRecord(name="b.example.com.", rtype=DNSType.A,
                                          rdata=b"\x01\x02\x03\x05", rdlength=4))
        assert zone.record_count == 2

    def test_get_ns_records(self):
        zone = Zone("example.com.")
        ns_rdata = DNSWireFormat.encode_name("ns1.example.com.")
        zone.add_record(DNSResourceRecord(
            name="example.com.", rtype=DNSType.NS,
            rdata=ns_rdata, rdlength=len(ns_rdata)))
        assert len(zone.get_ns_records()) == 1

    def test_soa_record_stored(self):
        zone = Zone("example.com.")
        soa_rdata = SOARecordBuilder.build("ns1.", "admin.", 1)
        zone.add_record(DNSResourceRecord(
            name="example.com.", rtype=DNSType.SOA,
            rdata=soa_rdata, rdlength=len(soa_rdata)))
        assert zone.soa is not None

    def test_origin_auto_appends_dot(self):
        zone = Zone("example.com")
        assert zone.origin == "example.com."


# =========================================================================
# Zone File Parser
# =========================================================================

class TestZoneFile:
    """Tests for BIND-style zone file parsing."""

    def test_parse_simple_zone(self):
        content = """
$ORIGIN example.com.
$TTL 3600
@ IN SOA ns1.example.com. admin.example.com. 1 3600 900 86400 300
@ IN NS ns1.example.com.
www IN A 1.2.3.4
"""
        zone = ZoneFile.parse(content)
        assert zone.origin == "example.com."
        assert zone.soa is not None

        results = zone.lookup("www.example.com.", DNSType.A)
        assert len(results) == 1
        assert results[0].rdata_parsed == "1.2.3.4"

    def test_parse_txt_record(self):
        content = """
$ORIGIN fizzbuzz.local.
$TTL 3600
15 IN TXT "FizzBuzz"
"""
        zone = ZoneFile.parse(content)
        results = zone.lookup("15.fizzbuzz.local.", DNSType.TXT)
        assert len(results) == 1
        assert results[0].rdata_parsed == "FizzBuzz"

    def test_parse_continuation_lines(self):
        content = """
$ORIGIN example.com.
$TTL 3600
@ IN SOA ns1.example.com. admin.example.com. (
    2024010100
    3600
    900
    86400
    300
)
"""
        zone = ZoneFile.parse(content)
        assert zone.soa is not None

    def test_parse_comments_stripped(self):
        content = """
$ORIGIN example.com.
; This is a comment
$TTL 3600  ; inline comment
www IN A 10.0.0.1  ; another comment
"""
        zone = ZoneFile.parse(content)
        results = zone.lookup("www.example.com.", DNSType.A)
        assert len(results) == 1

    def test_parse_with_explicit_origin(self):
        content = """
www IN A 192.168.1.1
"""
        zone = ZoneFile.parse(content, origin="test.local.")
        assert zone.origin == "test.local."

    def test_parse_mx_record(self):
        content = """
$ORIGIN example.com.
@ IN MX 10 mail.example.com.
"""
        zone = ZoneFile.parse(content)
        results = zone.lookup("example.com.", DNSType.MX)
        assert len(results) == 1
        assert "10" in results[0].rdata_parsed

    def test_parse_cname_record(self):
        content = """
$ORIGIN example.com.
alias IN CNAME www.example.com.
"""
        zone = ZoneFile.parse(content)
        results = zone.lookup("alias.example.com.", DNSType.CNAME)
        assert len(results) == 1


# =========================================================================
# FizzBuzz Zone
# =========================================================================

class TestFizzBuzzZone:
    """Tests for the pre-built fizzbuzz.local zone."""

    def test_zone_origin(self):
        zone = FizzBuzzZone.build()
        assert zone.origin == "fizzbuzz.local."

    def test_zone_has_soa(self):
        zone = FizzBuzzZone.build()
        assert zone.soa is not None
        assert zone.soa.rtype == DNSType.SOA

    def test_zone_has_ns(self):
        zone = FizzBuzzZone.build()
        ns = zone.get_ns_records()
        assert len(ns) >= 1

    def test_zone_has_ns1_a_record(self):
        zone = FizzBuzzZone.build()
        results = zone.lookup("ns1.fizzbuzz.local.", DNSType.A)
        assert len(results) == 1
        assert results[0].rdata_parsed == "127.0.0.1"

    def test_15_returns_fizzbuzz(self):
        zone = FizzBuzzZone.build()
        results = zone.lookup("15.fizzbuzz.local.", DNSType.TXT)
        assert len(results) >= 1
        assert results[0].rdata_parsed == "FizzBuzz"

    def test_3_returns_fizz(self):
        zone = FizzBuzzZone.build()
        results = zone.lookup("3.fizzbuzz.local.", DNSType.TXT)
        assert len(results) >= 1
        assert results[0].rdata_parsed == "Fizz"

    def test_5_returns_buzz(self):
        zone = FizzBuzzZone.build()
        results = zone.lookup("5.fizzbuzz.local.", DNSType.TXT)
        assert len(results) >= 1
        assert results[0].rdata_parsed == "Buzz"

    def test_1_returns_number(self):
        zone = FizzBuzzZone.build()
        results = zone.lookup("1.fizzbuzz.local.", DNSType.TXT)
        assert len(results) >= 1
        assert results[0].rdata_parsed == "1"

    def test_30_returns_fizzbuzz(self):
        zone = FizzBuzzZone.build()
        results = zone.lookup("30.fizzbuzz.local.", DNSType.TXT)
        assert len(results) >= 1
        assert results[0].rdata_parsed == "FizzBuzz"

    def test_100_returns_buzz(self):
        zone = FizzBuzzZone.build()
        results = zone.lookup("100.fizzbuzz.local.", DNSType.TXT)
        assert len(results) >= 1
        assert results[0].rdata_parsed == "Buzz"

    def test_all_100_numbers_registered(self):
        zone = FizzBuzzZone.build()
        for n in range(1, 101):
            results = zone.lookup(f"{n}.fizzbuzz.local.", DNSType.TXT)
            assert len(results) >= 1, f"Missing TXT record for {n}.fizzbuzz.local"

    def test_custom_range(self):
        zone = FizzBuzzZone.build(range_start=1, range_end=10)
        results = zone.lookup("10.fizzbuzz.local.", DNSType.TXT)
        assert len(results) >= 1
        assert results[0].rdata_parsed == "Buzz"

        # 11 should not exist
        results = zone.lookup("11.fizzbuzz.local.", DNSType.TXT)
        assert len(results) == 0

    def test_generate_zone_file(self):
        text = FizzBuzzZone.generate_zone_file(range_start=1, range_end=5)
        assert "$ORIGIN fizzbuzz.local." in text
        assert '$TTL 3600' in text
        assert '1 IN TXT "1"' in text
        assert '3 IN TXT "Fizz"' in text
        assert '5 IN TXT "Buzz"' in text

    def test_record_count_includes_infrastructure(self):
        zone = FizzBuzzZone.build(1, 10)
        # 10 TXT records + 1 SOA + 1 NS + 1 A = 13
        assert zone.record_count == 13


# =========================================================================
# Classify Number Helper
# =========================================================================

class TestClassifyNumber:
    """Tests for the internal classification function."""

    def test_fizz(self):
        assert _classify_number(3) == "Fizz"
        assert _classify_number(9) == "Fizz"

    def test_buzz(self):
        assert _classify_number(5) == "Buzz"
        assert _classify_number(10) == "Buzz"

    def test_fizzbuzz(self):
        assert _classify_number(15) == "FizzBuzz"
        assert _classify_number(30) == "FizzBuzz"
        assert _classify_number(45) == "FizzBuzz"

    def test_number(self):
        assert _classify_number(1) == "1"
        assert _classify_number(7) == "7"


# =========================================================================
# DNS Resolver
# =========================================================================

class TestDNSResolver:
    """Tests for DNS query resolution against zones."""

    @pytest.fixture
    def resolver(self):
        zone = FizzBuzzZone.build()
        r = DNSResolver()
        r.add_zone(zone)
        return r

    def test_resolve_txt_query(self, resolver):
        query = DNSMessage()
        query.header = DNSHeader(id=1, qr=0, rd=1, qdcount=1)
        query.questions = [DNSQuestion(qname="15.fizzbuzz.local.", qtype=DNSType.TXT)]

        response = resolver.resolve(query)
        assert response.header.qr == 1
        assert response.header.aa == 1
        assert response.header.rcode == DNSRCode.NOERROR
        assert len(response.answers) >= 1
        assert response.answers[0].rdata_parsed == "FizzBuzz"

    def test_resolve_nxdomain(self, resolver):
        query = DNSMessage()
        query.header = DNSHeader(id=2, qr=0, rd=1, qdcount=1)
        query.questions = [DNSQuestion(qname="999.fizzbuzz.local.", qtype=DNSType.TXT)]

        response = resolver.resolve(query)
        assert response.header.rcode == DNSRCode.NXDOMAIN

    def test_resolve_refused_for_unknown_zone(self, resolver):
        query = DNSMessage()
        query.header = DNSHeader(id=3, qr=0, rd=1, qdcount=1)
        query.questions = [DNSQuestion(qname="example.com.", qtype=DNSType.A)]

        response = resolver.resolve(query)
        assert response.header.rcode == DNSRCode.REFUSED

    def test_resolve_preserves_query_id(self, resolver):
        query = DNSMessage()
        query.header = DNSHeader(id=0xBEEF, qr=0, qdcount=1)
        query.questions = [DNSQuestion(qname="3.fizzbuzz.local.", qtype=DNSType.TXT)]

        response = resolver.resolve(query)
        assert response.header.id == 0xBEEF

    def test_resolve_simple_interface(self, resolver):
        result = resolver.resolve_simple("15.fizzbuzz.local.", "TXT")
        assert result == "FizzBuzz"

    def test_resolve_simple_nxdomain(self, resolver):
        result = resolver.resolve_simple("nonexistent.fizzbuzz.local.", "TXT")
        assert result is None

    def test_stats_tracking(self, resolver):
        resolver.resolve_simple("1.fizzbuzz.local.", "TXT")
        resolver.resolve_simple("2.fizzbuzz.local.", "TXT")
        resolver.resolve_simple("999.fizzbuzz.local.", "TXT")

        stats = resolver.stats
        assert stats["total_queries"] == 3
        assert stats["noerror"] == 2
        assert stats["nxdomain"] == 1

    def test_type_stats(self, resolver):
        resolver.resolve_simple("1.fizzbuzz.local.", "TXT")
        resolver.resolve_simple("ns1.fizzbuzz.local.", "A")

        stats = resolver.stats
        assert stats["type_breakdown"]["TXT"] >= 1
        assert stats["type_breakdown"]["A"] >= 1

    def test_authority_section_on_nxdomain(self, resolver):
        query = DNSMessage()
        query.header = DNSHeader(id=1, qdcount=1)
        query.questions = [DNSQuestion(qname="999.fizzbuzz.local.", qtype=DNSType.TXT)]

        response = resolver.resolve(query)
        # Should include SOA in authority section
        assert any(rr.rtype == DNSType.SOA for rr in response.authority)


# =========================================================================
# Negative Cache
# =========================================================================

class TestNegativeCache:
    """Tests for NSEC-style authenticated denial of existence cache."""

    def test_put_and_get(self):
        cache = NegativeCache()
        cache.put("missing.fizzbuzz.local.", DNSType.TXT, DNSRCode.NXDOMAIN)
        entry = cache.get("missing.fizzbuzz.local.", DNSType.TXT)
        assert entry is not None
        assert entry.rcode == DNSRCode.NXDOMAIN

    def test_miss_returns_none(self):
        cache = NegativeCache()
        assert cache.get("nothing.local.", DNSType.A) is None

    def test_expired_entry_removed(self):
        cache = NegativeCache(default_neg_ttl=0)
        cache.put("expired.local.", DNSType.TXT, DNSRCode.NXDOMAIN, ttl=0)
        # Entry should be immediately expired
        time.sleep(0.01)
        assert cache.get("expired.local.", DNSType.TXT) is None

    def test_max_entries_eviction(self):
        cache = NegativeCache(max_entries=2)
        cache.put("a.local.", DNSType.A, DNSRCode.NXDOMAIN)
        cache.put("b.local.", DNSType.A, DNSRCode.NXDOMAIN)
        cache.put("c.local.", DNSType.A, DNSRCode.NXDOMAIN)
        assert cache.size <= 2

    def test_hit_count_tracked(self):
        cache = NegativeCache()
        cache.put("test.local.", DNSType.TXT, DNSRCode.NXDOMAIN)
        cache.get("test.local.", DNSType.TXT)
        cache.get("test.local.", DNSType.TXT)
        entry = cache.get("test.local.", DNSType.TXT)
        assert entry.hit_count == 3

    def test_stats(self):
        cache = NegativeCache(max_entries=100)
        cache.put("a.local.", DNSType.A, DNSRCode.NXDOMAIN)
        cache.get("a.local.", DNSType.A)  # hit
        cache.get("b.local.", DNSType.A)  # miss

        stats = cache.stats
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["size"] == 1
        assert stats["hit_rate"] == 50.0

    def test_clear(self):
        cache = NegativeCache()
        cache.put("a.local.", DNSType.A, DNSRCode.NXDOMAIN)
        cache.clear()
        assert cache.size == 0

    def test_nsec_neighbors(self):
        cache = NegativeCache()
        zone_names = ["1.fizzbuzz.local.", "2.fizzbuzz.local.", "4.fizzbuzz.local."]
        cache.put("3.fizzbuzz.local.", DNSType.TXT, DNSRCode.NXDOMAIN,
                  zone_names=zone_names)
        entry = cache.get("3.fizzbuzz.local.", DNSType.TXT)
        assert entry is not None
        assert entry.nsec_prev == "2.fizzbuzz.local."
        assert entry.nsec_next == "4.fizzbuzz.local."


# =========================================================================
# DNS Dashboard
# =========================================================================

class TestDNSDashboard:
    """Tests for ASCII dashboard rendering."""

    def test_dashboard_renders_without_error(self):
        zone = FizzBuzzZone.build(1, 5)
        resolver = DNSResolver()
        resolver.add_zone(zone)

        output = DNSDashboard.render(resolver)
        assert "FizzDNS" in output
        assert "fizzbuzz.local." in output

    def test_dashboard_shows_query_stats(self):
        zone = FizzBuzzZone.build(1, 5)
        resolver = DNSResolver()
        resolver.add_zone(zone)
        resolver.resolve_simple("3.fizzbuzz.local.", "TXT")

        output = DNSDashboard.render(resolver)
        assert "Total Queries" in output

    def test_dashboard_with_negative_cache(self):
        resolver = DNSResolver()
        resolver.add_zone(FizzBuzzZone.build(1, 5))
        neg_cache = NegativeCache()
        neg_cache.put("999.fizzbuzz.local.", DNSType.TXT, DNSRCode.NXDOMAIN)

        output = DNSDashboard.render(resolver, negative_cache=neg_cache)
        assert "Negative Cache" in output

    def test_dashboard_respects_width(self):
        resolver = DNSResolver()
        resolver.add_zone(FizzBuzzZone.build(1, 3))

        output = DNSDashboard.render(resolver, width=80)
        for line in output.split("\n"):
            assert len(line) <= 80


# =========================================================================
# DNS Query Formatter
# =========================================================================

class TestDNSQueryFormatter:
    """Tests for dig-style query output formatting."""

    def test_format_response_includes_header(self):
        response = DNSMessage()
        response.header = DNSHeader(id=1, qr=1, aa=1, ancount=1, qdcount=1)
        response.questions = [DNSQuestion(qname="15.fizzbuzz.local.", qtype=DNSType.TXT)]
        txt_rdata = TXTRecordBuilder.build("FizzBuzz")
        response.answers = [DNSResourceRecord(
            name="15.fizzbuzz.local.", rtype=DNSType.TXT,
            ttl=3600, rdlength=len(txt_rdata), rdata=txt_rdata,
            rdata_parsed="FizzBuzz",
        )]

        output = DNSQueryFormatter.format_response(response)
        assert "HEADER" in output
        assert "NOERROR" in output
        assert "aa" in output

    def test_format_response_includes_answer(self):
        response = DNSMessage()
        response.header = DNSHeader(id=1, qr=1, aa=1, ancount=1)
        txt_rdata = TXTRecordBuilder.build("FizzBuzz")
        response.answers = [DNSResourceRecord(
            name="15.fizzbuzz.local.", rtype=DNSType.TXT,
            ttl=3600, rdlength=len(txt_rdata), rdata=txt_rdata,
            rdata_parsed="FizzBuzz",
        )]

        output = DNSQueryFormatter.format_response(response)
        assert "ANSWER SECTION" in output
        assert '"FizzBuzz"' in output

    def test_format_nxdomain(self):
        response = DNSMessage()
        response.header = DNSHeader(id=1, qr=1, aa=1, rcode=DNSRCode.NXDOMAIN, qdcount=1)
        response.questions = [DNSQuestion(qname="999.fizzbuzz.local.", qtype=DNSType.TXT)]

        output = DNSQueryFormatter.format_response(response)
        assert "NXDOMAIN" in output


# =========================================================================
# DNS Middleware
# =========================================================================

class TestDNSMiddleware:
    """Tests for the DNS middleware that registers results as DNS records."""

    @pytest.fixture
    def dns_components(self):
        zone = FizzBuzzZone.build(1, 100)
        resolver = DNSResolver()
        resolver.add_zone(zone)
        middleware = DNSMiddleware(zone, resolver)
        return zone, resolver, middleware

    def test_get_name(self, dns_components):
        _, _, middleware = dns_components
        assert middleware.get_name() == "DNSMiddleware"

    def test_records_updated_starts_at_zero(self, dns_components):
        _, _, middleware = dns_components
        assert middleware.records_updated == 0


# =========================================================================
# Integration: create_dns_subsystem
# =========================================================================

class TestCreateDNSSubsystem:
    """Tests for the subsystem factory function."""

    def test_creates_all_components(self):
        zone, resolver, neg_cache, middleware = create_dns_subsystem()
        assert zone is not None
        assert resolver is not None
        assert neg_cache is not None
        assert middleware is not None

    def test_zone_is_populated(self):
        zone, _, _, _ = create_dns_subsystem()
        assert zone.record_count > 100  # 100 TXT + SOA + NS + A

    def test_resolver_can_query(self):
        _, resolver, _, _ = create_dns_subsystem()
        result = resolver.resolve_simple("15.fizzbuzz.local.", "TXT")
        assert result == "FizzBuzz"

    def test_custom_range(self):
        zone, resolver, _, _ = create_dns_subsystem(range_start=1, range_end=50)
        assert resolver.resolve_simple("50.fizzbuzz.local.", "TXT") is not None
        assert resolver.resolve_simple("51.fizzbuzz.local.", "TXT") is None

    def test_negative_cache_params(self):
        _, _, neg_cache, _ = create_dns_subsystem(neg_cache_size=500, neg_cache_ttl=120)
        assert neg_cache.max_entries == 500
        assert neg_cache.default_neg_ttl == 120


# =========================================================================
# Wire Format RDATA Parsing
# =========================================================================

class TestRDATAParsing:
    """Tests for RDATA type-specific parsing during decode."""

    def test_parse_a_record(self):
        result = DNSWireFormat._parse_rdata(DNSType.A, b"\xc0\xa8\x01\x01", b"")
        assert result == "192.168.1.1"

    def test_parse_txt_record(self):
        rdata = TXTRecordBuilder.build("FizzBuzz")
        result = DNSWireFormat._parse_rdata(DNSType.TXT, rdata, b"")
        assert result == "FizzBuzz"

    def test_parse_aaaa_record(self):
        rdata = b"\x00\x01" * 8  # 0001:0001:0001:0001:0001:0001:0001:0001
        result = DNSWireFormat._parse_rdata(DNSType.AAAA, rdata, b"")
        assert "0001" in result

    def test_parse_unknown_type_returns_hex(self):
        result = DNSWireFormat._parse_rdata(999, b"\xab\xcd", b"")
        assert result == "abcd"


# =========================================================================
# End-to-End: dig simulation
# =========================================================================

class TestEndToEnd:
    """End-to-end tests simulating DNS query/response flow."""

    def test_dig_15_fizzbuzz_local_txt(self):
        """Simulate: dig 15.fizzbuzz.local TXT"""
        zone, resolver, _, _ = create_dns_subsystem()

        # Build query
        query = DNSMessage()
        query.header = DNSHeader(id=0xFACE, qr=0, rd=1, qdcount=1)
        query.questions = [DNSQuestion(
            qname="15.fizzbuzz.local.",
            qtype=DNSType.TXT,
            qclass=DNSClass.IN,
        )]

        # Encode to wire format
        wire_query = DNSWireFormat.encode_message(query)

        # Decode (simulating network receive)
        decoded_query = DNSWireFormat.decode_message(wire_query)

        # Resolve
        response = resolver.resolve(decoded_query)

        # Encode response
        wire_response = DNSWireFormat.encode_message(response)

        # Decode response
        decoded_response = DNSWireFormat.decode_message(wire_response)

        # Verify
        assert decoded_response.header.id == 0xFACE
        assert decoded_response.header.qr == 1
        assert decoded_response.header.aa == 1
        assert decoded_response.header.rcode == DNSRCode.NOERROR
        assert len(decoded_response.answers) >= 1

        # The TXT RDATA should decode to "FizzBuzz"
        txt_answer = decoded_response.answers[0]
        assert txt_answer.rtype == DNSType.TXT
        assert txt_answer.rdata_parsed == "FizzBuzz"

    def test_full_wire_roundtrip_for_multiple_queries(self):
        """Verify wire format correctness for a range of FizzBuzz lookups."""
        _, resolver, _, _ = create_dns_subsystem(range_start=1, range_end=30)

        test_cases = {
            1: "1", 3: "Fizz", 5: "Buzz", 15: "FizzBuzz",
            7: "7", 30: "FizzBuzz", 9: "Fizz", 20: "Buzz",
        }

        for number, expected in test_cases.items():
            qname = f"{number}.fizzbuzz.local."
            query = DNSMessage()
            query.header = DNSHeader(id=number, qr=0, rd=1, qdcount=1)
            query.questions = [DNSQuestion(qname=qname, qtype=DNSType.TXT)]

            wire = DNSWireFormat.encode_message(query)
            decoded_query = DNSWireFormat.decode_message(wire)
            response = resolver.resolve(decoded_query)

            assert response.header.rcode == DNSRCode.NOERROR, f"Failed for {number}"
            assert len(response.answers) >= 1, f"No answers for {number}"
            assert response.answers[0].rdata_parsed == expected, (
                f"Expected '{expected}' for {number}, got '{response.answers[0].rdata_parsed}'"
            )
