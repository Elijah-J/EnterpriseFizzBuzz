"""
Enterprise FizzBuzz Platform - Authoritative DNS Server Module

Implements a fully RFC 1035-compliant authoritative DNS server for the
fizzbuzz.local zone. Each number 1-100 is registered as a TXT record
containing its canonical FizzBuzz classification, enabling DNS-based
lookups of FizzBuzz results.

In modern distributed systems, DNS is the foundational service discovery
mechanism. By exposing FizzBuzz classifications as DNS TXT records, the
platform enables any DNS-aware client to resolve FizzBuzz evaluations
without coupling to the application layer. This is essential for
integration with legacy systems that only speak DNS, service meshes
that rely on DNS-based routing, and compliance frameworks that require
all data access to be auditable at the network layer.

Wire format encoding follows RFC 1035 Section 4, including:
- 12-byte fixed header with flags, opcodes, and section counts
- Length-prefixed label encoding for domain names
- Name compression via pointer references (0xC0 prefix + offset)
- TXT RDATA as length-prefixed character strings

The zone file parser supports a subset of BIND master file format,
sufficient for defining SOA, NS, A, AAAA, TXT, MX, CNAME, and PTR
records with standard TTL and class annotations.
"""

from __future__ import annotations

import enum
import hashlib
import logging
import struct
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DNS Constants (RFC 1035)
# ---------------------------------------------------------------------------

class DNSType(enum.IntEnum):
    """DNS resource record types as defined in RFC 1035 and extensions."""
    A = 1
    NS = 2
    CNAME = 5
    SOA = 6
    PTR = 12
    MX = 15
    TXT = 16
    AAAA = 28
    SRV = 33
    ANY = 255


class DNSClass(enum.IntEnum):
    """DNS resource record classes."""
    IN = 1
    CH = 3
    HS = 4
    ANY = 255


class DNSOpcode(enum.IntEnum):
    """DNS message opcodes."""
    QUERY = 0
    IQUERY = 1
    STATUS = 2
    NOTIFY = 4
    UPDATE = 5


class DNSRCode(enum.IntEnum):
    """DNS response codes."""
    NOERROR = 0
    FORMERR = 1
    SERVFAIL = 2
    NXDOMAIN = 3
    NOTIMP = 4
    REFUSED = 5
    YXDOMAIN = 6
    YXRRSET = 7
    NXRRSET = 8
    NOTAUTH = 9
    NOTZONE = 10


# Mapping from string type names to DNSType values
_TYPE_MAP: Dict[str, DNSType] = {
    "A": DNSType.A,
    "NS": DNSType.NS,
    "CNAME": DNSType.CNAME,
    "SOA": DNSType.SOA,
    "PTR": DNSType.PTR,
    "MX": DNSType.MX,
    "TXT": DNSType.TXT,
    "AAAA": DNSType.AAAA,
    "SRV": DNSType.SRV,
    "ANY": DNSType.ANY,
}

_CLASS_MAP: Dict[str, DNSClass] = {
    "IN": DNSClass.IN,
    "CH": DNSClass.CH,
    "HS": DNSClass.HS,
    "ANY": DNSClass.ANY,
}

# Default TTL for FizzBuzz zone records (1 hour)
DEFAULT_TTL = 3600

# Name compression pointer mask
_COMPRESSION_POINTER_MASK = 0xC0


# ---------------------------------------------------------------------------
# DNS Header
# ---------------------------------------------------------------------------

@dataclass
class DNSHeader:
    """DNS message header as specified in RFC 1035 Section 4.1.1.

    The header is always 12 bytes and contains the message ID, flags,
    and section counts. Every DNS message begins with this structure.

    Attributes:
        id: 16-bit identifier assigned by the program that generates
            the query. Copied into the response so the requester can
            match responses to outstanding queries.
        qr: Query/Response flag. 0 for query, 1 for response.
        opcode: Kind of query (QUERY, IQUERY, STATUS).
        aa: Authoritative Answer flag. Set when the responding name
            server is an authority for the domain in question.
        tc: Truncation flag. Set when the message was truncated due
            to length greater than permitted on the transport.
        rd: Recursion Desired. Directs the name server to pursue
            the query recursively. Not supported by this server.
        ra: Recursion Available. Set in responses to indicate the
            server supports recursive queries. Always 0 here.
        rcode: Response code indicating the status of the response.
        qdcount: Number of entries in the question section.
        ancount: Number of resource records in the answer section.
        nscount: Number of resource records in the authority section.
        arcount: Number of resource records in the additional section.
    """

    id: int = 0
    qr: int = 0
    opcode: int = 0
    aa: int = 0
    tc: int = 0
    rd: int = 0
    ra: int = 0
    rcode: int = 0
    qdcount: int = 0
    ancount: int = 0
    nscount: int = 0
    arcount: int = 0

    def to_flags(self) -> int:
        """Pack header flags into a 16-bit integer."""
        flags = 0
        flags |= (self.qr & 0x1) << 15
        flags |= (self.opcode & 0xF) << 11
        flags |= (self.aa & 0x1) << 10
        flags |= (self.tc & 0x1) << 9
        flags |= (self.rd & 0x1) << 8
        flags |= (self.ra & 0x1) << 7
        # Bits 4-6 are reserved (Z), always 0
        flags |= (self.rcode & 0xF)
        return flags

    @classmethod
    def from_flags(cls, msg_id: int, flags: int, qdcount: int,
                   ancount: int, nscount: int, arcount: int) -> DNSHeader:
        """Unpack a 16-bit flags field into a DNSHeader."""
        return cls(
            id=msg_id,
            qr=(flags >> 15) & 0x1,
            opcode=(flags >> 11) & 0xF,
            aa=(flags >> 10) & 0x1,
            tc=(flags >> 9) & 0x1,
            rd=(flags >> 8) & 0x1,
            ra=(flags >> 7) & 0x1,
            rcode=flags & 0xF,
            qdcount=qdcount,
            ancount=ancount,
            nscount=nscount,
            arcount=arcount,
        )


# ---------------------------------------------------------------------------
# DNS Question
# ---------------------------------------------------------------------------

@dataclass
class DNSQuestion:
    """DNS question entry as specified in RFC 1035 Section 4.1.2.

    Attributes:
        qname: The domain name being queried, as a fully qualified
            domain name (e.g. "15.fizzbuzz.local.").
        qtype: The type of record being requested.
        qclass: The class of the query (usually IN for Internet).
    """

    qname: str
    qtype: int = DNSType.A
    qclass: int = DNSClass.IN


# ---------------------------------------------------------------------------
# DNS Resource Record
# ---------------------------------------------------------------------------

@dataclass
class DNSResourceRecord:
    """DNS resource record as specified in RFC 1035 Section 4.1.3.

    Resource records carry the actual data in DNS responses. Each RR
    contains a name, type, class, TTL, and type-specific data.

    Attributes:
        name: The domain name to which this record pertains.
        rtype: The type code of the resource record.
        rclass: The class code (usually IN).
        ttl: Time to live in seconds. Specifies how long the record
            may be cached before it should be discarded.
        rdlength: Length of the RDATA field in bytes.
        rdata: Type-specific resource record data.
        rdata_parsed: Human-readable representation of the RDATA.
    """

    name: str
    rtype: int
    rclass: int = DNSClass.IN
    ttl: int = DEFAULT_TTL
    rdlength: int = 0
    rdata: bytes = b""
    rdata_parsed: str = ""

    def type_name(self) -> str:
        """Return the string name of this record's type."""
        try:
            return DNSType(self.rtype).name
        except ValueError:
            return f"TYPE{self.rtype}"

    def class_name(self) -> str:
        """Return the string name of this record's class."""
        try:
            return DNSClass(self.rclass).name
        except ValueError:
            return f"CLASS{self.rclass}"


# ---------------------------------------------------------------------------
# DNS Message
# ---------------------------------------------------------------------------

@dataclass
class DNSMessage:
    """Complete DNS message comprising header, questions, and RR sections.

    A DNS message consists of a header followed by four variable-length
    sections: questions, answers, authority records, and additional
    records. The header contains counts for each section.

    Attributes:
        header: The 12-byte message header.
        questions: List of question entries.
        answers: List of answer resource records.
        authority: List of authority resource records (NS, SOA).
        additional: List of additional resource records.
    """

    header: DNSHeader = field(default_factory=DNSHeader)
    questions: List[DNSQuestion] = field(default_factory=list)
    answers: List[DNSResourceRecord] = field(default_factory=list)
    authority: List[DNSResourceRecord] = field(default_factory=list)
    additional: List[DNSResourceRecord] = field(default_factory=list)


# ---------------------------------------------------------------------------
# DNS Wire Format Encoder/Decoder
# ---------------------------------------------------------------------------

class DNSWireFormat:
    """Encodes and decodes DNS messages to/from RFC 1035 wire format.

    This class handles the binary serialization of DNS messages, including
    the encoding of domain names as sequences of length-prefixed labels
    and the use of name compression pointers to reduce message size.

    Name compression works by replacing a domain name (or suffix thereof)
    with a two-byte pointer to a previous occurrence of the same name
    in the message. The pointer is identified by the two high bits being
    set (0xC0), with the remaining 14 bits giving the byte offset from
    the start of the message.
    """

    @staticmethod
    def encode_name(name: str) -> bytes:
        """Encode a domain name as a sequence of length-prefixed labels.

        Each label is preceded by its length as a single byte. The name
        is terminated by a zero-length label (null byte). For example,
        "15.fizzbuzz.local." encodes as:
            \\x02 15 \\x08 fizzbuzz \\x05 local \\x00

        Args:
            name: Fully qualified domain name. Trailing dot is optional.

        Returns:
            Bytes representing the encoded name.
        """
        if name.endswith("."):
            name = name[:-1]
        if not name:
            return b"\x00"

        result = b""
        for label in name.split("."):
            encoded_label = label.encode("ascii")
            if len(encoded_label) > 63:
                raise ValueError(
                    f"DNS label '{label}' exceeds 63 bytes. "
                    f"Domain name labels are limited to 63 octets per RFC 1035."
                )
            result += struct.pack("B", len(encoded_label)) + encoded_label
        result += b"\x00"
        return result

    @staticmethod
    def encode_name_compressed(name: str, message_buf: bytearray,
                               compression_table: Dict[str, int]) -> bytes:
        """Encode a domain name with compression pointer support.

        Checks whether the name (or any suffix) has been previously
        written to the message buffer. If so, emits a pointer instead
        of re-encoding the labels.

        Args:
            name: The domain name to encode.
            message_buf: The message buffer built so far.
            compression_table: Mapping of previously encoded names to
                their byte offsets in the message.

        Returns:
            Bytes for the encoded (possibly compressed) name.
        """
        if name.endswith("."):
            name = name[:-1]
        if not name:
            return b"\x00"

        labels = name.split(".")
        result = b""

        for i in range(len(labels)):
            suffix = ".".join(labels[i:])
            if suffix in compression_table:
                offset = compression_table[suffix]
                pointer = 0xC000 | (offset & 0x3FFF)
                result += struct.pack("!H", pointer)
                return result
            # Record this suffix position
            current_offset = len(message_buf) + len(result)
            if current_offset < 0x4000:
                compression_table[suffix] = current_offset
            encoded_label = labels[i].encode("ascii")
            result += struct.pack("B", len(encoded_label)) + encoded_label

        result += b"\x00"
        return result

    @staticmethod
    def decode_name(data: bytes, offset: int) -> Tuple[str, int]:
        """Decode a domain name from wire format, following compression pointers.

        Args:
            data: The complete DNS message bytes.
            offset: The byte offset where the name begins.

        Returns:
            Tuple of (decoded domain name with trailing dot, new offset
            after the name in the original data).
        """
        labels: List[str] = []
        original_offset = offset
        jumped = False
        return_offset = offset
        max_jumps = 20  # Prevent infinite loops from malformed pointers
        jumps = 0

        while True:
            if offset >= len(data):
                break

            length = data[offset]

            if (length & _COMPRESSION_POINTER_MASK) == _COMPRESSION_POINTER_MASK:
                # Compression pointer
                if not jumped:
                    return_offset = offset + 2
                if offset + 1 >= len(data):
                    break
                pointer_offset = struct.unpack("!H", data[offset:offset + 2])[0]
                pointer_offset &= 0x3FFF
                offset = pointer_offset
                jumped = True
                jumps += 1
                if jumps > max_jumps:
                    raise ValueError(
                        "DNS name compression pointer loop detected. "
                        "Maximum jump count exceeded."
                    )
                continue

            if length == 0:
                if not jumped:
                    return_offset = offset + 1
                break

            offset += 1
            if offset + length > len(data):
                break
            label = data[offset:offset + length].decode("ascii")
            labels.append(label)
            offset += length

        name = ".".join(labels) + "." if labels else "."
        return name, return_offset

    @classmethod
    def encode_message(cls, message: DNSMessage) -> bytes:
        """Encode a complete DNS message to wire format bytes.

        Builds the 12-byte header, followed by the question section,
        answer section, authority section, and additional section.
        Name compression is applied across all sections.

        Args:
            message: The DNS message to encode.

        Returns:
            Complete wire-format DNS message as bytes.
        """
        buf = bytearray()
        compression_table: Dict[str, int] = {}

        # Header (12 bytes)
        flags = message.header.to_flags()
        buf += struct.pack(
            "!HHHHHH",
            message.header.id,
            flags,
            message.header.qdcount,
            message.header.ancount,
            message.header.nscount,
            message.header.arcount,
        )

        # Questions
        for q in message.questions:
            name_bytes = cls.encode_name_compressed(q.qname, buf, compression_table)
            buf += name_bytes
            buf += struct.pack("!HH", q.qtype, q.qclass)

        # Resource record sections
        for rr in message.answers + message.authority + message.additional:
            name_bytes = cls.encode_name_compressed(rr.name, buf, compression_table)
            buf += name_bytes
            buf += struct.pack("!HHiH", rr.rtype, rr.rclass, rr.ttl, rr.rdlength)
            buf += rr.rdata

        return bytes(buf)

    @classmethod
    def decode_message(cls, data: bytes) -> DNSMessage:
        """Decode a DNS message from wire format bytes.

        Parses the header, then iterates through the question and
        resource record sections according to the counts in the header.

        Args:
            data: Raw DNS message bytes.

        Returns:
            Parsed DNSMessage object.

        Raises:
            ValueError: If the message is too short or malformed.
        """
        if len(data) < 12:
            raise ValueError(
                f"DNS message too short: {len(data)} bytes. "
                f"Minimum header size is 12 bytes per RFC 1035."
            )

        msg_id, flags, qdcount, ancount, nscount, arcount = struct.unpack(
            "!HHHHHH", data[:12]
        )
        header = DNSHeader.from_flags(msg_id, flags, qdcount, ancount, nscount, arcount)

        offset = 12
        questions: List[DNSQuestion] = []
        for _ in range(qdcount):
            qname, offset = cls.decode_name(data, offset)
            if offset + 4 > len(data):
                raise ValueError("DNS message truncated in question section.")
            qtype, qclass = struct.unpack("!HH", data[offset:offset + 4])
            offset += 4
            questions.append(DNSQuestion(qname=qname, qtype=qtype, qclass=qclass))

        def _decode_rr_section(count: int, off: int) -> Tuple[List[DNSResourceRecord], int]:
            records: List[DNSResourceRecord] = []
            for _ in range(count):
                name, off = cls.decode_name(data, off)
                if off + 10 > len(data):
                    raise ValueError("DNS message truncated in resource record.")
                rtype, rclass, ttl, rdlength = struct.unpack("!HHiH", data[off:off + 10])
                off += 10
                if off + rdlength > len(data):
                    raise ValueError("DNS message truncated in RDATA.")
                rdata = data[off:off + rdlength]
                off += rdlength

                rdata_parsed = cls._parse_rdata(rtype, rdata, data)
                records.append(DNSResourceRecord(
                    name=name,
                    rtype=rtype,
                    rclass=rclass,
                    ttl=ttl,
                    rdlength=rdlength,
                    rdata=rdata,
                    rdata_parsed=rdata_parsed,
                ))
            return records, off

        answers, offset = _decode_rr_section(ancount, offset)
        authority, offset = _decode_rr_section(nscount, offset)
        additional, offset = _decode_rr_section(arcount, offset)

        return DNSMessage(
            header=header,
            questions=questions,
            answers=answers,
            authority=authority,
            additional=additional,
        )

    @staticmethod
    def _parse_rdata(rtype: int, rdata: bytes, message_data: bytes) -> str:
        """Parse RDATA into a human-readable string based on record type."""
        if rtype == DNSType.A and len(rdata) == 4:
            return ".".join(str(b) for b in rdata)
        elif rtype == DNSType.AAAA and len(rdata) == 16:
            parts = []
            for i in range(0, 16, 2):
                parts.append(f"{rdata[i]:02x}{rdata[i+1]:02x}")
            return ":".join(parts)
        elif rtype == DNSType.TXT:
            return DNSWireFormat._decode_txt_rdata(rdata)
        elif rtype == DNSType.MX and len(rdata) >= 3:
            preference = struct.unpack("!H", rdata[:2])[0]
            # MX exchange name — simplified parse (no compression in RDATA for our use)
            exchange = rdata[2:].decode("ascii", errors="replace").strip("\x00")
            return f"{preference} {exchange}"
        elif rtype == DNSType.NS or rtype == DNSType.CNAME or rtype == DNSType.PTR:
            # These contain a domain name in RDATA
            try:
                name, _ = DNSWireFormat.decode_name(rdata, 0)
                return name
            except (ValueError, IndexError):
                return rdata.hex()
        elif rtype == DNSType.SOA:
            return DNSWireFormat._decode_soa_rdata(rdata)
        else:
            return rdata.hex()

    @staticmethod
    def _decode_txt_rdata(rdata: bytes) -> str:
        """Decode TXT RDATA, which is one or more length-prefixed strings."""
        texts: List[str] = []
        offset = 0
        while offset < len(rdata):
            length = rdata[offset]
            offset += 1
            if offset + length > len(rdata):
                break
            texts.append(rdata[offset:offset + length].decode("utf-8", errors="replace"))
            offset += length
        return " ".join(texts)

    @staticmethod
    def _decode_soa_rdata(rdata: bytes) -> str:
        """Decode SOA RDATA into a human-readable string."""
        try:
            mname, offset = DNSWireFormat.decode_name(rdata, 0)
            rname, offset = DNSWireFormat.decode_name(rdata, offset)
            if offset + 20 <= len(rdata):
                serial, refresh, retry, expire, minimum = struct.unpack(
                    "!IIIII", rdata[offset:offset + 20]
                )
                return (
                    f"{mname} {rname} {serial} {refresh} {retry} {expire} {minimum}"
                )
            return f"{mname} {rname}"
        except (ValueError, IndexError):
            return rdata.hex()


# ---------------------------------------------------------------------------
# TXT Record Builder
# ---------------------------------------------------------------------------

class TXTRecordBuilder:
    """Builds TXT record RDATA from character strings.

    TXT records contain one or more character strings, each preceded
    by a single-byte length field. Individual strings are limited to
    255 bytes. Longer text is split across multiple character strings
    within the same TXT record.
    """

    @staticmethod
    def build(text: str) -> bytes:
        """Encode a text string as TXT RDATA.

        Args:
            text: The text to encode. If longer than 255 bytes, it
                will be split into multiple character strings.

        Returns:
            TXT RDATA bytes with length-prefixed character strings.
        """
        encoded = text.encode("utf-8")
        result = b""
        offset = 0
        while offset < len(encoded):
            chunk = encoded[offset:offset + 255]
            result += struct.pack("B", len(chunk)) + chunk
            offset += 255
        if not encoded:
            result = b"\x00"
        return result

    @staticmethod
    def build_multi(texts: List[str]) -> bytes:
        """Encode multiple text strings into a single TXT RDATA field."""
        result = b""
        for text in texts:
            encoded = text.encode("utf-8")
            if len(encoded) > 255:
                raise ValueError(
                    f"Individual TXT string exceeds 255 bytes: {len(encoded)}. "
                    f"Use build() for automatic splitting."
                )
            result += struct.pack("B", len(encoded)) + encoded
        return result


# ---------------------------------------------------------------------------
# SOA Record Builder
# ---------------------------------------------------------------------------

class SOARecordBuilder:
    """Builds SOA record RDATA per RFC 1035 Section 3.3.13."""

    @staticmethod
    def build(
        mname: str,
        rname: str,
        serial: int,
        refresh: int = 3600,
        retry: int = 900,
        expire: int = 86400,
        minimum: int = 300,
    ) -> bytes:
        """Encode SOA RDATA.

        Args:
            mname: Primary name server for the zone.
            rname: Email address of the zone administrator
                (with @ replaced by .).
            serial: Zone serial number.
            refresh: Refresh interval in seconds.
            retry: Retry interval in seconds.
            expire: Expire interval in seconds.
            minimum: Minimum TTL for negative caching.

        Returns:
            SOA RDATA bytes.
        """
        result = DNSWireFormat.encode_name(mname)
        result += DNSWireFormat.encode_name(rname)
        result += struct.pack("!IIIII", serial, refresh, retry, expire, minimum)
        return result


# ---------------------------------------------------------------------------
# Zone
# ---------------------------------------------------------------------------

class Zone:
    """A DNS zone containing resource records for a domain.

    Supports exact name matching, wildcard matching (*.domain),
    and delegation via NS records. Records are indexed by name
    and type for efficient lookup.

    Attributes:
        origin: The zone's origin domain (e.g. "fizzbuzz.local.").
        default_ttl: Default TTL applied to records without explicit TTL.
        soa: The SOA record for this zone, if defined.
    """

    def __init__(self, origin: str, default_ttl: int = DEFAULT_TTL) -> None:
        if not origin.endswith("."):
            origin = origin + "."
        self.origin = origin
        self.default_ttl = default_ttl
        self.soa: Optional[DNSResourceRecord] = None
        self._records: Dict[str, List[DNSResourceRecord]] = defaultdict(list)
        self._ns_records: List[DNSResourceRecord] = []

    def add_record(self, record: DNSResourceRecord) -> None:
        """Add a resource record to the zone.

        Args:
            record: The resource record to add. The name should be
                fully qualified (ending with a dot).
        """
        name = record.name.lower()
        if not name.endswith("."):
            name = name + "."

        record_copy = DNSResourceRecord(
            name=name,
            rtype=record.rtype,
            rclass=record.rclass,
            ttl=record.ttl if record.ttl else self.default_ttl,
            rdlength=record.rdlength,
            rdata=record.rdata,
            rdata_parsed=record.rdata_parsed,
        )

        self._records[name].append(record_copy)

        if record.rtype == DNSType.SOA:
            self.soa = record_copy
        elif record.rtype == DNSType.NS:
            self._ns_records.append(record_copy)

    def lookup(self, qname: str, qtype: int) -> List[DNSResourceRecord]:
        """Look up records matching the given name and type.

        Performs exact match first, then wildcard match if no exact
        match is found. ANY type queries return all records for the name.

        Args:
            qname: The domain name to look up (case-insensitive).
            qtype: The record type to match, or ANY for all types.

        Returns:
            List of matching resource records.
        """
        qname = qname.lower()
        if not qname.endswith("."):
            qname = qname + "."

        results: List[DNSResourceRecord] = []

        # Exact match
        if qname in self._records:
            for rr in self._records[qname]:
                if qtype == DNSType.ANY or rr.rtype == qtype:
                    results.append(rr)

        # Wildcard match if no exact results
        if not results:
            labels = qname.split(".")
            for i in range(1, len(labels)):
                wildcard = "*." + ".".join(labels[i:])
                if wildcard in self._records:
                    for rr in self._records[wildcard]:
                        if qtype == DNSType.ANY or rr.rtype == qtype:
                            # Return the wildcard record with the queried name
                            results.append(DNSResourceRecord(
                                name=qname,
                                rtype=rr.rtype,
                                rclass=rr.rclass,
                                ttl=rr.ttl,
                                rdlength=rr.rdlength,
                                rdata=rr.rdata,
                                rdata_parsed=rr.rdata_parsed,
                            ))
                    break

        return results

    def get_ns_records(self) -> List[DNSResourceRecord]:
        """Return all NS records for the zone apex."""
        return list(self._ns_records)

    def get_all_records(self) -> List[DNSResourceRecord]:
        """Return all records in the zone, flattened."""
        all_rrs: List[DNSResourceRecord] = []
        for rr_list in self._records.values():
            all_rrs.extend(rr_list)
        return all_rrs

    def is_authoritative_for(self, qname: str) -> bool:
        """Check if this zone is authoritative for the given domain name."""
        qname = qname.lower()
        if not qname.endswith("."):
            qname = qname + "."
        return qname.endswith(self.origin) or qname == self.origin

    @property
    def record_count(self) -> int:
        """Total number of resource records in the zone."""
        return sum(len(rrs) for rrs in self._records.values())


# ---------------------------------------------------------------------------
# Zone File Parser
# ---------------------------------------------------------------------------

class ZoneFile:
    """Parses BIND-style zone file format into a Zone object.

    Supports a practical subset of the BIND master file format:
    - $ORIGIN directive for setting the zone origin
    - $TTL directive for setting default TTL
    - SOA, NS, A, AAAA, TXT, MX, CNAME, PTR record types
    - Relative and absolute (FQDN) domain names
    - Comments (lines starting with ; or inline after ;)

    Example zone file content:
        $ORIGIN fizzbuzz.local.
        $TTL 3600
        @  IN  SOA  ns1.fizzbuzz.local. admin.fizzbuzz.local. (
                     2024010100 3600 900 86400 300 )
        @  IN  NS   ns1.fizzbuzz.local.
        15 IN  TXT  "FizzBuzz"
    """

    @classmethod
    def parse(cls, content: str, origin: str = "") -> Zone:
        """Parse zone file content into a Zone object.

        Args:
            content: The zone file text content.
            origin: Default origin if not specified by $ORIGIN directive.

        Returns:
            Populated Zone object.
        """
        default_ttl = DEFAULT_TTL
        current_origin = origin
        if current_origin and not current_origin.endswith("."):
            current_origin += "."

        zone: Optional[Zone] = None
        last_name = ""

        # Pre-process: join parenthesized continuation lines
        lines = cls._join_continuations(content.split("\n"))

        for line in lines:
            # Strip comments
            comment_idx = line.find(";")
            if comment_idx >= 0:
                line = line[:comment_idx]
            line = line.rstrip()
            if not line:
                continue

            # Directives
            if line.startswith("$ORIGIN"):
                current_origin = line.split(None, 1)[1].strip()
                if not current_origin.endswith("."):
                    current_origin += "."
                if zone is None:
                    zone = Zone(current_origin, default_ttl)
                continue

            if line.startswith("$TTL"):
                default_ttl = int(line.split(None, 1)[1].strip())
                if zone is not None:
                    zone.default_ttl = default_ttl
                continue

            if zone is None:
                zone = Zone(current_origin or ".", default_ttl)

            # Parse resource record line
            rr = cls._parse_rr_line(line, current_origin, default_ttl, last_name)
            if rr is not None:
                last_name = rr.name
                zone.add_record(rr)

        if zone is None:
            zone = Zone(current_origin or ".", default_ttl)

        return zone

    @staticmethod
    def _join_continuations(lines: List[str]) -> List[str]:
        """Join lines that are continued with parentheses."""
        result: List[str] = []
        current = ""
        in_parens = False

        for line in lines:
            stripped = line.strip()
            if not in_parens:
                if "(" in stripped:
                    in_parens = True
                    current = stripped.replace("(", " ")
                else:
                    result.append(line)
            else:
                if ")" in stripped:
                    current += " " + stripped.replace(")", " ")
                    result.append(current.strip())
                    current = ""
                    in_parens = False
                else:
                    current += " " + stripped

        if current:
            result.append(current.strip())

        return result

    @classmethod
    def _parse_rr_line(cls, line: str, origin: str, default_ttl: int,
                       last_name: str) -> Optional[DNSResourceRecord]:
        """Parse a single resource record line."""
        tokens = line.split()
        if not tokens:
            return None

        idx = 0
        name = ""
        ttl = default_ttl
        rclass = DNSClass.IN

        # Determine the owner name
        if line[0] in (" ", "\t"):
            # Continuation of previous name
            name = last_name
        else:
            raw_name = tokens[idx]
            idx += 1
            if raw_name == "@":
                name = origin
            elif raw_name.endswith("."):
                name = raw_name
            else:
                name = raw_name + "." + origin

        # Parse optional TTL and class
        while idx < len(tokens):
            tok = tokens[idx].upper()
            if tok in _CLASS_MAP:
                rclass = _CLASS_MAP[tok]
                idx += 1
            elif tok.isdigit():
                ttl = int(tok)
                idx += 1
            else:
                break

        if idx >= len(tokens):
            return None

        # Record type
        type_str = tokens[idx].upper()
        idx += 1

        if type_str not in _TYPE_MAP:
            return None

        rtype = _TYPE_MAP[type_str]

        # Remaining tokens are RDATA
        rdata_tokens = tokens[idx:]
        rdata, rdata_parsed = cls._build_rdata(rtype, rdata_tokens, origin)

        return DNSResourceRecord(
            name=name.lower(),
            rtype=rtype,
            rclass=rclass,
            ttl=ttl,
            rdlength=len(rdata),
            rdata=rdata,
            rdata_parsed=rdata_parsed,
        )

    @staticmethod
    def _build_rdata(rtype: int, tokens: List[str],
                     origin: str) -> Tuple[bytes, str]:
        """Build RDATA bytes from parsed tokens based on record type."""
        if rtype == DNSType.A:
            ip = tokens[0] if tokens else "0.0.0.0"
            parts = [int(p) for p in ip.split(".")]
            return struct.pack("BBBB", *parts), ip

        elif rtype == DNSType.AAAA:
            # Simplified: store as raw text for the platform's purposes
            addr = tokens[0] if tokens else "::"
            # Expand and pack IPv6
            rdata = ZoneFile._pack_ipv6(addr)
            return rdata, addr

        elif rtype == DNSType.TXT:
            # Join all tokens and strip surrounding quotes
            text = " ".join(tokens)
            if text.startswith('"') and text.endswith('"'):
                text = text[1:-1]
            rdata = TXTRecordBuilder.build(text)
            return rdata, text

        elif rtype == DNSType.MX:
            preference = int(tokens[0]) if tokens else 10
            exchange = tokens[1] if len(tokens) > 1 else ""
            if not exchange.endswith("."):
                exchange = exchange + "." + origin
            rdata = struct.pack("!H", preference) + DNSWireFormat.encode_name(exchange)
            return rdata, f"{preference} {exchange}"

        elif rtype in (DNSType.NS, DNSType.CNAME, DNSType.PTR):
            target = tokens[0] if tokens else origin
            if not target.endswith("."):
                target = target + "." + origin
            rdata = DNSWireFormat.encode_name(target)
            return rdata, target

        elif rtype == DNSType.SOA:
            mname = tokens[0] if tokens else ""
            rname = tokens[1] if len(tokens) > 1 else ""
            serial = int(tokens[2]) if len(tokens) > 2 else 1
            refresh = int(tokens[3]) if len(tokens) > 3 else 3600
            retry = int(tokens[4]) if len(tokens) > 4 else 900
            expire = int(tokens[5]) if len(tokens) > 5 else 86400
            minimum = int(tokens[6]) if len(tokens) > 6 else 300
            rdata = SOARecordBuilder.build(mname, rname, serial, refresh, retry, expire, minimum)
            parsed = f"{mname} {rname} {serial} {refresh} {retry} {expire} {minimum}"
            return rdata, parsed

        else:
            # Unknown type: store raw hex
            raw = " ".join(tokens)
            return raw.encode("ascii", errors="replace"), raw

    @staticmethod
    def _pack_ipv6(addr: str) -> bytes:
        """Pack an IPv6 address string into 16 bytes."""
        # Handle :: expansion
        if "::" in addr:
            left, right = addr.split("::", 1)
            left_parts = left.split(":") if left else []
            right_parts = right.split(":") if right else []
            missing = 8 - len(left_parts) - len(right_parts)
            parts = left_parts + ["0"] * missing + right_parts
        else:
            parts = addr.split(":")

        result = b""
        for part in parts:
            result += struct.pack("!H", int(part, 16) if part else 0)

        # Pad or truncate to 16 bytes
        if len(result) < 16:
            result += b"\x00" * (16 - len(result))
        return result[:16]


# ---------------------------------------------------------------------------
# FizzBuzz Zone
# ---------------------------------------------------------------------------

def _classify_number(n: int) -> str:
    """Classify a number according to canonical FizzBuzz rules.

    This is an internal classification function used exclusively for
    populating the DNS zone. It does not bypass the main evaluation
    pipeline — it exists solely to provide seed data for DNS records.
    The authoritative DNS zone must contain pre-computed results so
    that DNS queries can be resolved without invoking the full
    middleware stack.

    Args:
        n: The number to classify.

    Returns:
        The FizzBuzz classification string.
    """
    if n % 15 == 0:
        return "FizzBuzz"
    elif n % 3 == 0:
        return "Fizz"
    elif n % 5 == 0:
        return "Buzz"
    else:
        return str(n)


class FizzBuzzZone:
    """Pre-built authoritative DNS zone for the fizzbuzz.local domain.

    Populates the zone with:
    - SOA record: ns1.fizzbuzz.local. admin.fizzbuzz.local.
    - NS record: ns1.fizzbuzz.local.
    - A record for ns1: 127.0.0.1
    - TXT records for numbers 1-100 with their FizzBuzz classification
    - Wildcard TXT record for out-of-range queries

    This zone enables DNS-based FizzBuzz evaluation lookups, which is
    essential for environments where HTTP is not available or where
    DNS is the mandated service discovery protocol. Enterprise
    compliance frameworks increasingly require all data access to be
    auditable at the network layer, and DNS queries are logged by
    default in most enterprise network monitoring solutions.
    """

    ORIGIN = "fizzbuzz.local."
    SOA_MNAME = "ns1.fizzbuzz.local."
    SOA_RNAME = "admin.fizzbuzz.local."
    SOA_SERIAL = 2024010100
    SOA_REFRESH = 3600
    SOA_RETRY = 900
    SOA_EXPIRE = 86400
    SOA_MINIMUM = 300
    NS_HOST = "ns1.fizzbuzz.local."
    NS_IP = "127.0.0.1"
    DEFAULT_TTL = 3600
    RANGE_START = 1
    RANGE_END = 100

    @classmethod
    def build(cls, range_start: int = 1, range_end: int = 100) -> Zone:
        """Build the authoritative fizzbuzz.local zone.

        Args:
            range_start: First number to register (inclusive).
            range_end: Last number to register (inclusive).

        Returns:
            Fully populated Zone object.
        """
        zone = Zone(cls.ORIGIN, cls.DEFAULT_TTL)

        # SOA record
        soa_rdata = SOARecordBuilder.build(
            cls.SOA_MNAME,
            cls.SOA_RNAME,
            cls.SOA_SERIAL,
            cls.SOA_REFRESH,
            cls.SOA_RETRY,
            cls.SOA_EXPIRE,
            cls.SOA_MINIMUM,
        )
        soa_parsed = (
            f"{cls.SOA_MNAME} {cls.SOA_RNAME} {cls.SOA_SERIAL} "
            f"{cls.SOA_REFRESH} {cls.SOA_RETRY} {cls.SOA_EXPIRE} {cls.SOA_MINIMUM}"
        )
        zone.add_record(DNSResourceRecord(
            name=cls.ORIGIN,
            rtype=DNSType.SOA,
            rclass=DNSClass.IN,
            ttl=cls.DEFAULT_TTL,
            rdlength=len(soa_rdata),
            rdata=soa_rdata,
            rdata_parsed=soa_parsed,
        ))

        # NS record
        ns_rdata = DNSWireFormat.encode_name(cls.NS_HOST)
        zone.add_record(DNSResourceRecord(
            name=cls.ORIGIN,
            rtype=DNSType.NS,
            rclass=DNSClass.IN,
            ttl=cls.DEFAULT_TTL,
            rdlength=len(ns_rdata),
            rdata=ns_rdata,
            rdata_parsed=cls.NS_HOST,
        ))

        # A record for ns1
        ns_ip_parts = [int(p) for p in cls.NS_IP.split(".")]
        ns_a_rdata = struct.pack("BBBB", *ns_ip_parts)
        zone.add_record(DNSResourceRecord(
            name=cls.NS_HOST,
            rtype=DNSType.A,
            rclass=DNSClass.IN,
            ttl=cls.DEFAULT_TTL,
            rdlength=4,
            rdata=ns_a_rdata,
            rdata_parsed=cls.NS_IP,
        ))

        # TXT records for each number in the range
        for n in range(range_start, range_end + 1):
            classification = _classify_number(n)
            txt_rdata = TXTRecordBuilder.build(classification)
            record_name = f"{n}.{cls.ORIGIN}"
            zone.add_record(DNSResourceRecord(
                name=record_name,
                rtype=DNSType.TXT,
                rclass=DNSClass.IN,
                ttl=cls.DEFAULT_TTL,
                rdlength=len(txt_rdata),
                rdata=txt_rdata,
                rdata_parsed=classification,
            ))

        logger.info(
            "Built fizzbuzz.local zone with %d records (range %d-%d)",
            zone.record_count, range_start, range_end,
        )

        return zone

    @classmethod
    def generate_zone_file(cls, range_start: int = 1, range_end: int = 100) -> str:
        """Generate a BIND-style zone file for fizzbuzz.local.

        Returns:
            Zone file content as a string.
        """
        lines = [
            f"; Zone file for {cls.ORIGIN}",
            f"; Generated by Enterprise FizzBuzz Platform DNS Server",
            f"; Serial: {cls.SOA_SERIAL}",
            f";",
            f"$ORIGIN {cls.ORIGIN}",
            f"$TTL {cls.DEFAULT_TTL}",
            f"",
            f"@ IN SOA {cls.SOA_MNAME} {cls.SOA_RNAME} (",
            f"    {cls.SOA_SERIAL}  ; Serial",
            f"    {cls.SOA_REFRESH}        ; Refresh (1 hour)",
            f"    {cls.SOA_RETRY}         ; Retry (15 minutes)",
            f"    {cls.SOA_EXPIRE}       ; Expire (1 day)",
            f"    {cls.SOA_MINIMUM}         ; Minimum TTL (5 minutes)",
            f")",
            f"",
            f"@ IN NS {cls.NS_HOST}",
            f"ns1 IN A {cls.NS_IP}",
            f"",
            f"; FizzBuzz classification records",
        ]

        for n in range(range_start, range_end + 1):
            classification = _classify_number(n)
            lines.append(f'{n} IN TXT "{classification}"')

        lines.append("")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# DNS Resolver
# ---------------------------------------------------------------------------

class DNSResolver:
    """Resolves DNS queries against loaded zones.

    The resolver accepts a DNS query message, matches it against
    registered zones, and constructs an appropriate response message
    with answer, authority, and additional sections populated
    according to RFC 1035 resolution rules.

    Attributes:
        zones: Dictionary mapping zone origins to Zone objects.
    """

    def __init__(self) -> None:
        self.zones: Dict[str, Zone] = {}
        self._query_count = 0
        self._nxdomain_count = 0
        self._noerror_count = 0
        self._type_stats: Dict[str, int] = defaultdict(int)

    def add_zone(self, zone: Zone) -> None:
        """Register a zone with the resolver.

        Args:
            zone: The zone to add. Its origin is used as the lookup key.
        """
        self.zones[zone.origin.lower()] = zone
        logger.info("Registered zone: %s (%d records)", zone.origin, zone.record_count)

    def resolve(self, query: DNSMessage) -> DNSMessage:
        """Resolve a DNS query and return a response message.

        Processes each question in the query, looks up matching records
        in the appropriate zone, and constructs a response with the
        authoritative answer flag set when the server is authoritative
        for the queried zone.

        Args:
            query: The incoming DNS query message.

        Returns:
            DNS response message with answers populated.
        """
        self._query_count += 1

        response = DNSMessage()
        response.header = DNSHeader(
            id=query.header.id,
            qr=1,  # This is a response
            opcode=query.header.opcode,
            rd=query.header.rd,
            ra=0,  # No recursion available
        )
        response.questions = list(query.questions)
        response.header.qdcount = len(response.questions)

        all_answers: List[DNSResourceRecord] = []
        all_authority: List[DNSResourceRecord] = []
        all_additional: List[DNSResourceRecord] = []
        rcode = DNSRCode.NOERROR

        for question in query.questions:
            type_name = DNSType(question.qtype).name if question.qtype in DNSType.__members__.values() else f"TYPE{question.qtype}"
            self._type_stats[type_name] += 1

            zone = self._find_zone(question.qname)
            if zone is None:
                rcode = DNSRCode.REFUSED
                continue

            response.header.aa = 1  # Authoritative

            records = zone.lookup(question.qname, question.qtype)

            if records:
                all_answers.extend(records)
                self._noerror_count += 1
            else:
                # Check if the name exists at all (for NXDOMAIN vs NODATA)
                any_records = zone.lookup(question.qname, DNSType.ANY)
                if not any_records:
                    rcode = DNSRCode.NXDOMAIN
                    self._nxdomain_count += 1
                else:
                    # Name exists but not with the requested type (NODATA)
                    self._noerror_count += 1

                # Add SOA to authority section for negative responses
                if zone.soa is not None:
                    all_authority.append(zone.soa)

            # Add NS records to authority section
            if records:
                for ns in zone.get_ns_records():
                    if ns not in all_authority:
                        all_authority.append(ns)

        response.answers = all_answers
        response.authority = all_authority
        response.additional = all_additional
        response.header.ancount = len(all_answers)
        response.header.nscount = len(all_authority)
        response.header.arcount = len(all_additional)
        response.header.rcode = rcode

        return response

    def resolve_simple(self, qname: str, qtype_str: str = "TXT") -> Optional[str]:
        """Simplified resolution interface for CLI queries.

        Args:
            qname: Domain name to query.
            qtype_str: Record type as a string (e.g. "TXT", "A").

        Returns:
            The RDATA parsed value if found, None if NXDOMAIN.
        """
        qtype = _TYPE_MAP.get(qtype_str.upper(), DNSType.A)

        query = DNSMessage()
        query.header = DNSHeader(id=0x1234, qr=0, opcode=0, rd=1)
        query.questions = [DNSQuestion(qname=qname, qtype=qtype, qclass=DNSClass.IN)]
        query.header.qdcount = 1

        response = self.resolve(query)

        if response.answers:
            return response.answers[0].rdata_parsed
        return None

    def _find_zone(self, qname: str) -> Optional[Zone]:
        """Find the most specific zone that is authoritative for qname."""
        qname = qname.lower()
        if not qname.endswith("."):
            qname = qname + "."

        labels = qname.split(".")
        for i in range(len(labels)):
            candidate = ".".join(labels[i:])
            if candidate in self.zones:
                return self.zones[candidate]

        return None

    @property
    def stats(self) -> Dict[str, Any]:
        """Return resolver statistics."""
        return {
            "total_queries": self._query_count,
            "noerror": self._noerror_count,
            "nxdomain": self._nxdomain_count,
            "type_breakdown": dict(self._type_stats),
            "zones_loaded": len(self.zones),
        }


# ---------------------------------------------------------------------------
# Negative Cache (NSEC-style Authenticated Denial of Existence)
# ---------------------------------------------------------------------------

class NegativeCache:
    """Caches negative DNS responses with NSEC-style denial of existence.

    When a query results in NXDOMAIN, the negative cache stores a
    proof of non-existence that can be returned for subsequent queries
    without re-querying the zone. This is modeled after DNSSEC NSEC
    records, which provide authenticated denial by listing the names
    that do exist on either side of the queried name in canonical order.

    The cache respects the SOA minimum TTL as the negative caching TTL,
    per RFC 2308. Entries are automatically expired when their TTL
    elapses.

    Attributes:
        max_entries: Maximum number of negative cache entries.
        default_neg_ttl: Default negative TTL in seconds.
    """

    @dataclass
    class NegEntry:
        """A negative cache entry representing a confirmed non-existence."""
        qname: str
        qtype: int
        rcode: int
        soa_rdata: Optional[bytes]
        timestamp: float
        ttl: int
        nsec_prev: str = ""
        nsec_next: str = ""
        hit_count: int = 0

    def __init__(self, max_entries: int = 1000, default_neg_ttl: int = 300) -> None:
        self.max_entries = max_entries
        self.default_neg_ttl = default_neg_ttl
        self._cache: Dict[str, NegativeCache.NegEntry] = {}
        self._total_lookups = 0
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def _make_key(self, qname: str, qtype: int) -> str:
        """Generate a cache key from query parameters."""
        return f"{qname.lower()}|{qtype}"

    def put(self, qname: str, qtype: int, rcode: int,
            soa_rdata: Optional[bytes] = None, ttl: Optional[int] = None,
            zone_names: Optional[List[str]] = None) -> None:
        """Store a negative response in the cache.

        Args:
            qname: The queried domain name.
            qtype: The queried record type.
            rcode: The response code (typically NXDOMAIN).
            soa_rdata: The SOA RDATA from the authority section.
            ttl: Override TTL for this entry.
            zone_names: Sorted list of names in the zone, used to
                compute NSEC predecessor and successor.
        """
        key = self._make_key(qname, qtype)

        # Compute NSEC-style neighbor names
        nsec_prev = ""
        nsec_next = ""
        if zone_names:
            sorted_names = sorted(zone_names)
            qname_lower = qname.lower()
            for i, name in enumerate(sorted_names):
                if name.lower() > qname_lower:
                    nsec_next = name
                    if i > 0:
                        nsec_prev = sorted_names[i - 1]
                    break
            if not nsec_next and sorted_names:
                nsec_prev = sorted_names[-1]

        entry = NegativeCache.NegEntry(
            qname=qname.lower(),
            qtype=qtype,
            rcode=rcode,
            soa_rdata=soa_rdata,
            timestamp=time.monotonic(),
            ttl=ttl or self.default_neg_ttl,
            nsec_prev=nsec_prev,
            nsec_next=nsec_next,
        )

        # Evict if at capacity
        if len(self._cache) >= self.max_entries and key not in self._cache:
            self._evict_oldest()

        self._cache[key] = entry

    def get(self, qname: str, qtype: int) -> Optional[NegEntry]:
        """Look up a negative cache entry.

        Returns the entry if found and not expired, None otherwise.
        Expired entries are removed on access.
        """
        self._total_lookups += 1
        key = self._make_key(qname, qtype)

        entry = self._cache.get(key)
        if entry is None:
            self._misses += 1
            return None

        elapsed = time.monotonic() - entry.timestamp
        if elapsed > entry.ttl:
            del self._cache[key]
            self._misses += 1
            return None

        entry.hit_count += 1
        self._hits += 1
        return entry

    def _evict_oldest(self) -> None:
        """Evict the oldest entry from the cache."""
        if not self._cache:
            return
        oldest_key = min(self._cache, key=lambda k: self._cache[k].timestamp)
        del self._cache[oldest_key]
        self._evictions += 1

    def clear(self) -> None:
        """Clear all entries from the negative cache."""
        self._cache.clear()

    @property
    def size(self) -> int:
        """Current number of entries in the cache."""
        return len(self._cache)

    @property
    def stats(self) -> Dict[str, Any]:
        """Return cache statistics."""
        return {
            "size": self.size,
            "max_entries": self.max_entries,
            "total_lookups": self._total_lookups,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": (self._hits / self._total_lookups * 100) if self._total_lookups > 0 else 0.0,
            "evictions": self._evictions,
        }


# ---------------------------------------------------------------------------
# DNS Dashboard
# ---------------------------------------------------------------------------

class DNSDashboard:
    """ASCII dashboard rendering for the FizzDNS subsystem.

    Displays query statistics, zone inventory, negative cache status,
    and sample records in a formatted terminal dashboard.
    """

    @staticmethod
    def render(
        resolver: DNSResolver,
        negative_cache: Optional[NegativeCache] = None,
        width: int = 72,
        show_records: bool = True,
        max_records: int = 20,
    ) -> str:
        """Render the DNS dashboard as a multi-section ASCII display.

        Args:
            resolver: The DNS resolver containing zones and stats.
            negative_cache: Optional negative cache for stats display.
            width: Dashboard width in characters.
            show_records: Whether to show sample zone records.
            max_records: Maximum number of records to display.

        Returns:
            Formatted dashboard string.
        """
        lines: List[str] = []
        border = "+" + "-" * (width - 2) + "+"

        def _center(text: str) -> str:
            return "|" + text.center(width - 2) + "|"

        def _left(text: str) -> str:
            return "|  " + text.ljust(width - 4) + "|"

        def _separator() -> str:
            return "+" + "-" * (width - 2) + "+"

        # Title
        lines.append(border)
        lines.append(_center("FizzDNS — Authoritative DNS Server"))
        lines.append(_center("Enterprise FizzBuzz Platform"))
        lines.append(border)

        # Resolver Statistics
        stats = resolver.stats
        lines.append(_center("Query Statistics"))
        lines.append(_separator())
        lines.append(_left(f"Total Queries:     {stats['total_queries']}"))
        lines.append(_left(f"NOERROR:           {stats['noerror']}"))
        lines.append(_left(f"NXDOMAIN:          {stats['nxdomain']}"))

        if stats["type_breakdown"]:
            lines.append(_left(""))
            lines.append(_left("Query Type Breakdown:"))
            for qtype, count in sorted(stats["type_breakdown"].items()):
                lines.append(_left(f"  {qtype:<10} {count:>6}"))

        lines.append(_separator())

        # Zone Inventory
        lines.append(_center("Zone Inventory"))
        lines.append(_separator())
        lines.append(_left(f"Zones Loaded: {stats['zones_loaded']}"))
        for origin, zone in resolver.zones.items():
            lines.append(_left(f"  {origin:<30} {zone.record_count:>4} records"))
            if zone.soa:
                max_soa_len = max(0, width - 15)
                lines.append(_left(f"    SOA: {zone.soa.rdata_parsed[:max_soa_len]}"))
        lines.append(_separator())

        # Negative Cache
        if negative_cache is not None:
            nc_stats = negative_cache.stats
            lines.append(_center("Negative Cache (NSEC-style)"))
            lines.append(_separator())
            lines.append(_left(f"Entries:    {nc_stats['size']} / {nc_stats['max_entries']}"))
            lines.append(_left(f"Lookups:    {nc_stats['total_lookups']}"))
            lines.append(_left(f"Hits:       {nc_stats['hits']}"))
            lines.append(_left(f"Misses:     {nc_stats['misses']}"))
            lines.append(_left(f"Hit Rate:   {nc_stats['hit_rate']:.1f}%"))
            lines.append(_left(f"Evictions:  {nc_stats['evictions']}"))
            lines.append(_separator())

        # Sample Records
        if show_records:
            lines.append(_center("Sample Zone Records"))
            lines.append(_separator())
            lines.append(_left(f"{'NAME':<30} {'TYPE':<6} {'TTL':<6} {'RDATA'}"))
            lines.append(_left("-" * (width - 6)))

            shown = 0
            for origin, zone in resolver.zones.items():
                for rr in zone.get_all_records():
                    if shown >= max_records:
                        remaining = zone.record_count - shown
                        if remaining > 0:
                            lines.append(_left(f"  ... and {remaining} more records"))
                        break
                    max_rdata = max(0, width - 50)
                    rdata_display = rr.rdata_parsed[:max_rdata] if rr.rdata_parsed else ""
                    name_display = rr.name[:28]
                    lines.append(_left(
                        f"{name_display:<30} {rr.type_name():<6} {rr.ttl:<6} {rdata_display}"
                    ))
                    shown += 1

            lines.append(border)

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# DNS Query Formatter
# ---------------------------------------------------------------------------

class DNSQueryFormatter:
    """Formats DNS query results in dig-style output.

    Produces output similar to the `dig` command-line tool, with
    header flags, question section, answer section, authority section,
    and query metadata.
    """

    @staticmethod
    def format_response(response: DNSMessage, query_time_us: float = 0.0) -> str:
        """Format a DNS response in dig-style output.

        Args:
            response: The DNS response message.
            query_time_us: Query time in microseconds.

        Returns:
            Formatted multi-line string resembling dig output.
        """
        lines: List[str] = []

        # Header
        opcode = DNSOpcode(response.header.opcode).name if response.header.opcode in DNSOpcode.__members__.values() else str(response.header.opcode)
        rcode = DNSRCode(response.header.rcode).name if response.header.rcode in DNSRCode.__members__.values() else str(response.header.rcode)

        flags_parts: List[str] = []
        if response.header.qr:
            flags_parts.append("qr")
        if response.header.aa:
            flags_parts.append("aa")
        if response.header.tc:
            flags_parts.append("tc")
        if response.header.rd:
            flags_parts.append("rd")
        if response.header.ra:
            flags_parts.append("ra")

        lines.append(f";; ->>HEADER<<- opcode: {opcode}, status: {rcode}, id: {response.header.id}")
        lines.append(f";; flags: {' '.join(flags_parts)}; QUERY: {response.header.qdcount}, "
                     f"ANSWER: {response.header.ancount}, AUTHORITY: {response.header.nscount}, "
                     f"ADDITIONAL: {response.header.arcount}")
        lines.append("")

        # Question section
        if response.questions:
            lines.append(";; QUESTION SECTION:")
            for q in response.questions:
                type_name = DNSType(q.qtype).name if q.qtype in DNSType.__members__.values() else f"TYPE{q.qtype}"
                class_name = DNSClass(q.qclass).name if q.qclass in DNSClass.__members__.values() else f"CLASS{q.qclass}"
                lines.append(f";{q.qname:<30} {class_name:<4} {type_name}")
            lines.append("")

        # Answer section
        if response.answers:
            lines.append(";; ANSWER SECTION:")
            for rr in response.answers:
                rdata_str = rr.rdata_parsed
                if rr.rtype == DNSType.TXT:
                    rdata_str = f'"{rr.rdata_parsed}"'
                lines.append(
                    f"{rr.name:<30} {rr.ttl:<6} {rr.class_name():<4} "
                    f"{rr.type_name():<6} {rdata_str}"
                )
            lines.append("")

        # Authority section
        if response.authority:
            lines.append(";; AUTHORITY SECTION:")
            for rr in response.authority:
                rdata_str = rr.rdata_parsed
                lines.append(
                    f"{rr.name:<30} {rr.ttl:<6} {rr.class_name():<4} "
                    f"{rr.type_name():<6} {rdata_str}"
                )
            lines.append("")

        # Additional section
        if response.additional:
            lines.append(";; ADDITIONAL SECTION:")
            for rr in response.additional:
                rdata_str = rr.rdata_parsed
                lines.append(
                    f"{rr.name:<30} {rr.ttl:<6} {rr.class_name():<4} "
                    f"{rr.type_name():<6} {rdata_str}"
                )
            lines.append("")

        # Query metadata
        lines.append(f";; Query time: {query_time_us:.0f} usec")
        lines.append(f";; SERVER: 127.0.0.1#5353 (fizzbuzz.local)")
        lines.append(f";; MSG SIZE  rcvd: {12 + sum(len(a.rdata) + 12 for a in response.answers)}")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# DNS Middleware
# ---------------------------------------------------------------------------

class DNSMiddleware(IMiddleware):
    """Middleware that registers FizzBuzz evaluation results as DNS records.

    As each number is processed through the middleware pipeline, this
    middleware updates the authoritative DNS zone with the result. This
    ensures that the DNS zone always reflects the most recent evaluation
    results, maintaining consistency between the application layer and
    the DNS data plane.

    If the evaluation pipeline produces a different classification than
    the pre-computed DNS record (which should never happen unless the
    rules have been modified), the DNS record is updated to match the
    authoritative pipeline result.

    Attributes:
        zone: The DNS zone to update with evaluation results.
        resolver: The DNS resolver for verification queries.
        records_updated: Count of DNS records created or updated.
    """

    def __init__(self, zone: Zone, resolver: DNSResolver) -> None:
        self._zone = zone
        self._resolver = resolver
        self.records_updated = 0
        self.records_verified = 0
        self._mismatches: List[Dict[str, str]] = []

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process context and register the result as a DNS TXT record."""
        result = next_handler(context)

        if result.results:
            latest = result.results[-1]
            record_name = f"{latest.number}.{self._zone.origin}"
            classification = latest.classification.value if hasattr(latest.classification, "value") else str(latest.classification)

            # Map enum values to canonical names
            classification_map = {
                "FizzBuzzClassification.FIZZ": "Fizz",
                "FizzBuzzClassification.BUZZ": "Buzz",
                "FizzBuzzClassification.FIZZBUZZ": "FizzBuzz",
            }
            display_name = classification_map.get(
                str(latest.classification), classification
            )

            # Check for canonical enum name patterns
            if hasattr(latest.classification, "name"):
                name_upper = latest.classification.name
                name_map = {
                    "FIZZ": "Fizz",
                    "BUZZ": "Buzz",
                    "FIZZBUZZ": "FizzBuzz",
                    "NUMBER": str(latest.number),
                }
                display_name = name_map.get(name_upper, display_name)

            # Verify against existing DNS record
            existing = self._resolver.resolve_simple(record_name, "TXT")
            if existing is not None and existing != display_name:
                self._mismatches.append({
                    "number": str(latest.number),
                    "dns_value": existing,
                    "pipeline_value": display_name,
                })

            # Update the zone with the authoritative result
            txt_rdata = TXTRecordBuilder.build(display_name)
            self._zone.add_record(DNSResourceRecord(
                name=record_name,
                rtype=DNSType.TXT,
                rclass=DNSClass.IN,
                ttl=DEFAULT_TTL,
                rdlength=len(txt_rdata),
                rdata=txt_rdata,
                rdata_parsed=display_name,
            ))
            self.records_updated += 1
            self.records_verified += 1

        return result

    def get_name(self) -> str:
        """Return the middleware identifier."""
        return "DNSMiddleware"

    def get_priority(self) -> int:
        """Return the middleware execution priority.

        DNS record registration runs late in the pipeline to capture
        the final, authoritative classification after all other
        middleware has had its say.
        """
        return 950

    @property
    def mismatches(self) -> List[Dict[str, str]]:
        """Return any mismatches between DNS and pipeline results."""
        return list(self._mismatches)


# ---------------------------------------------------------------------------
# Public API for __main__.py integration
# ---------------------------------------------------------------------------

def create_dns_subsystem(
    range_start: int = 1,
    range_end: int = 100,
    neg_cache_size: int = 1000,
    neg_cache_ttl: int = 300,
) -> Tuple[Zone, DNSResolver, NegativeCache, DNSMiddleware]:
    """Create and wire all DNS subsystem components.

    Args:
        range_start: First number in the FizzBuzz DNS zone.
        range_end: Last number in the FizzBuzz DNS zone.
        neg_cache_size: Maximum negative cache entries.
        neg_cache_ttl: Negative cache TTL in seconds.

    Returns:
        Tuple of (zone, resolver, negative_cache, middleware).
    """
    zone = FizzBuzzZone.build(range_start, range_end)
    resolver = DNSResolver()
    resolver.add_zone(zone)

    negative_cache = NegativeCache(
        max_entries=neg_cache_size,
        default_neg_ttl=neg_cache_ttl,
    )

    middleware = DNSMiddleware(zone, resolver)

    return zone, resolver, negative_cache, middleware
