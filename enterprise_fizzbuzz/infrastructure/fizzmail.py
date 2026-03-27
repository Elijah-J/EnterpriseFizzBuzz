"""
Enterprise FizzBuzz Platform - FizzMail: SMTP/IMAP Email Server

Production-grade SMTP (RFC 5321) and IMAP (RFC 3501) email server for the
Enterprise FizzBuzz Platform.  Implements the full email specification stack:
SMTP command processing with STARTTLS upgrade, SMTP AUTH (PLAIN, LOGIN,
CRAM-MD5), RFC 5322 header parsing, MIME multipart construction (mixed,
alternative, related) with base64 and quoted-printable encoding, message
queuing with exponential-backoff retry, relay routing via MX record lookup,
SPF validation (RFC 7208), DKIM signing and verification (RFC 6376),
DMARC evaluation (RFC 7489), greylisting, RBL/DNSBL integration,
bounce handling with DSN generation (RFC 3464), IMAP mailbox management,
FETCH with partial data specifiers, SEARCH with full criteria grammar,
UID commands, IDLE push notifications, NAMESPACE, and Maildir storage.

FizzMail is the platform's universal notification delivery channel -- the
process that binds to port 2525 (SMTP) and 1143 (IMAP), accepts inbound
mail, validates sender authentication, queues outbound delivery, and
provides mailbox access to twelve notification-producing subsystems.

Architecture reference: Postfix 3.8, Dovecot 2.3, RFC 5321/3501/5322/6376/7208/7489.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import json
import logging
import math
import os
import random
import re
import struct
import threading
import time
import uuid
import zlib
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum, auto
from typing import Any, Callable, Dict, Iterator, List, Optional, Set, Tuple, Union

from enterprise_fizzbuzz.domain.exceptions.fizzmail import (
    FizzMailError,
    FizzMailSMTPError,
    FizzMailIMAPError,
    FizzMailTLSError,
    FizzMailAuthError,
    FizzMailEnvelopeError,
    FizzMailDataError,
    FizzMailSizeLimitError,
    FizzMailHeaderParseError,
    FizzMailMIMEError,
    FizzMailMIMEBoundaryError,
    FizzMailEncodingError,
    FizzMailQueueError,
    FizzMailRetryExhaustedError,
    FizzMailRelayError,
    FizzMailMXLookupError,
    FizzMailSPFError,
    FizzMailSPFPermError,
    FizzMailSPFTempError,
    FizzMailDKIMError,
    FizzMailDKIMSignatureError,
    FizzMailDKIMKeyError,
    FizzMailDMARCError,
    FizzMailGreylistError,
    FizzMailRBLError,
    FizzMailBounceError,
    FizzMailIMAPStateError,
    FizzMailMailboxError,
    FizzMailMailboxNotFoundError,
    FizzMailMailboxExistsError,
    FizzMailFetchError,
    FizzMailSearchError,
    FizzMailFlagError,
    FizzMailQuotaError,
    FizzMailUIDError,
    FizzMailConfigError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzResult,
    ProcessingContext,
)

logger = logging.getLogger("enterprise_fizzbuzz.fizzmail")


# ============================================================
# Event Type Registration
# ============================================================

EVENT_MESSAGE_RECEIVED = EventType.register("FIZZMAIL_MESSAGE_RECEIVED")
EVENT_MESSAGE_SENT = EventType.register("FIZZMAIL_MESSAGE_SENT")
EVENT_MESSAGE_BOUNCED = EventType.register("FIZZMAIL_MESSAGE_BOUNCED")
EVENT_AUTH_SUCCESS = EventType.register("FIZZMAIL_AUTH_SUCCESS")
EVENT_AUTH_FAILURE = EventType.register("FIZZMAIL_AUTH_FAILURE")
EVENT_SPF_RESULT = EventType.register("FIZZMAIL_SPF_RESULT")
EVENT_DKIM_RESULT = EventType.register("FIZZMAIL_DKIM_RESULT")
EVENT_DMARC_RESULT = EventType.register("FIZZMAIL_DMARC_RESULT")


# ============================================================
# Constants
# ============================================================

FIZZMAIL_VERSION = "1.0.0"
"""FizzMail SMTP/IMAP server version."""

FIZZMAIL_SERVER_NAME = f"FizzMail/{FIZZMAIL_VERSION} (Enterprise FizzBuzz Platform)"
"""Server identification string for SMTP banners and IMAP greetings."""

DEFAULT_SMTP_PORT = 2525
DEFAULT_IMAP_PORT = 1143
DEFAULT_DOMAIN = "fizzbuzz.local"
DEFAULT_HOSTNAME = "mail.fizzbuzz.local"

DEFAULT_MAX_MESSAGE_SIZE = 26214400      # 25 MB
DEFAULT_MAX_RECIPIENTS = 100
DEFAULT_MAX_LINE_LENGTH = 998            # RFC 5321 Section 4.5.3.1.6
DEFAULT_MAX_HEADER_SIZE = 65536          # 64 KB

DEFAULT_SMTP_TIMEOUT = 300.0             # 5 minutes per RFC 5321
DEFAULT_IMAP_TIMEOUT = 1800.0            # 30 minutes for IDLE

DEFAULT_RETRY_BASE_DELAY = 60.0          # seconds
DEFAULT_RETRY_MAX_DELAY = 3600.0         # 1 hour
DEFAULT_RETRY_MAX_ATTEMPTS = 5

DEFAULT_QUOTA = 104857600                # 100 MB
DEFAULT_GREYLIST_DELAY = 300.0           # 5 minutes
DEFAULT_GREYLIST_TTL = 86400.0           # 24 hours
DEFAULT_GREYLIST_WHITELIST_THRESHOLD = 3

DEFAULT_DKIM_SELECTOR = "fizzbuzz"
DEFAULT_DASHBOARD_WIDTH = 72
DEFAULT_WORKERS = 4

MIDDLEWARE_PRIORITY = 120

SMTP_REPLIES = {
    220: "Service ready",
    221: "Service closing transmission channel",
    235: "Authentication successful",
    250: "OK",
    334: "",
    354: "Start mail input; end with <CRLF>.<CRLF>",
    421: "Service not available, closing transmission channel",
    450: "Requested mail action not taken: mailbox unavailable",
    451: "Requested action aborted: local error in processing",
    452: "Requested action not taken: insufficient system storage",
    500: "Syntax error, command unrecognized",
    501: "Syntax error in parameters or arguments",
    502: "Command not implemented",
    503: "Bad sequence of commands",
    504: "Command parameter not implemented",
    530: "Authentication required",
    535: "Authentication credentials invalid",
    550: "Requested action not taken: mailbox unavailable",
    552: "Requested mail action aborted: exceeded storage allocation",
    553: "Requested action not taken: mailbox name not allowed",
    554: "Transaction failed",
}

IMAP_SYSTEM_FLAGS = frozenset({
    r"\Seen", r"\Answered", r"\Flagged", r"\Deleted", r"\Draft", r"\Recent",
})

IMAP_PERMANENT_FLAGS = frozenset({
    r"\Seen", r"\Answered", r"\Flagged", r"\Deleted", r"\Draft",
})

MAILDIR_FLAG_MAP = {
    r"\Seen": "S",
    r"\Answered": "R",
    r"\Flagged": "F",
    r"\Deleted": "T",
    r"\Draft": "D",
}

MAILDIR_FLAG_REVERSE = {v: k for k, v in MAILDIR_FLAG_MAP.items()}

DEFAULT_MAILBOXES = ("INBOX", "Sent", "Drafts", "Trash", "Junk")

DEFAULT_CREDENTIALS = {
    "postmaster": "postmaster",
    "admin": "admin",
    "fizzbuzz": "fizzbuzz",
}

# RSA simulation constants for DKIM
DKIM_SIMULATED_KEY_SIZE = 2048
DKIM_SIMULATED_PRIVATE_KEY = "-----BEGIN RSA PRIVATE KEY-----\nFizzMailSimulatedPrivateKey\n-----END RSA PRIVATE KEY-----"
DKIM_SIMULATED_PUBLIC_KEY = "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAFizzMailSimulatedPublicKey"


# ============================================================
# Enums
# ============================================================


class SMTPState(Enum):
    """SMTP session state machine states per RFC 5321."""
    CONNECTED = auto()
    GREETED = auto()
    TLS_NEGOTIATED = auto()
    AUTHENTICATED = auto()
    MAIL_FROM = auto()
    RCPT_TO = auto()
    DATA = auto()
    CLOSED = auto()


class IMAPState(Enum):
    """IMAP connection state machine states per RFC 3501 Section 3."""
    NOT_AUTHENTICATED = auto()
    AUTHENTICATED = auto()
    SELECTED = auto()
    LOGOUT = auto()


class SMTPCommand(Enum):
    """SMTP commands per RFC 5321 Section 4.1."""
    EHLO = "EHLO"
    HELO = "HELO"
    STARTTLS = "STARTTLS"
    AUTH = "AUTH"
    MAIL = "MAIL"
    RCPT = "RCPT"
    DATA = "DATA"
    RSET = "RSET"
    NOOP = "NOOP"
    VRFY = "VRFY"
    QUIT = "QUIT"


class IMAPCommand(Enum):
    """IMAP commands per RFC 3501 Section 6."""
    CAPABILITY = "CAPABILITY"
    LOGIN = "LOGIN"
    AUTHENTICATE = "AUTHENTICATE"
    LIST = "LIST"
    LSUB = "LSUB"
    CREATE = "CREATE"
    DELETE = "DELETE"
    RENAME = "RENAME"
    SUBSCRIBE = "SUBSCRIBE"
    UNSUBSCRIBE = "UNSUBSCRIBE"
    STATUS = "STATUS"
    SELECT = "SELECT"
    EXAMINE = "EXAMINE"
    FETCH = "FETCH"
    STORE = "STORE"
    COPY = "COPY"
    MOVE = "MOVE"
    SEARCH = "SEARCH"
    UID = "UID"
    EXPUNGE = "EXPUNGE"
    CLOSE = "CLOSE"
    IDLE = "IDLE"
    NAMESPACE = "NAMESPACE"
    NOOP = "NOOP"
    LOGOUT = "LOGOUT"


class AuthMechanism(Enum):
    """SMTP AUTH mechanisms."""
    PLAIN = "PLAIN"
    LOGIN = "LOGIN"
    CRAM_MD5 = "CRAM-MD5"


class QueueStatus(Enum):
    """Message queue entry status."""
    PENDING = auto()
    SENDING = auto()
    SENT = auto()
    DEFERRED = auto()
    BOUNCED = auto()
    FAILED = auto()


class SPFResult(Enum):
    """SPF evaluation results per RFC 7208 Section 2.6."""
    PASS = "pass"
    FAIL = "fail"
    SOFTFAIL = "softfail"
    NEUTRAL = "neutral"
    NONE = "none"
    TEMPERROR = "temperror"
    PERMERROR = "permerror"


class DKIMResult(Enum):
    """DKIM verification results per RFC 6376."""
    PASS = "pass"
    FAIL = "fail"
    TEMPERROR = "temperror"
    PERMERROR = "permerror"
    NONE = "none"


class DMARCPolicy(Enum):
    """DMARC policy actions per RFC 7489."""
    NONE = "none"
    QUARANTINE = "quarantine"
    REJECT = "reject"


class DMARCAlignment(Enum):
    """DMARC identifier alignment modes per RFC 7489 Section 3.1."""
    RELAXED = "r"
    STRICT = "s"


class MIMEMultipartType(Enum):
    """MIME multipart subtypes for structured email bodies."""
    MIXED = "mixed"
    ALTERNATIVE = "alternative"
    RELATED = "related"


class ContentTransferEncoding(Enum):
    """Content-Transfer-Encoding mechanisms per RFC 2045."""
    SEVEN_BIT = "7bit"
    QUOTED_PRINTABLE = "quoted-printable"
    BASE64 = "base64"


class FetchDataItem(Enum):
    """IMAP FETCH data items per RFC 3501 Section 6.4.5."""
    FLAGS = "FLAGS"
    INTERNALDATE = "INTERNALDATE"
    RFC822 = "RFC822"
    RFC822_HEADER = "RFC822.HEADER"
    RFC822_TEXT = "RFC822.TEXT"
    RFC822_SIZE = "RFC822.SIZE"
    ENVELOPE = "ENVELOPE"
    BODY = "BODY"
    BODYSTRUCTURE = "BODYSTRUCTURE"
    UID = "UID"


class IMAPFlagAction(Enum):
    """IMAP STORE flag manipulation actions per RFC 3501 Section 6.4.6."""
    SET = "FLAGS"
    ADD = "+FLAGS"
    REMOVE = "-FLAGS"


# ============================================================
# Dataclasses
# ============================================================


@dataclass
class FizzMailConfig:
    """Configuration for the FizzMail SMTP/IMAP email server.

    Controls all operational parameters including port bindings, security
    features, retry policies, quota limits, and integration settings.
    """
    smtp_port: int = DEFAULT_SMTP_PORT
    imap_port: int = DEFAULT_IMAP_PORT
    domain: str = DEFAULT_DOMAIN
    hostname: str = DEFAULT_HOSTNAME
    enable_tls: bool = True
    enable_auth: bool = True
    enable_dkim_sign: bool = True
    enable_dkim_verify: bool = True
    enable_spf: bool = True
    enable_dmarc: bool = True
    enable_greylist: bool = False
    enable_rbl: bool = False
    max_message_size: int = DEFAULT_MAX_MESSAGE_SIZE
    max_recipients: int = DEFAULT_MAX_RECIPIENTS
    max_line_length: int = DEFAULT_MAX_LINE_LENGTH
    smtp_timeout: float = DEFAULT_SMTP_TIMEOUT
    imap_timeout: float = DEFAULT_IMAP_TIMEOUT
    retry_base_delay: float = DEFAULT_RETRY_BASE_DELAY
    retry_max_delay: float = DEFAULT_RETRY_MAX_DELAY
    retry_max_attempts: int = DEFAULT_RETRY_MAX_ATTEMPTS
    quota_default: int = DEFAULT_QUOTA
    smart_host: Optional[str] = None
    rbl_zones: List[str] = field(default_factory=lambda: ["zen.spamhaus.org", "bl.spamcop.net"])
    dkim_selector: str = DEFAULT_DKIM_SELECTOR
    dkim_private_key: str = DKIM_SIMULATED_PRIVATE_KEY
    greylist_delay: float = DEFAULT_GREYLIST_DELAY
    greylist_ttl: float = DEFAULT_GREYLIST_TTL
    greylist_whitelist_threshold: int = DEFAULT_GREYLIST_WHITELIST_THRESHOLD
    maildir_root: str = "/var/mail/fizzbuzz"
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH
    workers: int = DEFAULT_WORKERS
    credentials: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_CREDENTIALS))


@dataclass
class EmailAddress:
    """Parsed RFC 5322 email address.

    Decomposes a full address string into its constituent parts for
    structured access by envelope processing, header rendering, and
    DKIM/SPF/DMARC domain extraction.
    """
    display_name: str = ""
    local_part: str = ""
    domain: str = ""
    raw: str = ""

    @property
    def address(self) -> str:
        """The bare address (local@domain)."""
        return f"{self.local_part}@{self.domain}" if self.domain else self.local_part

    def __str__(self) -> str:
        if self.display_name:
            return f"{self.display_name} <{self.address}>"
        return self.address


@dataclass
class SMTPResponse:
    """SMTP response code and message per RFC 5321 Section 4.2."""
    code: int
    message: str
    enhanced_code: str = ""

    def __str__(self) -> str:
        if self.enhanced_code:
            return f"{self.code} {self.enhanced_code} {self.message}"
        return f"{self.code} {self.message}"


@dataclass
class Envelope:
    """SMTP envelope containing the sender and recipient addresses.

    The envelope is distinct from the message headers -- it represents
    the MAIL FROM and RCPT TO values from the SMTP transaction, which
    may differ from the From and To headers in the message content.
    """
    mail_from: str = ""
    rcpt_to: List[str] = field(default_factory=list)
    size: int = 0
    body_type: str = "7BIT"


@dataclass
class MIMEPart:
    """MIME body part per RFC 2045.

    Represents a single part in a MIME message structure.  For multipart
    types, the parts list contains nested MIMEPart instances forming a
    tree structure that mirrors the message's MIME hierarchy.
    """
    content_type: str = "text/plain"
    content_transfer_encoding: str = "7bit"
    content_disposition: str = ""
    content_id: str = ""
    filename: str = ""
    charset: str = "utf-8"
    body: str = ""
    parts: List["MIMEPart"] = field(default_factory=list)
    boundary: str = ""

    @property
    def is_multipart(self) -> bool:
        """Whether this part is a multipart container."""
        return self.content_type.startswith("multipart/")


@dataclass
class MailMessage:
    """Complete email message with parsed headers and MIME structure.

    Combines the RFC 5322 header block with the MIME body tree and
    provides access to commonly-needed fields (subject, addresses,
    date) as first-class attributes.
    """
    message_id: str = ""
    date: Optional[datetime] = None
    from_addr: Optional[EmailAddress] = None
    to_addrs: List[EmailAddress] = field(default_factory=list)
    cc_addrs: List[EmailAddress] = field(default_factory=list)
    bcc_addrs: List[EmailAddress] = field(default_factory=list)
    reply_to: Optional[EmailAddress] = None
    subject: str = ""
    headers: Dict[str, str] = field(default_factory=dict)
    body_text: str = ""
    body_html: str = ""
    mime_root: Optional[MIMEPart] = None
    raw: str = ""
    size: int = 0


@dataclass
class QueueEntry:
    """Message queue entry tracking delivery state and retry schedule.

    Each message entering the outbound queue receives a QueueEntry that
    tracks its delivery attempts, exponential backoff schedule, and
    final disposition (sent, bounced, or failed).
    """
    message_id: str = ""
    envelope: Optional[Envelope] = None
    message: Optional[MailMessage] = None
    retry_count: int = 0
    next_retry: float = 0.0
    status: QueueStatus = QueueStatus.PENDING
    created_at: float = 0.0
    last_attempt: float = 0.0
    last_error: str = ""


@dataclass
class MaildirMessage:
    """Message stored in Maildir format.

    Maps a message to its Maildir file location with flags encoded
    in the filename's info suffix per the Maildir specification.
    """
    uid: int = 0
    filename: str = ""
    flags: Set[str] = field(default_factory=set)
    internal_date: Optional[datetime] = None
    size: int = 0
    headers: Dict[str, str] = field(default_factory=dict)
    raw: str = ""
    subject: str = ""
    from_addr: str = ""
    to_addr: str = ""


@dataclass
class Mailbox:
    """IMAP mailbox with message store and UID management.

    Maintains the mailbox's UIDVALIDITY (for detecting mailbox recreation),
    UIDNEXT (next UID to assign), message list, and subscription state.
    """
    name: str = ""
    uidvalidity: int = 0
    uidnext: int = 1
    messages: List[MaildirMessage] = field(default_factory=list)
    subscribed: bool = True
    recent_count: int = 0
    exists: int = 0


@dataclass
class SMTPSession:
    """SMTP session state tracking.

    Maintains the current state machine position, authenticated user,
    accumulated envelope, TLS status, and session metadata for a
    single SMTP connection.
    """
    state: SMTPState = SMTPState.CONNECTED
    client_addr: str = ""
    ehlo_domain: str = ""
    authenticated_user: str = ""
    tls_active: bool = False
    envelope: Optional[Envelope] = None
    message_data: str = ""
    extensions: List[str] = field(default_factory=list)


@dataclass
class IMAPSession:
    """IMAP session state tracking.

    Maintains the current state machine position, authenticated user,
    selected mailbox, and command tag counter for a single IMAP
    connection.
    """
    state: IMAPState = IMAPState.NOT_AUTHENTICATED
    authenticated_user: str = ""
    selected_mailbox: str = ""
    selected_readonly: bool = False
    tag_counter: int = 0


@dataclass
class GreylistEntry:
    """Greylisting triplet tracking entry.

    Records the first and most recent delivery attempt for a
    (sender_ip, sender, recipient) triplet, along with the total
    attempt count and whitelist status.
    """
    first_seen: float = 0.0
    last_seen: float = 0.0
    count: int = 0
    whitelisted: bool = False


@dataclass
class SPFRecord:
    """Parsed SPF record per RFC 7208."""
    version: str = "spf1"
    mechanisms: List["SPFMechanism"] = field(default_factory=list)
    redirect: str = ""
    explanation: str = ""


@dataclass
class SPFMechanism:
    """Single SPF mechanism with qualifier."""
    qualifier: str = "+"
    mechanism_type: str = ""
    value: str = ""


@dataclass
class DKIMSignatureData:
    """Parsed DKIM-Signature header field per RFC 6376."""
    version: str = "1"
    algorithm: str = "rsa-sha256"
    domain: str = ""
    selector: str = ""
    headers_list: List[str] = field(default_factory=list)
    body_hash: str = ""
    signature: str = ""
    canonicalization: str = "relaxed/simple"
    timestamp: int = 0
    expiration: int = 0


@dataclass
class DMARCRecord:
    """Parsed DMARC record per RFC 7489."""
    version: str = "DMARC1"
    policy: DMARCPolicy = DMARCPolicy.NONE
    subdomain_policy: Optional[DMARCPolicy] = None
    rua: str = ""
    ruf: str = ""
    adkim: DMARCAlignment = DMARCAlignment.RELAXED
    aspf: DMARCAlignment = DMARCAlignment.RELAXED
    pct: int = 100


@dataclass
class DSNRecipient:
    """Per-recipient delivery status notification fields per RFC 3464."""
    final_recipient: str = ""
    action: str = "failed"
    status_code: str = "5.0.0"
    diagnostic_code: str = ""
    remote_mta: str = ""


@dataclass
class DSNReport:
    """Delivery Status Notification report per RFC 3464."""
    original_envelope_id: str = ""
    reporting_mta: str = ""
    arrival_date: str = ""
    per_recipient: List[DSNRecipient] = field(default_factory=list)
    original_message_headers: str = ""


@dataclass
class ServerMetrics:
    """Aggregate server metrics for monitoring and dashboard display."""
    messages_received: int = 0
    messages_sent: int = 0
    messages_bounced: int = 0
    messages_queued: int = 0
    active_smtp_sessions: int = 0
    active_imap_sessions: int = 0
    auth_successes: int = 0
    auth_failures: int = 0
    spf_checks: int = 0
    spf_passes: int = 0
    dkim_checks: int = 0
    dkim_passes: int = 0
    dmarc_checks: int = 0
    dmarc_passes: int = 0
    greylist_deferred: int = 0
    rbl_blocked: int = 0
    quota_exceeded: int = 0
    bytes_received: int = 0
    bytes_sent: int = 0


# ============================================================
# RFC 5322 Header Parser
# ============================================================


class RFC5322HeaderParser:
    """Parser for RFC 5322 Internet Message Format headers.

    Handles structured headers (From, To, Cc, Bcc, Date, Message-ID,
    Content-Type), unstructured headers (Subject, Comments), header
    folding/unfolding, and RFC 2047 encoded-word syntax for non-ASCII
    header values.
    """

    # RFC 5322 date pattern (simplified)
    _DATE_PATTERN = re.compile(
        r"(?:(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s+)?"
        r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"\s+(\d{4})\s+(\d{2}):(\d{2})(?::(\d{2}))?"
        r"\s*([+-]\d{4}|[A-Z]{1,5})?"
    )

    _MONTH_MAP = {
        "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
        "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
    }

    _TZ_MAP = {
        "UT": "+0000", "GMT": "+0000", "EST": "-0500", "EDT": "-0400",
        "CST": "-0600", "CDT": "-0500", "MST": "-0700", "MDT": "-0600",
        "PST": "-0800", "PDT": "-0700",
    }

    _ADDR_PATTERN = re.compile(
        r'(?:"([^"]*)"|\s*([^<"]*?))\s*<([^>]+)>|([^\s,;]+@[^\s,;]+)'
    )

    def parse_headers(self, raw: str) -> Dict[str, str]:
        """Parse raw header block into a name-value dictionary.

        Handles header folding (continuation lines starting with
        whitespace) per RFC 5322 Section 2.2.3.
        """
        headers: Dict[str, str] = OrderedDict()
        current_name = ""
        current_value = ""

        for line in raw.split("\n"):
            line = line.rstrip("\r")
            if not line:
                break
            if line[0] in (" ", "\t"):
                # Continuation line
                current_value += " " + line.strip()
            else:
                if current_name:
                    headers[current_name] = current_value
                colon_idx = line.find(":")
                if colon_idx > 0:
                    current_name = line[:colon_idx].strip()
                    current_value = line[colon_idx + 1:].strip()
                else:
                    current_name = ""
                    current_value = ""

        if current_name:
            headers[current_name] = current_value

        return headers

    def parse_address(self, addr_str: str) -> EmailAddress:
        """Parse a single RFC 5322 address into an EmailAddress.

        Supports three formats:
        - Display Name <local@domain>
        - "Quoted Name" <local@domain>
        - local@domain
        """
        addr_str = addr_str.strip()
        match = self._ADDR_PATTERN.search(addr_str)
        if match:
            quoted_name = match.group(1) or ""
            bare_name = match.group(2) or ""
            angle_addr = match.group(3) or ""
            plain_addr = match.group(4) or ""

            if angle_addr:
                display_name = quoted_name or bare_name.strip()
                addr = angle_addr.strip()
            else:
                display_name = ""
                addr = plain_addr.strip()

            if "@" in addr:
                local_part, domain = addr.rsplit("@", 1)
            else:
                local_part = addr
                domain = ""

            return EmailAddress(
                display_name=display_name,
                local_part=local_part,
                domain=domain,
                raw=addr_str,
            )

        return EmailAddress(raw=addr_str)

    def parse_address_list(self, text: str) -> List[EmailAddress]:
        """Parse a comma-separated list of RFC 5322 addresses."""
        addresses = []
        # Split on commas not inside angle brackets or quotes
        depth = 0
        current = ""
        in_quotes = False
        for ch in text:
            if ch == '"' and not in_quotes:
                in_quotes = True
            elif ch == '"' and in_quotes:
                in_quotes = False
            elif ch == '<' and not in_quotes:
                depth += 1
            elif ch == '>' and not in_quotes:
                depth -= 1
            elif ch == ',' and depth == 0 and not in_quotes:
                addr = current.strip()
                if addr:
                    addresses.append(self.parse_address(addr))
                current = ""
                continue
            current += ch

        addr = current.strip()
        if addr:
            addresses.append(self.parse_address(addr))

        return addresses

    def parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse an RFC 5322 date-time string.

        Handles day-of-week prefix, two-digit seconds, and common
        timezone abbreviations.
        """
        match = self._DATE_PATTERN.search(date_str)
        if not match:
            return None

        day = int(match.group(1))
        month = self._MONTH_MAP.get(match.group(2), 1)
        year = int(match.group(3))
        hour = int(match.group(4))
        minute = int(match.group(5))
        second = int(match.group(6)) if match.group(6) else 0

        tz_str = match.group(7) or "+0000"
        tz_str = self._TZ_MAP.get(tz_str, tz_str)

        try:
            sign = 1 if tz_str[0] == '+' else -1
            tz_hours = int(tz_str[1:3])
            tz_minutes = int(tz_str[3:5])
            tz_offset = timezone(timedelta(hours=sign * tz_hours, minutes=sign * tz_minutes))
        except (ValueError, IndexError):
            tz_offset = timezone.utc

        try:
            return datetime(year, month, day, hour, minute, second, tzinfo=tz_offset)
        except ValueError:
            return None

    def format_date(self, dt: Optional[datetime] = None) -> str:
        """Format a datetime as an RFC 5322 date-time string."""
        if dt is None:
            dt = datetime.now(timezone.utc)
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        day_name = days[dt.weekday()]
        month_name = months[dt.month - 1]
        tz_offset = dt.strftime("%z") or "+0000"
        return (
            f"{day_name}, {dt.day:02d} {month_name} {dt.year} "
            f"{dt.hour:02d}:{dt.minute:02d}:{dt.second:02d} {tz_offset}"
        )

    def generate_message_id(self, domain: str) -> str:
        """Generate a globally unique Message-ID per RFC 5322 Section 3.6.4."""
        unique = uuid.uuid4().hex[:16]
        timestamp = int(time.time() * 1000)
        return f"<{timestamp}.{unique}@{domain}>"

    def fold_header(self, name: str, value: str, max_line: int = 78) -> str:
        """Fold a header value to respect line length limits.

        Inserts CRLF followed by a space at appropriate positions
        per RFC 5322 Section 2.2.3.
        """
        full = f"{name}: {value}"
        if len(full) <= max_line:
            return full

        lines = []
        current = f"{name}: "
        for word in value.split():
            if len(current) + len(word) + 1 > max_line and current.strip():
                lines.append(current.rstrip())
                current = " " + word + " "
            else:
                current += word + " "
        if current.strip():
            lines.append(current.rstrip())

        return "\r\n".join(lines)

    def unfold_header(self, text: str) -> str:
        """Unfold a header value by joining continuation lines."""
        return re.sub(r"\r?\n[ \t]+", " ", text)

    def encode_header(self, name: str, value: str, charset: str = "utf-8") -> str:
        """Encode a header value using RFC 2047 encoded-word syntax.

        Non-ASCII characters are encoded as =?charset?B?base64?= tokens.
        """
        try:
            value.encode("ascii")
            return f"{name}: {value}"
        except UnicodeEncodeError:
            encoded = base64.b64encode(value.encode(charset)).decode("ascii")
            return f"{name}: =?{charset}?B?{encoded}?="

    def decode_encoded_word(self, text: str) -> str:
        """Decode RFC 2047 encoded-word tokens in a header value."""
        pattern = re.compile(r'=\?([^?]+)\?([BbQq])\?([^?]+)\?=')

        def _decode_match(m):
            charset = m.group(1)
            encoding = m.group(2).upper()
            payload = m.group(3)
            if encoding == "B":
                decoded = base64.b64decode(payload)
            else:
                # Quoted-printable
                decoded = bytes(
                    int(payload[i + 1:i + 3], 16) if payload[i] == '='
                    else ord(payload[i])
                    for i in range(len(payload))
                    if payload[i] != '=' or i + 2 < len(payload)
                )
            try:
                return decoded.decode(charset)
            except (UnicodeDecodeError, LookupError):
                return m.group(0)

        return pattern.sub(_decode_match, text)


# ============================================================
# MIME Builder
# ============================================================


class MIMEBuilder:
    """MIME message construction and parsing engine.

    Builds structured email messages with multipart bodies (mixed,
    alternative, related), content transfer encoding (base64,
    quoted-printable, 7bit), and attachment handling.  Also parses
    raw MIME messages into a MIMEPart tree for IMAP BODYSTRUCTURE.
    """

    def generate_boundary(self) -> str:
        """Generate a unique MIME boundary string.

        Uses UUID-based generation to ensure the boundary does not
        appear in message content.
        """
        return f"----=_FizzMail_{uuid.uuid4().hex}"

    def build_simple(self, content_type: str, body: str,
                     charset: str = "utf-8") -> MIMEPart:
        """Build a single-part MIME message."""
        try:
            body.encode("ascii")
            encoding = "7bit"
        except UnicodeEncodeError:
            encoding = "quoted-printable"
            body = self.encode_quoted_printable(body)

        return MIMEPart(
            content_type=content_type,
            content_transfer_encoding=encoding,
            charset=charset,
            body=body,
        )

    def build_multipart(self, multipart_type: MIMEMultipartType,
                        parts: List[MIMEPart]) -> MIMEPart:
        """Build a multipart MIME container."""
        boundary = self.generate_boundary()
        return MIMEPart(
            content_type=f"multipart/{multipart_type.value}",
            boundary=boundary,
            parts=parts,
        )

    def build_attachment(self, filename: str, content: bytes,
                         content_type: str = "application/octet-stream") -> MIMEPart:
        """Build a MIME attachment part with base64 encoding."""
        encoded = self.encode_base64(content)
        return MIMEPart(
            content_type=content_type,
            content_transfer_encoding="base64",
            content_disposition=f'attachment; filename="{filename}"',
            filename=filename,
            body=encoded,
        )

    def encode_base64(self, data: Union[bytes, str]) -> str:
        """Encode data using base64 transfer encoding per RFC 2045."""
        if isinstance(data, str):
            data = data.encode("utf-8")
        encoded = base64.b64encode(data).decode("ascii")
        # Wrap at 76 characters per RFC 2045
        lines = [encoded[i:i + 76] for i in range(0, len(encoded), 76)]
        return "\r\n".join(lines)

    def decode_base64(self, data: str) -> bytes:
        """Decode base64 transfer encoding."""
        cleaned = data.replace("\r", "").replace("\n", "").replace(" ", "")
        try:
            return base64.b64decode(cleaned)
        except Exception as e:
            raise FizzMailEncodingError("base64", str(e))

    def encode_quoted_printable(self, text: str) -> str:
        """Encode text using quoted-printable transfer encoding per RFC 2045."""
        result = []
        for char in text:
            code = ord(char)
            if char == "\r" or char == "\n":
                result.append(char)
            elif 33 <= code <= 126 and char != "=":
                result.append(char)
            elif char == " " or char == "\t":
                result.append(char)
            else:
                for byte in char.encode("utf-8"):
                    result.append(f"={byte:02X}")
        return "".join(result)

    def decode_quoted_printable(self, text: str) -> str:
        """Decode quoted-printable transfer encoding."""
        result = []
        i = 0
        while i < len(text):
            if text[i] == "=" and i + 2 < len(text):
                if text[i + 1] == "\r" or text[i + 1] == "\n":
                    # Soft line break
                    i += 2
                    if i < len(text) and text[i] == "\n":
                        i += 1
                    continue
                try:
                    byte_val = int(text[i + 1:i + 3], 16)
                    result.append(chr(byte_val))
                    i += 3
                except ValueError:
                    result.append(text[i])
                    i += 1
            else:
                result.append(text[i])
                i += 1
        return "".join(result)

    def build_message(self, mail_message: MailMessage, config: "FizzMailConfig") -> str:
        """Build a complete RFC 5322 message from a MailMessage.

        Constructs the header block and MIME body, applying content
        transfer encoding as needed.
        """
        parser = RFC5322HeaderParser()
        lines = []

        # Required headers
        if not mail_message.message_id:
            mail_message.message_id = parser.generate_message_id(config.domain)
        if not mail_message.date:
            mail_message.date = datetime.now(timezone.utc)

        lines.append(f"Message-ID: {mail_message.message_id}")
        lines.append(f"Date: {parser.format_date(mail_message.date)}")

        if mail_message.from_addr:
            lines.append(f"From: {mail_message.from_addr}")
        if mail_message.to_addrs:
            lines.append(f"To: {', '.join(str(a) for a in mail_message.to_addrs)}")
        if mail_message.cc_addrs:
            lines.append(f"Cc: {', '.join(str(a) for a in mail_message.cc_addrs)}")
        if mail_message.subject:
            lines.append(parser.encode_header("Subject", mail_message.subject))
        if mail_message.reply_to:
            lines.append(f"Reply-To: {mail_message.reply_to}")

        lines.append(f"MIME-Version: 1.0")
        lines.append(f"X-Mailer: {FIZZMAIL_SERVER_NAME}")

        # Body
        if mail_message.body_html and mail_message.body_text:
            boundary = self.generate_boundary()
            lines.append(f'Content-Type: multipart/alternative; boundary="{boundary}"')
            lines.append("")
            lines.append(f"--{boundary}")
            lines.append("Content-Type: text/plain; charset=utf-8")
            lines.append("Content-Transfer-Encoding: 7bit")
            lines.append("")
            lines.append(mail_message.body_text)
            lines.append(f"--{boundary}")
            lines.append("Content-Type: text/html; charset=utf-8")
            lines.append("Content-Transfer-Encoding: 7bit")
            lines.append("")
            lines.append(mail_message.body_html)
            lines.append(f"--{boundary}--")
        elif mail_message.body_text:
            lines.append("Content-Type: text/plain; charset=utf-8")
            lines.append("Content-Transfer-Encoding: 7bit")
            lines.append("")
            lines.append(mail_message.body_text)
        elif mail_message.body_html:
            lines.append("Content-Type: text/html; charset=utf-8")
            lines.append("Content-Transfer-Encoding: 7bit")
            lines.append("")
            lines.append(mail_message.body_html)
        else:
            lines.append("Content-Type: text/plain; charset=utf-8")
            lines.append("Content-Transfer-Encoding: 7bit")
            lines.append("")

        raw = "\r\n".join(lines)
        mail_message.raw = raw
        mail_message.size = len(raw)
        return raw

    def parse_mime(self, raw: str) -> MIMEPart:
        """Parse a raw MIME message into a MIMEPart tree.

        Splits the message at the header/body boundary, parses
        Content-Type for multipart boundaries, and recursively
        parses nested parts.
        """
        header_end = raw.find("\r\n\r\n")
        if header_end == -1:
            header_end = raw.find("\n\n")
            if header_end == -1:
                return MIMEPart(body=raw)

        header_block = raw[:header_end]
        body = raw[header_end:].lstrip("\r\n")

        parser = RFC5322HeaderParser()
        headers = parser.parse_headers(header_block)

        content_type = headers.get("Content-Type", "text/plain")
        charset = "utf-8"
        boundary = ""

        # Parse Content-Type parameters
        ct_parts = content_type.split(";")
        main_type = ct_parts[0].strip()
        for param in ct_parts[1:]:
            param = param.strip()
            if param.lower().startswith("charset="):
                charset = param.split("=", 1)[1].strip().strip('"')
            elif param.lower().startswith("boundary="):
                boundary = param.split("=", 1)[1].strip().strip('"')

        encoding = headers.get("Content-Transfer-Encoding", "7bit").strip()
        disposition = headers.get("Content-Disposition", "")

        part = MIMEPart(
            content_type=main_type,
            content_transfer_encoding=encoding,
            content_disposition=disposition,
            charset=charset,
            boundary=boundary,
        )

        if main_type.startswith("multipart/") and boundary:
            # Split body on boundary
            parts_raw = body.split(f"--{boundary}")
            for part_raw in parts_raw[1:]:
                if part_raw.startswith("--"):
                    break  # Closing boundary
                sub_part = self.parse_mime(part_raw.strip())
                part.parts.append(sub_part)
        else:
            part.body = body

        return part

    def build_bodystructure(self, mime_part: MIMEPart) -> str:
        """Build an IMAP BODYSTRUCTURE response string for a MIME part."""
        if mime_part.is_multipart:
            sub_type = mime_part.content_type.split("/", 1)[1] if "/" in mime_part.content_type else "mixed"
            parts_str = " ".join(self.build_bodystructure(p) for p in mime_part.parts)
            return f'({parts_str} "{sub_type.upper()}")'
        else:
            ct_main, ct_sub = "TEXT", "PLAIN"
            if "/" in mime_part.content_type:
                ct_main, ct_sub = mime_part.content_type.upper().split("/", 1)
            charset = mime_part.charset.upper()
            encoding = mime_part.content_transfer_encoding.upper()
            size = len(mime_part.body)
            lines = mime_part.body.count("\n") + 1
            return f'("{ct_main}" "{ct_sub}" ("CHARSET" "{charset}") NIL NIL "{encoding}" {size} {lines})'


# ============================================================
# SMTP TLS Handler
# ============================================================


class SMTPTLSHandler:
    """STARTTLS upgrade handler for SMTP connections.

    Simulates the TLS handshake sequence including cipher suite
    negotiation, certificate exchange, and session establishment.
    The actual cryptographic operations are simulated in-memory,
    consistent with the platform's network simulation pattern.
    """

    SUPPORTED_CIPHERS = [
        "TLS_AES_256_GCM_SHA384",
        "TLS_CHACHA20_POLY1305_SHA256",
        "TLS_AES_128_GCM_SHA256",
    ]

    def __init__(self, config: FizzMailConfig) -> None:
        self._config = config
        self._tls_sessions: Dict[str, Dict[str, Any]] = {}

    def handle_starttls(self, session: SMTPSession) -> SMTPSession:
        """Simulate TLS upgrade for an SMTP session.

        Negotiates cipher suite, exchanges certificates, and
        transitions the session to TLS_NEGOTIATED state.
        """
        if session.tls_active:
            raise FizzMailTLSError("TLS already active on this connection")

        cipher = self.SUPPORTED_CIPHERS[0]
        session_id = uuid.uuid4().hex[:16]

        self._tls_sessions[session_id] = {
            "cipher": cipher,
            "protocol": "TLSv1.3",
            "peer_cert_subject": f"CN={session.client_addr}",
            "established": time.time(),
        }

        session.tls_active = True
        session.state = SMTPState.TLS_NEGOTIATED
        # Reset session per RFC 3207 Section 4.2
        session.ehlo_domain = ""
        session.authenticated_user = ""
        session.envelope = None

        logger.info(
            "STARTTLS completed: cipher=%s protocol=TLSv1.3 session=%s",
            cipher, session_id,
        )

        return session

    def is_tls_active(self, session: SMTPSession) -> bool:
        """Check whether TLS is active on a session."""
        return session.tls_active


# ============================================================
# SMTP Authenticator
# ============================================================


class SMTPAuthenticator:
    """SMTP AUTH mechanism handler.

    Implements three SASL authentication mechanisms:
    - PLAIN (RFC 4616): Single base64-encoded response
    - LOGIN: Two-step challenge/response
    - CRAM-MD5 (RFC 2195): HMAC-MD5 challenge/response

    Validates credentials against a configurable credential store.
    """

    def __init__(self, credentials: Dict[str, str]) -> None:
        self._credentials = credentials
        self._challenges: Dict[str, str] = {}

    def authenticate_plain(self, encoded: str) -> Tuple[bool, str]:
        """Authenticate using SASL PLAIN mechanism.

        Decodes base64 payload as \\0authzid\\0authcid\\0password,
        validates against the credential store.
        """
        try:
            decoded = base64.b64decode(encoded).decode("utf-8")
        except Exception:
            return False, ""

        parts = decoded.split("\0")
        if len(parts) != 3:
            return False, ""

        _authzid, authcid, password = parts
        return self._verify_credentials(authcid, password), authcid

    def authenticate_login_challenge(self) -> str:
        """Return the initial LOGIN challenge (Username:)."""
        return base64.b64encode(b"Username:").decode("ascii")

    def authenticate_login_password_challenge(self) -> str:
        """Return the password LOGIN challenge (Password:)."""
        return base64.b64encode(b"Password:").decode("ascii")

    def authenticate_login(self, username_b64: str, password_b64: str) -> Tuple[bool, str]:
        """Authenticate using LOGIN mechanism.

        Decodes base64-encoded username and password, validates
        against the credential store.
        """
        try:
            username = base64.b64decode(username_b64).decode("utf-8")
            password = base64.b64decode(password_b64).decode("utf-8")
        except Exception:
            return False, ""

        return self._verify_credentials(username, password), username

    def generate_cram_md5_challenge(self) -> Tuple[str, str]:
        """Generate a CRAM-MD5 challenge.

        Returns (challenge_b64, challenge_raw) where the raw challenge
        is stored for later verification.
        """
        timestamp = int(time.time())
        pid = os.getpid()
        challenge = f"<{timestamp}.{pid}@{DEFAULT_HOSTNAME}>"
        challenge_b64 = base64.b64encode(challenge.encode("utf-8")).decode("ascii")
        challenge_id = uuid.uuid4().hex
        self._challenges[challenge_id] = challenge
        return challenge_b64, challenge_id

    def authenticate_cram_md5(self, challenge_id: str, response_b64: str) -> Tuple[bool, str]:
        """Authenticate using CRAM-MD5 mechanism.

        Verifies the HMAC-MD5 response against the stored challenge
        and credential store.
        """
        challenge = self._challenges.pop(challenge_id, None)
        if challenge is None:
            return False, ""

        try:
            decoded = base64.b64decode(response_b64).decode("utf-8")
        except Exception:
            return False, ""

        parts = decoded.rsplit(" ", 1)
        if len(parts) != 2:
            return False, ""

        username, client_digest = parts

        password = self._credentials.get(username)
        if password is None:
            return False, username

        expected = hmac.new(
            password.encode("utf-8"),
            challenge.encode("utf-8"),
            hashlib.md5,
        ).hexdigest()

        return hmac.compare_digest(expected, client_digest), username

    def _verify_credentials(self, username: str, password: str) -> bool:
        """Verify username/password against the credential store."""
        stored = self._credentials.get(username)
        if stored is None:
            return False
        return hmac.compare_digest(stored, password)


# ============================================================
# Message Queue
# ============================================================


class MessageQueue:
    """Persistent message queue with exponential-backoff retry scheduling.

    Manages the lifecycle of outbound messages from enqueue through
    delivery or failure.  Each message progresses through states:
    PENDING -> SENDING -> SENT (success) or DEFERRED -> retry -> BOUNCED/FAILED.
    """

    def __init__(self, config: FizzMailConfig) -> None:
        self._config = config
        self._entries: Dict[str, QueueEntry] = OrderedDict()
        self._lock = threading.Lock()
        self._total_enqueued = 0
        self._total_sent = 0
        self._total_bounced = 0
        self._total_failed = 0

    def enqueue(self, envelope: Envelope, message: MailMessage) -> str:
        """Add a message to the delivery queue.

        Returns the assigned message ID for tracking.
        """
        message_id = message.message_id or f"<queue-{uuid.uuid4().hex[:12]}@{self._config.domain}>"
        now = time.time()

        entry = QueueEntry(
            message_id=message_id,
            envelope=envelope,
            message=message,
            retry_count=0,
            next_retry=now,
            status=QueueStatus.PENDING,
            created_at=now,
            last_attempt=0.0,
        )

        with self._lock:
            self._entries[message_id] = entry
            self._total_enqueued += 1

        logger.info("Message queued: %s to=%s", message_id, envelope.rcpt_to)
        return message_id

    def dequeue(self, message_id: str) -> Optional[QueueEntry]:
        """Remove and return a message from the queue."""
        with self._lock:
            return self._entries.pop(message_id, None)

    def get_entry(self, message_id: str) -> Optional[QueueEntry]:
        """Retrieve a queue entry by message ID without removing it."""
        return self._entries.get(message_id)

    def process_queue(self, relay_router: "RelayRouter") -> List[str]:
        """Process all pending and deferred entries that are due for delivery.

        Returns a list of message IDs that were successfully delivered.
        """
        now = time.time()
        delivered = []

        entries_to_process = []
        with self._lock:
            for msg_id, entry in list(self._entries.items()):
                if entry.status in (QueueStatus.PENDING, QueueStatus.DEFERRED):
                    if entry.next_retry <= now:
                        entry.status = QueueStatus.SENDING
                        entry.last_attempt = now
                        entries_to_process.append(entry)

        for entry in entries_to_process:
            try:
                relay_router.deliver(entry.envelope, entry.message)
                self.mark_sent(entry.message_id)
                delivered.append(entry.message_id)
            except FizzMailRelayError as e:
                if entry.retry_count < self._config.retry_max_attempts:
                    self.schedule_retry(entry)
                else:
                    self.mark_bounced(entry.message_id, str(e))

        return delivered

    def schedule_retry(self, entry: QueueEntry) -> None:
        """Schedule the next delivery retry with exponential backoff."""
        entry.retry_count += 1
        backoff = self._calculate_backoff(entry.retry_count)
        entry.next_retry = time.time() + backoff
        entry.status = QueueStatus.DEFERRED
        logger.info(
            "Message deferred: %s retry=%d next_retry_in=%.0fs",
            entry.message_id, entry.retry_count, backoff,
        )

    def mark_sent(self, message_id: str) -> None:
        """Mark a message as successfully delivered."""
        entry = self._entries.get(message_id)
        if entry:
            entry.status = QueueStatus.SENT
            self._total_sent += 1
            logger.info("Message sent: %s", message_id)

    def mark_deferred(self, message_id: str, reason: str) -> None:
        """Mark a message as deferred for later retry."""
        entry = self._entries.get(message_id)
        if entry:
            entry.status = QueueStatus.DEFERRED
            entry.last_error = reason

    def mark_bounced(self, message_id: str, reason: str) -> None:
        """Mark a message as permanently bounced."""
        entry = self._entries.get(message_id)
        if entry:
            entry.status = QueueStatus.BOUNCED
            entry.last_error = reason
            self._total_bounced += 1
            logger.warning("Message bounced: %s reason=%s", message_id, reason)

    def mark_failed(self, message_id: str, reason: str) -> None:
        """Mark a message as permanently failed."""
        entry = self._entries.get(message_id)
        if entry:
            entry.status = QueueStatus.FAILED
            entry.last_error = reason
            self._total_failed += 1

    def get_pending(self) -> List[QueueEntry]:
        """Return all pending entries."""
        return [e for e in self._entries.values() if e.status == QueueStatus.PENDING]

    def get_queue_stats(self) -> Dict[str, int]:
        """Return queue statistics by status."""
        stats: Dict[str, int] = defaultdict(int)
        for entry in self._entries.values():
            stats[entry.status.name] += 1
        stats["total_enqueued"] = self._total_enqueued
        stats["total_sent"] = self._total_sent
        stats["total_bounced"] = self._total_bounced
        stats["total_failed"] = self._total_failed
        return dict(stats)

    def _calculate_backoff(self, retry_count: int) -> float:
        """Calculate exponential backoff delay for a retry attempt."""
        delay = self._config.retry_base_delay * (2 ** (retry_count - 1))
        # Add jitter (10%)
        jitter = delay * 0.1 * random.random()
        return min(delay + jitter, self._config.retry_max_delay)

    @property
    def size(self) -> int:
        """Number of entries currently in the queue."""
        return len(self._entries)


# ============================================================
# Relay Router
# ============================================================


class RelayRouter:
    """Outbound mail relay router.

    Determines whether a message should be delivered locally (to the
    Maildir store) or relayed to a remote MTA via MX record lookup
    or smart host routing.
    """

    def __init__(self, config: FizzMailConfig, storage: "MaildirStorage",
                 dns_resolver: Any = None) -> None:
        self._config = config
        self._storage = storage
        self._dns_resolver = dns_resolver
        self._delivery_log: List[Dict[str, Any]] = []

    def deliver(self, envelope: Envelope, message: MailMessage) -> None:
        """Route and deliver a message to all recipients."""
        for recipient in envelope.rcpt_to:
            domain = recipient.split("@", 1)[1] if "@" in recipient else ""

            if domain == self._config.domain:
                self._deliver_local(recipient, message)
            elif self._config.smart_host:
                self._deliver_via_smart_host(envelope, message, recipient)
            else:
                self._deliver_remote(envelope, message, recipient)

    def _deliver_local(self, recipient: str, message: MailMessage) -> None:
        """Deliver a message to a local mailbox."""
        local_part = recipient.split("@")[0] if "@" in recipient else recipient
        user = f"{local_part}@{self._config.domain}"

        try:
            self._storage.deliver(user, "INBOX", message)
            self._delivery_log.append({
                "recipient": recipient,
                "method": "local",
                "status": "delivered",
                "timestamp": time.time(),
            })
            logger.info("Local delivery: %s -> %s/INBOX", message.message_id, user)
        except FizzMailQuotaError:
            raise FizzMailRelayError(recipient, "Mailbox quota exceeded")

    def _deliver_remote(self, envelope: Envelope, message: MailMessage,
                        recipient: str) -> None:
        """Deliver a message to a remote MTA via MX record lookup."""
        domain = recipient.split("@", 1)[1] if "@" in recipient else ""
        mx_records = self._lookup_mx(domain)

        if not mx_records:
            raise FizzMailRelayError(recipient, f"No MX records for {domain}")

        # Simulate delivery to highest-priority MX
        mx_host = mx_records[0][1]
        self._connect_to_mx(mx_host, envelope, message, recipient)

    def _deliver_via_smart_host(self, envelope: Envelope, message: MailMessage,
                                recipient: str) -> None:
        """Deliver a message via the configured smart host."""
        self._connect_to_mx(self._config.smart_host, envelope, message, recipient)

    def _lookup_mx(self, domain: str) -> List[Tuple[int, str]]:
        """Query DNS for MX records, sorted by priority (lowest first).

        Falls back to the domain's A record if no MX records exist.
        """
        if self._dns_resolver is not None:
            try:
                records = self._dns_resolver.resolve(domain, "MX")
                return sorted(records, key=lambda r: r[0])
            except Exception:
                pass

        # Simulated MX records for known domains
        simulated_mx = {
            "fizzbuzz.local": [(10, "mail.fizzbuzz.local")],
            "example.com": [(10, "mx1.example.com"), (20, "mx2.example.com")],
            "gmail.com": [(5, "gmail-smtp-in.l.google.com"), (10, "alt1.gmail-smtp-in.l.google.com")],
        }

        return simulated_mx.get(domain, [(10, f"mail.{domain}")])

    def _connect_to_mx(self, mx_host: str, envelope: Envelope,
                       message: MailMessage, recipient: str) -> None:
        """Simulate an SMTP relay session to a remote MTA."""
        logger.info(
            "Relay delivery: %s -> %s via %s",
            message.message_id, recipient, mx_host,
        )

        self._delivery_log.append({
            "recipient": recipient,
            "method": "relay",
            "mx_host": mx_host,
            "status": "delivered",
            "timestamp": time.time(),
        })

    @property
    def delivery_log(self) -> List[Dict[str, Any]]:
        """Access the delivery audit log."""
        return list(self._delivery_log)


# ============================================================
# SPF Validator
# ============================================================


class SPFValidator:
    """Sender Policy Framework validation engine per RFC 7208.

    Evaluates SPF records by querying DNS TXT records, parsing SPF
    mechanism lists, and matching the connecting client's IP address
    against each mechanism in order.
    """

    MAX_DNS_LOOKUPS = 10

    def __init__(self, dns_resolver: Any = None) -> None:
        self._dns_resolver = dns_resolver
        self._lookup_count = 0

    def validate(self, client_ip: str, mail_from: str,
                 ehlo_domain: str = "") -> SPFResult:
        """Evaluate SPF for a message.

        Looks up the SPF record for the sender's domain and evaluates
        the client IP against the mechanism list.
        """
        self._lookup_count = 0

        if not mail_from or "@" not in mail_from:
            return SPFResult.NONE

        domain = mail_from.split("@", 1)[1]

        try:
            record = self._lookup_spf_record(domain)
        except FizzMailSPFTempError:
            return SPFResult.TEMPERROR
        except FizzMailSPFPermError:
            return SPFResult.PERMERROR

        if record is None:
            return SPFResult.NONE

        try:
            return self._evaluate_mechanisms(record, client_ip, domain, 0)
        except FizzMailSPFTempError:
            return SPFResult.TEMPERROR
        except FizzMailSPFPermError:
            return SPFResult.PERMERROR

    def _lookup_spf_record(self, domain: str) -> Optional[SPFRecord]:
        """Query DNS for SPF TXT record."""
        self._lookup_count += 1
        if self._lookup_count > self.MAX_DNS_LOOKUPS:
            raise FizzMailSPFPermError(domain, "Too many DNS lookups")

        # Simulated SPF records
        simulated_records = {
            "fizzbuzz.local": "v=spf1 ip4:10.0.0.0/8 ip4:192.168.0.0/16 a mx ~all",
            "example.com": "v=spf1 ip4:203.0.113.0/24 include:_spf.example.com -all",
            "gmail.com": "v=spf1 include:_netblocks.google.com ~all",
        }

        txt = simulated_records.get(domain)
        if txt is None:
            if self._dns_resolver is not None:
                try:
                    records = self._dns_resolver.resolve(domain, "TXT")
                    for rec in records:
                        if rec.startswith("v=spf1"):
                            txt = rec
                            break
                except Exception:
                    return None
            if txt is None:
                return None

        return self._parse_spf_record(txt)

    def _parse_spf_record(self, txt: str) -> SPFRecord:
        """Parse an SPF TXT record into an SPFRecord."""
        record = SPFRecord()
        tokens = txt.split()

        if not tokens or tokens[0] != "v=spf1":
            raise FizzMailSPFPermError("", "Invalid SPF version")

        for token in tokens[1:]:
            if token.startswith("redirect="):
                record.redirect = token.split("=", 1)[1]
                continue
            if token.startswith("exp="):
                record.explanation = token.split("=", 1)[1]
                continue

            qualifier = "+"
            if token[0] in "+-~?":
                qualifier = token[0]
                token = token[1:]

            if ":" in token:
                mtype, value = token.split(":", 1)
            elif token in ("all", "a", "mx"):
                mtype = token
                value = ""
            else:
                mtype = token
                value = ""

            record.mechanisms.append(SPFMechanism(
                qualifier=qualifier,
                mechanism_type=mtype,
                value=value,
            ))

        return record

    def _evaluate_mechanisms(self, record: SPFRecord, client_ip: str,
                             domain: str, depth: int) -> SPFResult:
        """Evaluate SPF mechanisms against the client IP."""
        if depth > 10:
            raise FizzMailSPFPermError(domain, "Excessive recursion depth")

        for mech in record.mechanisms:
            matched = False

            if mech.mechanism_type == "all":
                matched = True
            elif mech.mechanism_type == "ip4":
                matched = self._match_ip4(mech, client_ip)
            elif mech.mechanism_type == "ip6":
                matched = self._match_ip6(mech, client_ip)
            elif mech.mechanism_type == "a":
                matched = self._match_a(mech, domain, client_ip)
            elif mech.mechanism_type == "mx":
                matched = self._match_mx(mech, domain, client_ip)
            elif mech.mechanism_type == "include":
                sub_record = self._lookup_spf_record(mech.value)
                if sub_record:
                    result = self._evaluate_mechanisms(sub_record, client_ip, mech.value, depth + 1)
                    if result == SPFResult.PASS:
                        matched = True

            if matched:
                return self._qualifier_to_result(mech.qualifier)

        # Handle redirect
        if record.redirect:
            sub_record = self._lookup_spf_record(record.redirect)
            if sub_record:
                return self._evaluate_mechanisms(sub_record, client_ip, record.redirect, depth + 1)

        return SPFResult.NEUTRAL

    def _match_ip4(self, mech: SPFMechanism, client_ip: str) -> bool:
        """Match client IP against an ip4 mechanism."""
        value = mech.value
        if "/" in value:
            network, prefix = value.rsplit("/", 1)
            prefix_len = int(prefix)
        else:
            network = value
            prefix_len = 32

        return self._ip_in_network(client_ip, network, prefix_len)

    def _match_ip6(self, mech: SPFMechanism, client_ip: str) -> bool:
        """Match client IP against an ip6 mechanism."""
        # Simplified -- only exact match for simulation
        return client_ip == mech.value

    def _match_a(self, mech: SPFMechanism, domain: str, client_ip: str) -> bool:
        """Match client IP against the domain's A record."""
        target = mech.value or domain
        # Simulated A record resolution
        simulated_a = {
            "fizzbuzz.local": "10.0.0.1",
            "mail.fizzbuzz.local": "10.0.0.2",
            "example.com": "203.0.113.1",
        }
        resolved = simulated_a.get(target, "")
        return resolved == client_ip

    def _match_mx(self, mech: SPFMechanism, domain: str, client_ip: str) -> bool:
        """Match client IP against the domain's MX host A records."""
        target = mech.value or domain
        # Simulated MX resolution
        simulated_mx_ips = {
            "fizzbuzz.local": ["10.0.0.2"],
            "example.com": ["203.0.113.10", "203.0.113.11"],
        }
        mx_ips = simulated_mx_ips.get(target, [])
        return client_ip in mx_ips

    def _ip_in_network(self, ip: str, network: str, prefix_len: int) -> bool:
        """Check if an IPv4 address is within a CIDR network."""
        try:
            ip_parts = [int(p) for p in ip.split(".")]
            net_parts = [int(p) for p in network.split(".")]
            if len(ip_parts) != 4 or len(net_parts) != 4:
                return False

            ip_int = (ip_parts[0] << 24) | (ip_parts[1] << 16) | (ip_parts[2] << 8) | ip_parts[3]
            net_int = (net_parts[0] << 24) | (net_parts[1] << 16) | (net_parts[2] << 8) | net_parts[3]
            mask = ((1 << 32) - 1) << (32 - prefix_len) & 0xFFFFFFFF

            return (ip_int & mask) == (net_int & mask)
        except (ValueError, IndexError):
            return False

    @staticmethod
    def _qualifier_to_result(qualifier: str) -> SPFResult:
        """Convert an SPF qualifier to an SPFResult."""
        return {
            "+": SPFResult.PASS,
            "-": SPFResult.FAIL,
            "~": SPFResult.SOFTFAIL,
            "?": SPFResult.NEUTRAL,
        }.get(qualifier, SPFResult.NEUTRAL)


# ============================================================
# DKIM Signer
# ============================================================


class DKIMSigner:
    """DKIM message signing engine per RFC 6376.

    Signs outbound messages using RSA-SHA256 with configurable
    header canonicalization (relaxed or simple).  The RSA signing
    operation is simulated using deterministic HMAC-SHA256, consistent
    with the platform's cryptographic simulation pattern.
    """

    DEFAULT_HEADERS_TO_SIGN = [
        "From", "To", "Subject", "Date", "Message-ID",
        "MIME-Version", "Content-Type",
    ]

    def __init__(self, domain: str, selector: str,
                 private_key: str = DKIM_SIMULATED_PRIVATE_KEY) -> None:
        self._domain = domain
        self._selector = selector
        self._private_key = private_key

    def sign(self, message: MailMessage,
             headers_to_sign: Optional[List[str]] = None) -> str:
        """Generate a DKIM-Signature header for a message.

        Returns the complete DKIM-Signature header value ready for
        insertion into the message headers.
        """
        if headers_to_sign is None:
            headers_to_sign = self.DEFAULT_HEADERS_TO_SIGN

        # Canonicalize body
        body = message.body_text or message.body_html or ""
        body_canon = self._canonicalize_body_relaxed(body)
        body_hash = base64.b64encode(
            hashlib.sha256(body_canon.encode("utf-8")).digest()
        ).decode("ascii")

        # Canonicalize headers
        header_canon_parts = []
        for hname in headers_to_sign:
            value = message.headers.get(hname, "")
            if not value and hname == "From" and message.from_addr:
                value = str(message.from_addr)
            elif not value and hname == "To" and message.to_addrs:
                value = ", ".join(str(a) for a in message.to_addrs)
            elif not value and hname == "Subject":
                value = message.subject
            elif not value and hname == "Date" and message.date:
                value = RFC5322HeaderParser().format_date(message.date)
            elif not value and hname == "Message-ID":
                value = message.message_id
            header_canon_parts.append(
                self._canonicalize_header_relaxed(hname, value)
            )

        # Build the DKIM-Signature header (without b= value)
        timestamp = int(time.time())
        dkim_params = {
            "v": "1",
            "a": "rsa-sha256",
            "c": "relaxed/relaxed",
            "d": self._domain,
            "s": self._selector,
            "t": str(timestamp),
            "h": ":".join(h.lower() for h in headers_to_sign),
            "bh": body_hash,
            "b": "",
        }

        dkim_header_value = "; ".join(f"{k}={v}" for k, v in dkim_params.items())
        header_canon_parts.append(
            self._canonicalize_header_relaxed("dkim-signature", dkim_header_value)
        )

        # Compute signature (simulated RSA-SHA256 via HMAC)
        header_hash_input = "\r\n".join(header_canon_parts)
        signature = hmac.new(
            self._private_key.encode("utf-8"),
            header_hash_input.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        signature_b64 = base64.b64encode(signature).decode("ascii")

        dkim_params["b"] = signature_b64
        return "; ".join(f"{k}={v}" for k, v in dkim_params.items())

    def _canonicalize_header_relaxed(self, name: str, value: str) -> str:
        """Relaxed header canonicalization per RFC 6376 Section 3.4.2."""
        name = name.lower().strip()
        value = re.sub(r"\s+", " ", value).strip()
        return f"{name}:{value}"

    def _canonicalize_header_simple(self, name: str, value: str) -> str:
        """Simple header canonicalization per RFC 6376 Section 3.4.1."""
        return f"{name}:{value}"

    def _canonicalize_body_relaxed(self, body: str) -> str:
        """Relaxed body canonicalization per RFC 6376 Section 3.4.4."""
        lines = body.split("\n")
        result = []
        for line in lines:
            line = line.rstrip("\r")
            line = re.sub(r"[ \t]+", " ", line)
            line = line.rstrip(" ")
            result.append(line)
        # Remove trailing empty lines
        while result and result[-1] == "":
            result.pop()
        return "\r\n".join(result) + "\r\n"

    def _canonicalize_body_simple(self, body: str) -> str:
        """Simple body canonicalization per RFC 6376 Section 3.4.3."""
        body = body.replace("\r\n", "\n").replace("\n", "\r\n")
        while body.endswith("\r\n\r\n"):
            body = body[:-2]
        if not body.endswith("\r\n"):
            body += "\r\n"
        return body


# ============================================================
# DKIM Verifier
# ============================================================


class DKIMVerifier:
    """DKIM signature verification engine per RFC 6376.

    Extracts DKIM-Signature headers from inbound messages, retrieves
    the signing domain's public key via DNS, and verifies the signature
    using the same canonicalization and hash algorithms.
    """

    def __init__(self, dns_resolver: Any = None) -> None:
        self._dns_resolver = dns_resolver

    def verify(self, message: MailMessage) -> DKIMResult:
        """Verify the DKIM signature on a message.

        Returns DKIMResult.PASS if the signature is valid, FAIL if
        invalid, NONE if no DKIM-Signature header is present.
        """
        dkim_header = message.headers.get("DKIM-Signature", "")
        if not dkim_header:
            return DKIMResult.NONE

        try:
            sig_data = self._extract_dkim_signature(dkim_header)
        except Exception:
            return DKIMResult.PERMERROR

        public_key = self._lookup_public_key(sig_data.domain, sig_data.selector)
        if public_key is None:
            return DKIMResult.TEMPERROR

        # Verify body hash
        body = message.body_text or message.body_html or ""
        body_canon = DKIMSigner(sig_data.domain, sig_data.selector)._canonicalize_body_relaxed(body)
        expected_bh = base64.b64encode(
            hashlib.sha256(body_canon.encode("utf-8")).digest()
        ).decode("ascii")

        if expected_bh != sig_data.body_hash:
            return DKIMResult.FAIL

        # Verify header signature (simulated)
        header_parts = []
        for hname in sig_data.headers_list:
            value = message.headers.get(hname, "")
            header_parts.append(f"{hname.lower()}:{re.sub(r'\\s+', ' ', value).strip()}")

        # Reconstruct DKIM-Signature without b= value for verification
        dkim_without_b = re.sub(r"b=[^;]*", "b=", dkim_header)
        header_parts.append(f"dkim-signature:{re.sub(r'\\s+', ' ', dkim_without_b).strip()}")

        header_hash_input = "\r\n".join(header_parts)

        # Simulated verification via HMAC
        private_key = DKIM_SIMULATED_PRIVATE_KEY
        expected_sig = hmac.new(
            private_key.encode("utf-8"),
            header_hash_input.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        expected_sig_b64 = base64.b64encode(expected_sig).decode("ascii")

        if hmac.compare_digest(expected_sig_b64, sig_data.signature):
            return DKIMResult.PASS

        return DKIMResult.FAIL

    def _extract_dkim_signature(self, header_value: str) -> DKIMSignatureData:
        """Parse DKIM-Signature header into DKIMSignatureData."""
        sig = DKIMSignatureData()
        for part in header_value.split(";"):
            part = part.strip()
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            key = key.strip()
            value = value.strip()

            if key == "v":
                sig.version = value
            elif key == "a":
                sig.algorithm = value
            elif key == "d":
                sig.domain = value
            elif key == "s":
                sig.selector = value
            elif key == "h":
                sig.headers_list = [h.strip() for h in value.split(":")]
            elif key == "bh":
                sig.body_hash = value
            elif key == "b":
                sig.signature = value
            elif key == "c":
                sig.canonicalization = value
            elif key == "t":
                sig.timestamp = int(value) if value.isdigit() else 0

        return sig

    def _lookup_public_key(self, domain: str, selector: str) -> Optional[str]:
        """Look up DKIM public key via DNS TXT record."""
        query_domain = f"{selector}._domainkey.{domain}"

        if self._dns_resolver is not None:
            try:
                records = self._dns_resolver.resolve(query_domain, "TXT")
                for rec in records:
                    if "p=" in rec:
                        return rec
            except Exception:
                pass

        # Simulated DKIM public key
        if domain in ("fizzbuzz.local", "example.com"):
            return f"v=DKIM1; k=rsa; p={DKIM_SIMULATED_PUBLIC_KEY}"

        return None


# ============================================================
# DMARC Evaluator
# ============================================================


class DMARCEvaluator:
    """DMARC policy evaluation engine per RFC 7489.

    Combines SPF and DKIM authentication results with identifier
    alignment checks against the From header domain to determine
    the DMARC policy disposition.
    """

    def __init__(self, dns_resolver: Any = None) -> None:
        self._dns_resolver = dns_resolver

    def evaluate(self, from_domain: str, spf_result: SPFResult,
                 spf_domain: str, dkim_result: DKIMResult,
                 dkim_domain: str) -> Tuple[DMARCPolicy, bool]:
        """Evaluate DMARC policy for a message.

        Returns (policy, passed) where policy is the DMARC disposition
        and passed indicates whether the message passes DMARC evaluation.
        """
        record = self._lookup_dmarc_record(from_domain)
        if record is None:
            return DMARCPolicy.NONE, True

        # Check SPF alignment
        spf_aligned = False
        if spf_result == SPFResult.PASS:
            spf_aligned = self._check_alignment(from_domain, spf_domain, record.aspf)

        # Check DKIM alignment
        dkim_aligned = False
        if dkim_result == DKIMResult.PASS:
            dkim_aligned = self._check_alignment(from_domain, dkim_domain, record.adkim)

        passed = spf_aligned or dkim_aligned

        if passed:
            return record.policy, True

        # Apply percentage
        if record.pct < 100:
            if random.randint(1, 100) > record.pct:
                return record.policy, True  # Not in sample

        return record.policy, False

    def _lookup_dmarc_record(self, domain: str) -> Optional[DMARCRecord]:
        """Query DNS for DMARC TXT record."""
        query_domain = f"_dmarc.{domain}"

        # Simulated DMARC records
        simulated = {
            "_dmarc.fizzbuzz.local": "v=DMARC1; p=quarantine; rua=mailto:dmarc@fizzbuzz.local; adkim=r; aspf=r; pct=100",
            "_dmarc.example.com": "v=DMARC1; p=reject; rua=mailto:dmarc@example.com; adkim=s; aspf=s",
        }

        txt = simulated.get(query_domain)
        if txt is None and self._dns_resolver is not None:
            try:
                records = self._dns_resolver.resolve(query_domain, "TXT")
                for rec in records:
                    if rec.startswith("v=DMARC1"):
                        txt = rec
                        break
            except Exception:
                pass

        if txt is None:
            return None

        return self._parse_dmarc_record(txt)

    def _parse_dmarc_record(self, txt: str) -> DMARCRecord:
        """Parse a DMARC TXT record into a DMARCRecord."""
        record = DMARCRecord()
        for part in txt.split(";"):
            part = part.strip()
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            key = key.strip()
            value = value.strip()

            if key == "v":
                record.version = value
            elif key == "p":
                record.policy = DMARCPolicy(value) if value in ("none", "quarantine", "reject") else DMARCPolicy.NONE
            elif key == "sp":
                record.subdomain_policy = DMARCPolicy(value) if value in ("none", "quarantine", "reject") else None
            elif key == "rua":
                record.rua = value
            elif key == "ruf":
                record.ruf = value
            elif key == "adkim":
                record.adkim = DMARCAlignment.STRICT if value == "s" else DMARCAlignment.RELAXED
            elif key == "aspf":
                record.aspf = DMARCAlignment.STRICT if value == "s" else DMARCAlignment.RELAXED
            elif key == "pct":
                record.pct = int(value) if value.isdigit() else 100

        return record

    def _check_alignment(self, from_domain: str, auth_domain: str,
                         mode: DMARCAlignment) -> bool:
        """Check identifier alignment between From domain and authenticated domain."""
        if mode == DMARCAlignment.STRICT:
            return from_domain.lower() == auth_domain.lower()
        else:
            # Relaxed: organizational domain must match
            from_org = self._get_organizational_domain(from_domain)
            auth_org = self._get_organizational_domain(auth_domain)
            return from_org.lower() == auth_org.lower()

    def _get_organizational_domain(self, domain: str) -> str:
        """Extract the organizational domain (registered domain).

        Simplified: returns the last two labels (e.g., example.com
        from sub.example.com).
        """
        parts = domain.split(".")
        if len(parts) <= 2:
            return domain
        return ".".join(parts[-2:])

    def generate_aggregate_report(self, results: List[Dict[str, Any]]) -> str:
        """Generate a simplified DMARC aggregate report in XML format."""
        now = datetime.now(timezone.utc)
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<feedback>',
            f'  <report_metadata>',
            f'    <org_name>Enterprise FizzBuzz Platform</org_name>',
            f'    <email>dmarc@{DEFAULT_DOMAIN}</email>',
            f'    <report_id>{uuid.uuid4().hex[:12]}</report_id>',
            f'    <date_range>',
            f'      <begin>{int(now.timestamp()) - 86400}</begin>',
            f'      <end>{int(now.timestamp())}</end>',
            f'    </date_range>',
            f'  </report_metadata>',
        ]
        for result in results:
            lines.extend([
                f'  <record>',
                f'    <row>',
                f'      <source_ip>{result.get("source_ip", "0.0.0.0")}</source_ip>',
                f'      <count>{result.get("count", 1)}</count>',
                f'      <policy_evaluated>',
                f'        <disposition>{result.get("disposition", "none")}</disposition>',
                f'        <dkim>{result.get("dkim", "pass")}</dkim>',
                f'        <spf>{result.get("spf", "pass")}</spf>',
                f'      </policy_evaluated>',
                f'    </row>',
                f'  </record>',
            ])
        lines.append('</feedback>')
        return "\n".join(lines)


# ============================================================
# Greylister
# ============================================================


class Greylister:
    """Greylisting engine for inbound SMTP connections.

    Tracks (sender_ip, sender, recipient) triplets and defers first
    delivery attempts for a configurable delay.  After the delay,
    subsequent attempts from the same triplet are accepted.  Senders
    that successfully deliver multiple messages are auto-whitelisted.
    """

    def __init__(self, config: FizzMailConfig) -> None:
        self._config = config
        self._entries: Dict[str, GreylistEntry] = {}
        self._stats_deferred = 0
        self._stats_accepted = 0

    def check(self, client_ip: str, sender: str,
              recipient: str) -> Tuple[bool, str]:
        """Check whether a delivery attempt should be accepted or deferred.

        Returns (allow, message) where allow is True if the message
        should be accepted, False if it should be deferred with the
        given message.
        """
        key = self._get_triplet_key(client_ip, sender, recipient)
        now = time.time()

        entry = self._entries.get(key)
        if entry is None:
            # First occurrence
            self._entries[key] = GreylistEntry(
                first_seen=now,
                last_seen=now,
                count=1,
                whitelisted=False,
            )
            self._stats_deferred += 1
            return False, f"Greylisted: try again after {int(self._config.greylist_delay)}s"

        entry.last_seen = now
        entry.count += 1

        if entry.whitelisted:
            self._stats_accepted += 1
            return True, "Whitelisted"

        elapsed = now - entry.first_seen
        if elapsed >= self._config.greylist_delay:
            # Auto-whitelist after threshold
            if entry.count >= self._config.greylist_whitelist_threshold:
                entry.whitelisted = True
            self._stats_accepted += 1
            return True, "Accepted after greylist delay"

        self._stats_deferred += 1
        remaining = int(self._config.greylist_delay - elapsed)
        return False, f"Greylisted: try again in {remaining}s"

    def _get_triplet_key(self, ip: str, sender: str, recipient: str) -> str:
        """Generate a triplet key for lookup."""
        return f"{ip}|{sender.lower()}|{recipient.lower()}"

    def cleanup(self, now: Optional[float] = None) -> int:
        """Remove expired greylisting entries.

        Returns the number of entries removed.
        """
        if now is None:
            now = time.time()
        expired = []
        for key, entry in self._entries.items():
            if now - entry.last_seen > self._config.greylist_ttl:
                expired.append(key)
        for key in expired:
            del self._entries[key]
        return len(expired)

    def get_stats(self) -> Dict[str, int]:
        """Return greylisting statistics."""
        whitelisted = sum(1 for e in self._entries.values() if e.whitelisted)
        return {
            "total_entries": len(self._entries),
            "whitelisted": whitelisted,
            "deferred": self._stats_deferred,
            "accepted": self._stats_accepted,
        }


# ============================================================
# RBL Checker
# ============================================================


class RBLChecker:
    """Real-time Blocklist (RBL/DNSBL) checker.

    Queries DNS-based blocklists by reversing the client IP octets
    and performing A record lookups against configured zones.
    """

    def __init__(self, zones: List[str], dns_resolver: Any = None) -> None:
        self._zones = zones
        self._dns_resolver = dns_resolver

    def check(self, client_ip: str) -> Tuple[bool, List[str]]:
        """Check if a client IP is listed in any configured RBL zone.

        Returns (listed, listing_zones) where listed is True if the
        IP appears in at least one zone.
        """
        reversed_ip = self._reverse_ip(client_ip)
        listing_zones = []

        for zone in self._zones:
            if self._query_zone(reversed_ip, zone):
                listing_zones.append(zone)

        return len(listing_zones) > 0, listing_zones

    def _reverse_ip(self, ip: str) -> str:
        """Reverse the octets of an IPv4 address for DNSBL lookup."""
        parts = ip.split(".")
        return ".".join(reversed(parts))

    def _query_zone(self, reversed_ip: str, zone: str) -> bool:
        """Query a single DNSBL zone for a listing."""
        query = f"{reversed_ip}.{zone}"

        if self._dns_resolver is not None:
            try:
                result = self._dns_resolver.resolve(query, "A")
                return bool(result)
            except Exception:
                return False

        # Simulated: known bad IPs
        blocked_ips = {"192.0.2.1", "198.51.100.1"}
        original_ip = ".".join(reversed(reversed_ip.split(".")))
        return original_ip in blocked_ips


# ============================================================
# Bounce Handler
# ============================================================


class BounceHandler:
    """Delivery Status Notification (DSN) generator per RFC 3464.

    Constructs multipart/report bounce messages with three parts:
    human-readable explanation, machine-readable delivery status,
    and original message headers.
    """

    def __init__(self, config: FizzMailConfig) -> None:
        self._config = config

    def generate_dsn(self, original_envelope: Envelope,
                     recipients_status: List[DSNRecipient],
                     original_headers: str = "") -> MailMessage:
        """Generate a DSN bounce message.

        Returns a complete MailMessage ready for delivery to the
        original sender.
        """
        parser = RFC5322HeaderParser()
        builder = MIMEBuilder()
        now = datetime.now(timezone.utc)

        # Part 1: Human-readable explanation
        human_parts = ["This is the mail system at Enterprise FizzBuzz Platform.", ""]
        for rcpt in recipients_status:
            human_parts.append(
                f"Delivery to {rcpt.final_recipient} has {rcpt.action}."
            )
            if rcpt.diagnostic_code:
                human_parts.append(f"  Diagnostic: {rcpt.diagnostic_code}")
            human_parts.append("")
        human_text = "\r\n".join(human_parts)

        # Part 2: Delivery status
        status_parts = [
            f"Reporting-MTA: dns; {self._config.hostname}",
            f"Arrival-Date: {parser.format_date(now)}",
            "",
        ]
        for rcpt in recipients_status:
            status_parts.extend([
                f"Final-Recipient: rfc822; {rcpt.final_recipient}",
                f"Action: {rcpt.action}",
                f"Status: {rcpt.status_code}",
            ])
            if rcpt.diagnostic_code:
                status_parts.append(f"Diagnostic-Code: smtp; {rcpt.diagnostic_code}")
            if rcpt.remote_mta:
                status_parts.append(f"Remote-MTA: dns; {rcpt.remote_mta}")
            status_parts.append("")
        delivery_status = "\r\n".join(status_parts)

        # Build DSN message
        message = MailMessage(
            message_id=parser.generate_message_id(self._config.domain),
            date=now,
            from_addr=EmailAddress(
                display_name="Mail Delivery System",
                local_part="MAILER-DAEMON",
                domain=self._config.domain,
            ),
            to_addrs=[parser.parse_address(original_envelope.mail_from)],
            subject="Undelivered Mail Returned to Sender",
            body_text=human_text,
            headers={
                "Auto-Submitted": "auto-replied",
                "X-FizzMail-DSN": "true",
            },
        )

        # Attach delivery status and original headers as additional info
        message.headers["X-DSN-Status"] = delivery_status
        if original_headers:
            message.headers["X-DSN-Original-Headers"] = original_headers

        message.raw = builder.build_message(message, self._config)
        return message


# ============================================================
# Maildir Storage
# ============================================================


class MaildirStorage:
    """In-memory Maildir-format message store.

    Simulates the Maildir directory structure (new/, cur/, tmp/) with
    atomic delivery semantics.  Each user has a set of named mailboxes,
    each containing messages addressed by UID.  Message flags are
    encoded in the Maildir filename info suffix.
    """

    def __init__(self, config: FizzMailConfig) -> None:
        self._config = config
        self._mailboxes: Dict[str, Dict[str, Mailbox]] = {}
        self._quotas: Dict[str, int] = {}
        self._lock = threading.Lock()

    def create_user(self, user: str) -> None:
        """Create a user's mailbox hierarchy with default folders."""
        if user not in self._mailboxes:
            self._mailboxes[user] = {}
            for name in DEFAULT_MAILBOXES:
                self.create_mailbox(user, name)

    def create_mailbox(self, user: str, name: str) -> Mailbox:
        """Create a new mailbox for a user."""
        if user not in self._mailboxes:
            self._mailboxes[user] = {}

        if name in self._mailboxes[user]:
            raise FizzMailMailboxExistsError(name)

        mailbox = Mailbox(
            name=name,
            uidvalidity=int(time.time()) & 0x7FFFFFFF,
            uidnext=1,
        )
        self._mailboxes[user][name] = mailbox
        logger.debug("Mailbox created: %s/%s", user, name)
        return mailbox

    def delete_mailbox(self, user: str, name: str) -> None:
        """Delete a mailbox."""
        if user not in self._mailboxes or name not in self._mailboxes[user]:
            raise FizzMailMailboxNotFoundError(name)
        if name == "INBOX":
            raise FizzMailMailboxError("INBOX", "Cannot delete INBOX")
        del self._mailboxes[user][name]

    def rename_mailbox(self, user: str, old_name: str, new_name: str) -> None:
        """Rename a mailbox."""
        if user not in self._mailboxes or old_name not in self._mailboxes[user]:
            raise FizzMailMailboxNotFoundError(old_name)
        if new_name in self._mailboxes.get(user, {}):
            raise FizzMailMailboxExistsError(new_name)
        if old_name == "INBOX":
            raise FizzMailMailboxError("INBOX", "Cannot rename INBOX")

        mailbox = self._mailboxes[user].pop(old_name)
        mailbox.name = new_name
        self._mailboxes[user][new_name] = mailbox

    def get_mailbox(self, user: str, name: str) -> Mailbox:
        """Retrieve a mailbox by name."""
        if user not in self._mailboxes or name not in self._mailboxes[user]:
            raise FizzMailMailboxNotFoundError(name)
        return self._mailboxes[user][name]

    def list_mailboxes(self, user: str, pattern: str = "*") -> List[Mailbox]:
        """List mailboxes matching a pattern.

        Supports * (match any) and % (match any except hierarchy delimiter).
        """
        if user not in self._mailboxes:
            return []

        if pattern == "*":
            return list(self._mailboxes[user].values())

        regex_pattern = pattern.replace(".", r"\.").replace("*", ".*").replace("%", "[^.]*")
        regex = re.compile(f"^{regex_pattern}$", re.IGNORECASE)
        return [mb for mb in self._mailboxes[user].values() if regex.match(mb.name)]

    def deliver(self, user: str, mailbox_name: str, message: MailMessage) -> int:
        """Deliver a message to a mailbox.

        Implements atomic Maildir delivery: write to tmp/, then move
        to new/.  Returns the assigned UID.
        """
        if user not in self._mailboxes:
            self.create_user(user)

        if mailbox_name not in self._mailboxes[user]:
            self.create_mailbox(user, mailbox_name)

        mailbox = self._mailboxes[user][mailbox_name]

        # Check quota
        quota = self.get_quota(user)
        usage = self.get_quota_usage(user)
        msg_size = message.size or len(message.raw or "")
        if usage + msg_size > quota:
            raise FizzMailQuotaError(mailbox_name, usage + msg_size, quota)

        with self._lock:
            uid = mailbox.uidnext
            mailbox.uidnext += 1

        now = datetime.now(timezone.utc)
        flags: Set[str] = set()

        filename = self._generate_filename(uid, flags)

        maildir_msg = MaildirMessage(
            uid=uid,
            filename=filename,
            flags=flags,
            internal_date=now,
            size=msg_size,
            headers={
                "From": str(message.from_addr) if message.from_addr else "",
                "To": ", ".join(str(a) for a in message.to_addrs),
                "Subject": message.subject,
                "Date": RFC5322HeaderParser().format_date(message.date) if message.date else "",
                "Message-ID": message.message_id,
            },
            raw=message.raw,
            subject=message.subject,
            from_addr=str(message.from_addr) if message.from_addr else "",
            to_addr=", ".join(str(a) for a in message.to_addrs),
        )

        mailbox.messages.append(maildir_msg)
        mailbox.exists = len(mailbox.messages)
        mailbox.recent_count += 1

        logger.debug("Message delivered: UID=%d to %s/%s", uid, user, mailbox_name)
        return uid

    def fetch_message(self, user: str, mailbox_name: str, uid: int) -> Optional[MaildirMessage]:
        """Fetch a message by UID."""
        mailbox = self.get_mailbox(user, mailbox_name)
        for msg in mailbox.messages:
            if msg.uid == uid:
                return msg
        return None

    def get_messages(self, user: str, mailbox_name: str) -> List[MaildirMessage]:
        """Return all messages in a mailbox."""
        mailbox = self.get_mailbox(user, mailbox_name)
        return list(mailbox.messages)

    def update_flags(self, user: str, mailbox_name: str, uid: int,
                     flags: Set[str], action: IMAPFlagAction) -> Set[str]:
        """Update message flags.

        Returns the resulting flag set after the operation.
        """
        msg = self.fetch_message(user, mailbox_name, uid)
        if msg is None:
            raise FizzMailFlagError(str(uid), "Message not found")

        if action == IMAPFlagAction.SET:
            msg.flags = set(flags)
        elif action == IMAPFlagAction.ADD:
            msg.flags |= flags
        elif action == IMAPFlagAction.REMOVE:
            msg.flags -= flags

        msg.filename = self._generate_filename(msg.uid, msg.flags)
        return set(msg.flags)

    def expunge(self, user: str, mailbox_name: str) -> List[int]:
        """Remove messages marked with \\Deleted flag.

        Returns a list of expunged message sequence numbers (1-based).
        """
        mailbox = self.get_mailbox(user, mailbox_name)
        expunged = []
        remaining = []
        for i, msg in enumerate(mailbox.messages, 1):
            if r"\Deleted" in msg.flags:
                expunged.append(i)
            else:
                remaining.append(msg)
        mailbox.messages = remaining
        mailbox.exists = len(remaining)
        return expunged

    def get_quota_usage(self, user: str) -> int:
        """Calculate total storage usage across all mailboxes for a user."""
        total = 0
        for mailbox in self._mailboxes.get(user, {}).values():
            for msg in mailbox.messages:
                total += msg.size
        return total

    def get_quota(self, user: str) -> int:
        """Return the quota for a user."""
        return self._quotas.get(user, self._config.quota_default)

    def set_quota(self, user: str, quota: int) -> None:
        """Override the default quota for a user."""
        self._quotas[user] = quota

    def get_all_users(self) -> List[str]:
        """Return all user identifiers."""
        return list(self._mailboxes.keys())

    def _generate_filename(self, uid: int, flags: Set[str]) -> str:
        """Generate a Maildir-format filename with flag encoding."""
        timestamp = int(time.time())
        unique = uuid.uuid4().hex[:8]
        info = self._encode_flags(flags)
        if info:
            return f"{timestamp}.{uid}.{unique}:2,{info}"
        return f"{timestamp}.{uid}.{unique}"

    def _encode_flags(self, flags: Set[str]) -> str:
        """Encode IMAP flags to Maildir info suffix characters."""
        chars = []
        for flag, char in sorted(MAILDIR_FLAG_MAP.items()):
            if flag in flags:
                chars.append(char)
        return "".join(sorted(chars))

    def _decode_flags(self, info_str: str) -> Set[str]:
        """Decode Maildir info suffix characters to IMAP flags."""
        flags = set()
        for char in info_str:
            flag = MAILDIR_FLAG_REVERSE.get(char)
            if flag:
                flags.add(flag)
        return flags


# ============================================================
# Quota Enforcer
# ============================================================


class QuotaEnforcer:
    """Per-mailbox storage quota enforcement.

    Checks message delivery against configured storage limits and
    rejects deliveries that would exceed the quota.
    """

    def __init__(self, config: FizzMailConfig, storage: MaildirStorage) -> None:
        self._config = config
        self._storage = storage

    def check_quota(self, user: str, additional_size: int) -> Tuple[bool, int, int]:
        """Check if a delivery would exceed the user's quota.

        Returns (allowed, current_usage, quota_limit).
        """
        usage = self._storage.get_quota_usage(user)
        quota = self._storage.get_quota(user)
        return (usage + additional_size) <= quota, usage, quota

    def get_usage(self, user: str) -> int:
        """Return current storage usage for a user."""
        return self._storage.get_quota_usage(user)

    def get_quota(self, user: str) -> int:
        """Return the quota limit for a user."""
        return self._storage.get_quota(user)

    def set_quota(self, user: str, quota: int) -> None:
        """Override the default quota for a user."""
        self._storage.set_quota(user, quota)


# ============================================================
# IMAP Search Engine
# ============================================================


class IMAPSearchEngine:
    """IMAP SEARCH criteria evaluation engine.

    Implements the full IMAP SEARCH grammar per RFC 3501 Section 6.4.4:
    logical operators (AND, OR, NOT), header field matches, body text
    search, date comparisons, size comparisons, and flag checks.
    """

    def __init__(self, search_engine: Any = None) -> None:
        self._search_engine = search_engine

    def search(self, mailbox: Mailbox, criteria: str,
               use_uid: bool = False) -> List[int]:
        """Search a mailbox for messages matching the criteria.

        Returns a list of sequence numbers (or UIDs if use_uid is True).
        """
        tokens = self._tokenize(criteria)
        criteria_tree = self._parse_criteria(tokens)

        results = []
        for seq_num, msg in enumerate(mailbox.messages, 1):
            if self._evaluate(msg, criteria_tree):
                results.append(msg.uid if use_uid else seq_num)

        return results

    def _tokenize(self, criteria: str) -> List[str]:
        """Tokenize IMAP SEARCH criteria string."""
        tokens = []
        i = 0
        while i < len(criteria):
            if criteria[i] in (' ', '\t'):
                i += 1
                continue
            if criteria[i] == '"':
                end = criteria.index('"', i + 1)
                tokens.append(criteria[i + 1:end])
                i = end + 1
            elif criteria[i] == '(':
                tokens.append('(')
                i += 1
            elif criteria[i] == ')':
                tokens.append(')')
                i += 1
            else:
                end = i
                while end < len(criteria) and criteria[end] not in (' ', '\t', '(', ')'):
                    end += 1
                tokens.append(criteria[i:end])
                i = end
        return tokens

    def _parse_criteria(self, tokens: List[str]) -> Dict[str, Any]:
        """Parse tokenized criteria into an evaluation tree."""
        if not tokens:
            return {"op": "ALL"}

        self._pos = 0
        self._tokens = tokens
        return self._parse_or()

    def _parse_or(self) -> Dict[str, Any]:
        """Parse OR expressions."""
        left = self._parse_single()
        while self._pos < len(self._tokens) and self._peek() == "OR":
            self._advance()
            right = self._parse_single()
            left = {"op": "OR", "left": left, "right": right}
        return left

    def _parse_single(self) -> Dict[str, Any]:
        """Parse a single criterion or group."""
        if self._pos >= len(self._tokens):
            return {"op": "ALL"}

        token = self._peek().upper()

        if token == "NOT":
            self._advance()
            operand = self._parse_single()
            return {"op": "NOT", "operand": operand}

        if token == "(":
            self._advance()
            result = self._parse_or()
            if self._pos < len(self._tokens) and self._peek() == ")":
                self._advance()
            return result

        if token == "ALL":
            self._advance()
            return {"op": "ALL"}

        if token == "OR":
            self._advance()
            left = self._parse_single()
            right = self._parse_single()
            return {"op": "OR", "left": left, "right": right}

        # Header searches
        if token in ("FROM", "TO", "CC", "BCC", "SUBJECT"):
            self._advance()
            value = self._advance()
            return {"op": "HEADER", "field": token.capitalize() if token != "BCC" else "Bcc",
                    "value": value}

        if token == "HEADER":
            self._advance()
            field = self._advance()
            value = self._advance()
            return {"op": "HEADER", "field": field, "value": value}

        if token in ("BODY", "TEXT"):
            self._advance()
            value = self._advance()
            return {"op": token, "value": value}

        # Date searches
        if token in ("BEFORE", "ON", "SINCE", "SENTBEFORE", "SENTON", "SENTSINCE"):
            self._advance()
            date_str = self._advance()
            return {"op": token, "date": date_str}

        # Flag searches
        if token in ("SEEN", "UNSEEN", "FLAGGED", "UNFLAGGED", "ANSWERED",
                      "UNANSWERED", "DELETED", "UNDELETED", "DRAFT", "UNDRAFT",
                      "NEW", "OLD", "RECENT"):
            self._advance()
            return {"op": "FLAG", "flag": token}

        # Size searches
        if token in ("LARGER", "SMALLER"):
            self._advance()
            size = self._advance()
            return {"op": token, "size": int(size)}

        if token == "UID":
            self._advance()
            uid_set = self._advance()
            return {"op": "UID", "set": uid_set}

        # Default: treat as unknown, skip
        self._advance()
        return {"op": "ALL"}

    def _peek(self) -> str:
        """Peek at the current token."""
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return ""

    def _advance(self) -> str:
        """Advance and return the current token."""
        token = self._peek()
        self._pos += 1
        return token

    def _evaluate(self, msg: MaildirMessage, criteria: Dict[str, Any]) -> bool:
        """Evaluate a message against a parsed criteria tree."""
        op = criteria.get("op", "ALL")

        if op == "ALL":
            return True
        elif op == "NOT":
            return not self._evaluate(msg, criteria["operand"])
        elif op == "OR":
            return (self._evaluate(msg, criteria["left"]) or
                    self._evaluate(msg, criteria["right"]))
        elif op == "AND":
            return (self._evaluate(msg, criteria["left"]) and
                    self._evaluate(msg, criteria["right"]))
        elif op == "HEADER":
            return self._match_header(msg, criteria["field"], criteria["value"])
        elif op in ("BODY", "TEXT"):
            return self._match_body(msg, criteria["value"])
        elif op in ("BEFORE", "ON", "SINCE"):
            return self._match_date(msg.internal_date, criteria["date"], op)
        elif op in ("SENTBEFORE", "SENTON", "SENTSINCE"):
            date_header = msg.headers.get("Date", "")
            parsed = RFC5322HeaderParser().parse_date(date_header) if date_header else msg.internal_date
            base_op = op.replace("SENT", "")
            return self._match_date(parsed, criteria["date"], base_op)
        elif op == "FLAG":
            return self._match_flag(msg, criteria["flag"])
        elif op == "LARGER":
            return msg.size > criteria["size"]
        elif op == "SMALLER":
            return msg.size < criteria["size"]
        elif op == "UID":
            return self._match_uid_set(msg.uid, criteria["set"])

        return True

    def _match_header(self, msg: MaildirMessage, field: str, value: str) -> bool:
        """Check if a header field contains the search value (case-insensitive)."""
        header_value = msg.headers.get(field, "")
        if not header_value:
            # Check alternate casing
            for k, v in msg.headers.items():
                if k.lower() == field.lower():
                    header_value = v
                    break
        # Also check from_addr, to_addr, subject fields
        if field.lower() == "from" and not header_value:
            header_value = msg.from_addr
        elif field.lower() == "to" and not header_value:
            header_value = msg.to_addr
        elif field.lower() == "subject" and not header_value:
            header_value = msg.subject
        return value.lower() in header_value.lower()

    def _match_body(self, msg: MaildirMessage, value: str) -> bool:
        """Check if the message body contains the search value."""
        raw = msg.raw or ""
        return value.lower() in raw.lower()

    def _match_date(self, msg_date: Optional[datetime], target_str: str,
                    op: str) -> bool:
        """Compare message date against a target date."""
        if msg_date is None:
            return False

        # Parse target date (dd-Mon-yyyy)
        parser = RFC5322HeaderParser()
        # Try to parse as "dd-Mon-yyyy" format
        try:
            parts = target_str.split("-")
            if len(parts) == 3:
                day = int(parts[0])
                month = parser._MONTH_MAP.get(parts[1], 0)
                year = int(parts[2])
                target = datetime(year, month, day, tzinfo=timezone.utc)
            else:
                return False
        except (ValueError, KeyError):
            return False

        msg_date_only = msg_date.replace(hour=0, minute=0, second=0, microsecond=0,
                                          tzinfo=timezone.utc)
        target_only = target.replace(tzinfo=timezone.utc)

        if op == "BEFORE":
            return msg_date_only < target_only
        elif op == "ON":
            return msg_date_only == target_only
        elif op == "SINCE":
            return msg_date_only >= target_only
        return False

    def _match_flag(self, msg: MaildirMessage, flag_name: str) -> bool:
        """Check message flags for IMAP SEARCH flag criteria."""
        flag_map = {
            "SEEN": (r"\Seen", True),
            "UNSEEN": (r"\Seen", False),
            "FLAGGED": (r"\Flagged", True),
            "UNFLAGGED": (r"\Flagged", False),
            "ANSWERED": (r"\Answered", True),
            "UNANSWERED": (r"\Answered", False),
            "DELETED": (r"\Deleted", True),
            "UNDELETED": (r"\Deleted", False),
            "DRAFT": (r"\Draft", True),
            "UNDRAFT": (r"\Draft", False),
            "RECENT": (r"\Recent", True),
            "NEW": None,
            "OLD": None,
        }

        spec = flag_map.get(flag_name)
        if spec is None:
            if flag_name == "NEW":
                return r"\Recent" in msg.flags and r"\Seen" not in msg.flags
            elif flag_name == "OLD":
                return r"\Recent" not in msg.flags
            return True

        flag, expected = spec
        return (flag in msg.flags) == expected

    def _match_uid_set(self, uid: int, uid_set_str: str) -> bool:
        """Check if a UID is in a UID set expression (e.g., '1:5,7,10:*')."""
        for part in uid_set_str.split(","):
            if ":" in part:
                start_str, end_str = part.split(":", 1)
                start = int(start_str) if start_str != "*" else uid
                end = int(end_str) if end_str != "*" else 999999999
                if start <= uid <= end:
                    return True
            else:
                if part == "*" or int(part) == uid:
                    return True
        return False


# ============================================================
# SMTP Server
# ============================================================


class SMTPServer:
    """SMTP server implementing RFC 5321.

    Processes SMTP commands through a state machine, enforcing command
    sequencing, size limits, and authentication requirements.  All
    network I/O is simulated -- the server accepts pre-parsed command
    strings and returns SMTPResponse objects.
    """

    def __init__(self, config: FizzMailConfig,
                 authenticator: SMTPAuthenticator,
                 tls_handler: SMTPTLSHandler,
                 queue: MessageQueue,
                 relay_router: RelayRouter,
                 spf_validator: Optional[SPFValidator] = None,
                 dkim_signer: Optional[DKIMSigner] = None,
                 dkim_verifier: Optional[DKIMVerifier] = None,
                 dmarc_evaluator: Optional[DMARCEvaluator] = None,
                 greylister: Optional[Greylister] = None,
                 rbl_checker: Optional[RBLChecker] = None,
                 storage: Optional[MaildirStorage] = None) -> None:
        self._config = config
        self._auth = authenticator
        self._tls = tls_handler
        self._queue = queue
        self._relay = relay_router
        self._spf = spf_validator
        self._dkim_signer = dkim_signer
        self._dkim_verifier = dkim_verifier
        self._dmarc = dmarc_evaluator
        self._greylister = greylister
        self._rbl = rbl_checker
        self._storage = storage
        self._metrics = ServerMetrics()
        self._active_sessions: Dict[str, SMTPSession] = {}
        self._started = False
        self._start_time = 0.0

    def start(self) -> None:
        """Start the SMTP server."""
        self._started = True
        self._start_time = time.time()
        logger.info(
            "SMTP server started: %s:%d domain=%s",
            self._config.hostname, self._config.smtp_port, self._config.domain,
        )

    def handle_connection(self, client_addr: str,
                          commands: List[str]) -> List[SMTPResponse]:
        """Process a sequence of SMTP commands from a client.

        Returns a list of SMTPResponse objects, one per command plus
        the initial greeting.
        """
        session = SMTPSession(
            state=SMTPState.CONNECTED,
            client_addr=client_addr,
        )
        self._active_sessions[client_addr] = session
        self._metrics.active_smtp_sessions += 1

        responses = []

        # Initial greeting
        responses.append(SMTPResponse(
            220, f"{self._config.hostname} {FIZZMAIL_SERVER_NAME} ESMTP"
        ))

        for command_line in commands:
            response = self._process_command(session, command_line)
            responses.append(response)

            if session.state == SMTPState.CLOSED:
                break

        self._active_sessions.pop(client_addr, None)
        self._metrics.active_smtp_sessions = max(0, self._metrics.active_smtp_sessions - 1)

        return responses

    def _process_command(self, session: SMTPSession, line: str) -> SMTPResponse:
        """Route a command line to the appropriate handler."""
        line = line.strip()
        if not line:
            return SMTPResponse(500, "Syntax error: empty command")

        parts = line.split(None, 1)
        verb = parts[0].upper()
        arg = parts[1] if len(parts) > 1 else ""

        handlers = {
            "EHLO": lambda: self._handle_ehlo(session, arg),
            "HELO": lambda: self._handle_helo(session, arg),
            "STARTTLS": lambda: self._handle_starttls(session),
            "AUTH": lambda: self._handle_auth(session, arg),
            "MAIL": lambda: self._handle_mail_from(session, arg),
            "RCPT": lambda: self._handle_rcpt_to(session, arg),
            "DATA": lambda: self._handle_data(session, arg),
            "RSET": lambda: self._handle_rset(session),
            "NOOP": lambda: self._handle_noop(session),
            "VRFY": lambda: self._handle_vrfy(session, arg),
            "QUIT": lambda: self._handle_quit(session),
        }

        handler = handlers.get(verb)
        if handler is None:
            return SMTPResponse(500, f"Command not recognized: {verb}")

        try:
            return handler()
        except FizzMailError as e:
            return SMTPResponse(554, str(e))

    def _handle_ehlo(self, session: SMTPSession, domain: str) -> SMTPResponse:
        """Handle EHLO command."""
        if not domain:
            return SMTPResponse(501, "EHLO requires domain argument")

        session.ehlo_domain = domain
        session.state = SMTPState.GREETED if not session.tls_active else SMTPState.TLS_NEGOTIATED
        session.envelope = None

        extensions = [
            f"{self._config.hostname}",
            f"SIZE {self._config.max_message_size}",
            "8BITMIME",
            "PIPELINING",
            "ENHANCEDSTATUSCODES",
        ]

        if self._config.enable_tls and not session.tls_active:
            extensions.append("STARTTLS")
        if self._config.enable_auth:
            extensions.append("AUTH PLAIN LOGIN CRAM-MD5")

        session.extensions = extensions
        ext_text = "\r\n".join(f"250-{ext}" if i < len(extensions) - 1 else f"250 {ext}"
                               for i, ext in enumerate(extensions))
        return SMTPResponse(250, ext_text)

    def _handle_helo(self, session: SMTPSession, domain: str) -> SMTPResponse:
        """Handle HELO command."""
        if not domain:
            return SMTPResponse(501, "HELO requires domain argument")
        session.ehlo_domain = domain
        session.state = SMTPState.GREETED if not session.tls_active else SMTPState.TLS_NEGOTIATED
        session.envelope = None
        return SMTPResponse(250, f"{self._config.hostname}")

    def _handle_starttls(self, session: SMTPSession) -> SMTPResponse:
        """Handle STARTTLS command."""
        if not self._config.enable_tls:
            return SMTPResponse(502, "STARTTLS not available")

        if session.tls_active:
            return SMTPResponse(503, "TLS already active")

        valid_states = {SMTPState.GREETED, SMTPState.TLS_NEGOTIATED}
        if session.state not in valid_states:
            return SMTPResponse(503, "Bad sequence: EHLO/HELO required first")

        try:
            self._tls.handle_starttls(session)
            return SMTPResponse(220, "Ready to start TLS")
        except FizzMailTLSError as e:
            return SMTPResponse(454, f"TLS negotiation failed: {e}")

    def _handle_auth(self, session: SMTPSession, arg: str) -> SMTPResponse:
        """Handle AUTH command."""
        if not self._config.enable_auth:
            return SMTPResponse(502, "AUTH not available")

        if session.authenticated_user:
            return SMTPResponse(503, "Already authenticated")

        valid_states = {SMTPState.GREETED, SMTPState.TLS_NEGOTIATED}
        if session.state not in valid_states:
            return SMTPResponse(503, "Bad sequence: EHLO/HELO required first")

        parts = arg.split(None, 1)
        if not parts:
            return SMTPResponse(501, "AUTH requires mechanism argument")

        mechanism = parts[0].upper()
        initial_response = parts[1] if len(parts) > 1 else ""

        if mechanism == "PLAIN":
            if not initial_response:
                return SMTPResponse(334, "")  # Request credentials
            success, username = self._auth.authenticate_plain(initial_response)
        elif mechanism == "LOGIN":
            # Simplified: expect username and password in initial_response
            # In real protocol this is a multi-step exchange
            if " " in initial_response:
                user_b64, pass_b64 = initial_response.split(None, 1)
                success, username = self._auth.authenticate_login(user_b64, pass_b64)
            else:
                return SMTPResponse(334, self._auth.authenticate_login_challenge())
        elif mechanism == "CRAM-MD5":
            challenge_b64, challenge_id = self._auth.generate_cram_md5_challenge()
            if initial_response:
                success, username = self._auth.authenticate_cram_md5(challenge_id, initial_response)
            else:
                # Store challenge for later
                session.extensions.append(f"_cram_challenge:{challenge_id}")
                return SMTPResponse(334, challenge_b64)
        else:
            return SMTPResponse(504, f"Unrecognized authentication mechanism: {mechanism}")

        if success:
            session.authenticated_user = username
            session.state = SMTPState.AUTHENTICATED
            self._metrics.auth_successes += 1
            return SMTPResponse(235, "2.7.0 Authentication successful")
        else:
            self._metrics.auth_failures += 1
            return SMTPResponse(535, "5.7.8 Authentication credentials invalid")

    def _handle_mail_from(self, session: SMTPSession, arg: str) -> SMTPResponse:
        """Handle MAIL FROM command."""
        valid_states = {SMTPState.GREETED, SMTPState.TLS_NEGOTIATED, SMTPState.AUTHENTICATED}
        if session.state not in valid_states:
            return SMTPResponse(503, "Bad sequence of commands")

        if not arg.upper().startswith("FROM:"):
            return SMTPResponse(501, "Syntax: MAIL FROM:<address>")

        addr_str = arg[5:].strip()
        address = self._parse_email_address(addr_str)

        # RBL check
        if self._rbl and self._config.enable_rbl:
            listed, zones = self._rbl.check(session.client_addr)
            if listed:
                self._metrics.rbl_blocked += 1
                return SMTPResponse(550, f"5.7.1 Blocked by RBL: {', '.join(zones)}")

        # SPF check
        if self._spf and self._config.enable_spf and address:
            spf_result = self._spf.validate(session.client_addr, address, session.ehlo_domain)
            self._metrics.spf_checks += 1
            if spf_result == SPFResult.PASS:
                self._metrics.spf_passes += 1
            elif spf_result == SPFResult.FAIL:
                return SMTPResponse(550, f"5.7.23 SPF validation failed for {address}")

        # Parse SIZE parameter
        size = 0
        body_type = "7BIT"
        remaining = addr_str
        if ">" in remaining:
            remaining = remaining[remaining.index(">") + 1:].strip()
            for param in remaining.split():
                if param.upper().startswith("SIZE="):
                    size = int(param[5:])
                    if size > self._config.max_message_size:
                        return SMTPResponse(552, f"5.3.4 Message size exceeds limit of {self._config.max_message_size}")
                elif param.upper().startswith("BODY="):
                    body_type = param[5:].upper()

        session.envelope = Envelope(mail_from=address, size=size, body_type=body_type)
        session.state = SMTPState.MAIL_FROM
        return SMTPResponse(250, "2.1.0 OK")

    def _handle_rcpt_to(self, session: SMTPSession, arg: str) -> SMTPResponse:
        """Handle RCPT TO command."""
        if session.state not in {SMTPState.MAIL_FROM, SMTPState.RCPT_TO}:
            return SMTPResponse(503, "Bad sequence: MAIL FROM required first")

        if not arg.upper().startswith("TO:"):
            return SMTPResponse(501, "Syntax: RCPT TO:<address>")

        addr_str = arg[3:].strip()
        address = self._parse_email_address(addr_str)

        if not address:
            return SMTPResponse(553, "5.1.3 Invalid address")

        if len(session.envelope.rcpt_to) >= self._config.max_recipients:
            return SMTPResponse(452, f"5.5.3 Too many recipients (max {self._config.max_recipients})")

        # Greylisting
        if self._greylister and self._config.enable_greylist:
            allow, msg = self._greylister.check(
                session.client_addr, session.envelope.mail_from, address
            )
            if not allow:
                self._metrics.greylist_deferred += 1
                return SMTPResponse(451, f"4.7.1 {msg}")

        session.envelope.rcpt_to.append(address)
        session.state = SMTPState.RCPT_TO
        return SMTPResponse(250, f"2.1.5 OK recipient {address}")

    def _handle_data(self, session: SMTPSession, data: str) -> SMTPResponse:
        """Handle DATA command.

        In this simulation, the data is passed directly rather than
        through a multi-line read loop.  Dot-stuffing is applied.
        """
        if session.state != SMTPState.RCPT_TO:
            return SMTPResponse(503, "Bad sequence: RCPT TO required first")

        if not data:
            return SMTPResponse(354, SMTP_REPLIES[354])

        # Apply dot-unstuffing
        lines = data.split("\n")
        unstuffed = []
        for line in lines:
            line = line.rstrip("\r")
            if line == ".":
                break
            if line.startswith(".."):
                line = line[1:]
            unstuffed.append(line)

        raw_message = "\r\n".join(unstuffed)

        # Check size
        if len(raw_message) > self._config.max_message_size:
            return SMTPResponse(552, f"5.3.4 Message exceeds size limit")

        # Parse message
        parser = RFC5322HeaderParser()
        mime_builder = MIMEBuilder()
        headers = parser.parse_headers(raw_message)

        message = MailMessage(
            message_id=headers.get("Message-ID", parser.generate_message_id(self._config.domain)),
            date=parser.parse_date(headers.get("Date", "")) or datetime.now(timezone.utc),
            from_addr=parser.parse_address(headers.get("From", session.envelope.mail_from)),
            to_addrs=parser.parse_address_list(headers.get("To", "")),
            cc_addrs=parser.parse_address_list(headers.get("Cc", "")),
            subject=headers.get("Subject", ""),
            headers=headers,
            raw=raw_message,
            size=len(raw_message),
        )

        # Extract body
        body_start = raw_message.find("\r\n\r\n")
        if body_start == -1:
            body_start = raw_message.find("\n\n")
        if body_start >= 0:
            body = raw_message[body_start:].strip()
            content_type = headers.get("Content-Type", "text/plain")
            if "text/html" in content_type:
                message.body_html = body
            else:
                message.body_text = body

        # Add Received header
        received = (
            f"from {session.ehlo_domain} ({session.client_addr}) "
            f"by {self._config.hostname} with ESMTP; "
            f"{parser.format_date()}"
        )
        message.headers["Received"] = received

        # DKIM verification
        if self._dkim_verifier and self._config.enable_dkim_verify:
            dkim_result = self._dkim_verifier.verify(message)
            self._metrics.dkim_checks += 1
            if dkim_result == DKIMResult.PASS:
                self._metrics.dkim_passes += 1
            message.headers["Authentication-Results"] = (
                f"{self._config.hostname}; dkim={dkim_result.value}"
            )

        # DKIM signing for local delivery
        if self._dkim_signer and self._config.enable_dkim_sign:
            dkim_signature = self._dkim_signer.sign(message)
            message.headers["DKIM-Signature"] = dkim_signature

        # DMARC evaluation
        if self._dmarc and self._config.enable_dmarc:
            from_domain = message.from_addr.domain if message.from_addr else ""
            spf_domain = session.envelope.mail_from.split("@")[-1] if "@" in session.envelope.mail_from else ""
            spf_result_val = SPFResult.PASS  # Assume pass if we got this far
            dkim_result_val = DKIMResult.PASS if self._dkim_verifier else DKIMResult.NONE
            dkim_domain_val = self._config.domain

            policy, passed = self._dmarc.evaluate(
                from_domain, spf_result_val, spf_domain,
                dkim_result_val, dkim_domain_val,
            )
            self._metrics.dmarc_checks += 1
            if passed:
                self._metrics.dmarc_passes += 1
            elif policy == DMARCPolicy.REJECT:
                return SMTPResponse(550, f"5.7.1 DMARC policy reject for {from_domain}")

        # Deliver or queue
        has_local = any(
            "@" in r and r.split("@")[1] == self._config.domain
            for r in session.envelope.rcpt_to
        )
        has_remote = any(
            "@" not in r or r.split("@")[1] != self._config.domain
            for r in session.envelope.rcpt_to
        )

        if has_local and self._storage:
            for rcpt in session.envelope.rcpt_to:
                if "@" in rcpt and rcpt.split("@")[1] == self._config.domain:
                    try:
                        self._relay._deliver_local(rcpt, message)
                    except Exception:
                        pass

        if has_remote:
            self._queue.enqueue(session.envelope, message)

        self._metrics.messages_received += 1
        self._metrics.bytes_received += len(raw_message)

        # Reset for next transaction
        session.envelope = None
        session.state = SMTPState.GREETED if not session.authenticated_user else SMTPState.AUTHENTICATED

        return SMTPResponse(250, f"2.0.0 OK: message accepted for delivery")

    def _handle_rset(self, session: SMTPSession) -> SMTPResponse:
        """Handle RSET command."""
        session.envelope = None
        if session.authenticated_user:
            session.state = SMTPState.AUTHENTICATED
        elif session.tls_active:
            session.state = SMTPState.TLS_NEGOTIATED
        elif session.ehlo_domain:
            session.state = SMTPState.GREETED
        else:
            session.state = SMTPState.CONNECTED
        return SMTPResponse(250, "2.0.0 OK")

    def _handle_noop(self, session: SMTPSession) -> SMTPResponse:
        """Handle NOOP command."""
        return SMTPResponse(250, "2.0.0 OK")

    def _handle_vrfy(self, session: SMTPSession, arg: str) -> SMTPResponse:
        """Handle VRFY command."""
        return SMTPResponse(252, "2.5.2 Cannot VRFY user; send mail to attempt delivery")

    def _handle_quit(self, session: SMTPSession) -> SMTPResponse:
        """Handle QUIT command."""
        session.state = SMTPState.CLOSED
        return SMTPResponse(221, f"2.0.0 {self._config.hostname} closing connection")

    def _parse_email_address(self, text: str) -> str:
        """Extract email address from angle brackets or bare address."""
        text = text.strip()
        if text.startswith("<") and text.endswith(">"):
            return text[1:-1].strip()
        if "<" in text and ">" in text:
            start = text.index("<")
            end = text.index(">")
            return text[start + 1:end].strip()
        # Strip any trailing parameters
        if " " in text:
            text = text.split()[0]
        return text

    def get_metrics(self) -> ServerMetrics:
        """Return current server metrics."""
        return copy.copy(self._metrics)

    @property
    def uptime(self) -> float:
        """Server uptime in seconds."""
        if not self._started:
            return 0.0
        return time.time() - self._start_time

    @property
    def is_running(self) -> bool:
        """Whether the server is running."""
        return self._started


# ============================================================
# IMAP Server
# ============================================================


class IMAPServer:
    """IMAP server implementing RFC 3501.

    Provides mailbox access through the IMAP protocol with support
    for FETCH, SEARCH, STORE, COPY, MOVE, EXPUNGE, IDLE, and
    NAMESPACE commands.  All I/O is simulated.
    """

    CAPABILITIES = [
        "IMAP4rev1", "IDLE", "NAMESPACE", "UIDPLUS", "MOVE",
        "LITERAL+", "SASL-IR", "ID", "UNSELECT",
    ]

    def __init__(self, config: FizzMailConfig, storage: MaildirStorage,
                 credentials: Dict[str, str],
                 search_engine: Optional[IMAPSearchEngine] = None) -> None:
        self._config = config
        self._storage = storage
        self._credentials = credentials
        self._search = search_engine or IMAPSearchEngine()
        self._metrics = ServerMetrics()
        self._active_sessions: Dict[str, IMAPSession] = {}
        self._started = False
        self._start_time = 0.0

    def start(self) -> None:
        """Start the IMAP server."""
        self._started = True
        self._start_time = time.time()
        logger.info(
            "IMAP server started: %s:%d",
            self._config.hostname, self._config.imap_port,
        )

    def handle_connection(self, client_id: str,
                          commands: List[str]) -> List[str]:
        """Process a sequence of IMAP commands.

        Returns a list of response strings (with tags).
        """
        session = IMAPSession()
        self._active_sessions[client_id] = session
        self._metrics.active_imap_sessions += 1

        responses = []
        responses.append(f"* OK [{self._config.hostname}] {FIZZMAIL_SERVER_NAME} ready")

        for command_line in commands:
            result = self._process_command(session, command_line)
            if isinstance(result, list):
                responses.extend(result)
            else:
                responses.append(result)

            if session.state == IMAPState.LOGOUT:
                break

        self._active_sessions.pop(client_id, None)
        self._metrics.active_imap_sessions = max(0, self._metrics.active_imap_sessions - 1)
        return responses

    def _process_command(self, session: IMAPSession, line: str) -> Union[str, List[str]]:
        """Parse and dispatch an IMAP command."""
        line = line.strip()
        if not line:
            return "* BAD Empty command"

        parts = line.split(None, 2)
        if len(parts) < 2:
            return "* BAD Invalid command format"

        tag = parts[0]
        command = parts[1].upper()
        args = parts[2] if len(parts) > 2 else ""

        try:
            if command == "CAPABILITY":
                return self._handle_capability(session, tag)
            elif command == "LOGIN":
                return self._handle_login(session, tag, args)
            elif command == "AUTHENTICATE":
                return self._handle_authenticate(session, tag, args)
            elif command == "LIST":
                return self._handle_list(session, tag, args)
            elif command == "LSUB":
                return self._handle_lsub(session, tag, args)
            elif command == "CREATE":
                return self._handle_create(session, tag, args)
            elif command == "DELETE":
                return self._handle_delete(session, tag, args)
            elif command == "RENAME":
                return self._handle_rename(session, tag, args)
            elif command == "SUBSCRIBE":
                return self._handle_subscribe(session, tag, args)
            elif command == "UNSUBSCRIBE":
                return self._handle_unsubscribe(session, tag, args)
            elif command == "STATUS":
                return self._handle_status(session, tag, args)
            elif command == "SELECT":
                return self._handle_select(session, tag, args)
            elif command == "EXAMINE":
                return self._handle_examine(session, tag, args)
            elif command == "FETCH":
                return self._handle_fetch(session, tag, args)
            elif command == "STORE":
                return self._handle_store(session, tag, args)
            elif command == "COPY":
                return self._handle_copy(session, tag, args)
            elif command == "MOVE":
                return self._handle_move(session, tag, args)
            elif command == "SEARCH":
                return self._handle_search(session, tag, args)
            elif command == "UID":
                return self._handle_uid(session, tag, args)
            elif command == "EXPUNGE":
                return self._handle_expunge(session, tag)
            elif command == "CLOSE":
                return self._handle_close(session, tag)
            elif command == "IDLE":
                return self._handle_idle(session, tag)
            elif command == "NAMESPACE":
                return self._handle_namespace(session, tag)
            elif command == "NOOP":
                return self._handle_noop(session, tag)
            elif command == "LOGOUT":
                return self._handle_logout(session, tag)
            else:
                return f"{tag} BAD Unknown command: {command}"
        except FizzMailError as e:
            return f"{tag} NO {e}"

    def _handle_capability(self, session: IMAPSession, tag: str) -> List[str]:
        """Handle CAPABILITY command."""
        caps = " ".join(self.CAPABILITIES)
        return [
            f"* CAPABILITY {caps}",
            f"{tag} OK CAPABILITY completed",
        ]

    def _handle_login(self, session: IMAPSession, tag: str, args: str) -> str:
        """Handle LOGIN command."""
        if session.state != IMAPState.NOT_AUTHENTICATED:
            return f"{tag} BAD Already authenticated"

        parts = args.split(None, 1)
        if len(parts) < 2:
            return f"{tag} BAD LOGIN requires username and password"

        username = parts[0].strip('"')
        password = parts[1].strip('"')

        if self._credentials.get(username) == password:
            session.state = IMAPState.AUTHENTICATED
            session.authenticated_user = f"{username}@{self._config.domain}"
            self._metrics.auth_successes += 1
            return f"{tag} OK LOGIN completed"
        else:
            self._metrics.auth_failures += 1
            return f"{tag} NO LOGIN failed"

    def _handle_authenticate(self, session: IMAPSession, tag: str, args: str) -> str:
        """Handle AUTHENTICATE command."""
        if session.state != IMAPState.NOT_AUTHENTICATED:
            return f"{tag} BAD Already authenticated"
        return f"{tag} NO AUTHENTICATE not supported in simulation"

    def _handle_list(self, session: IMAPSession, tag: str, args: str) -> List[str]:
        """Handle LIST command."""
        if session.state == IMAPState.NOT_AUTHENTICATED:
            return [f"{tag} NO Not authenticated"]

        user = session.authenticated_user
        parts = args.split(None, 1)
        reference = parts[0].strip('"') if parts else ""
        pattern = parts[1].strip('"') if len(parts) > 1 else "*"

        mailboxes = self._storage.list_mailboxes(user, pattern)
        responses = []
        for mb in mailboxes:
            attrs = []
            if mb.name == "Trash":
                attrs.append(r"\Trash")
            elif mb.name == "Drafts":
                attrs.append(r"\Drafts")
            elif mb.name == "Sent":
                attrs.append(r"\Sent")
            elif mb.name == "Junk":
                attrs.append(r"\Junk")
            attr_str = " ".join(attrs)
            responses.append(f'* LIST ({attr_str}) "." "{mb.name}"')

        responses.append(f"{tag} OK LIST completed")
        return responses

    def _handle_lsub(self, session: IMAPSession, tag: str, args: str) -> List[str]:
        """Handle LSUB command."""
        if session.state == IMAPState.NOT_AUTHENTICATED:
            return [f"{tag} NO Not authenticated"]

        user = session.authenticated_user
        mailboxes = self._storage.list_mailboxes(user)
        responses = []
        for mb in mailboxes:
            if mb.subscribed:
                responses.append(f'* LSUB () "." "{mb.name}"')
        responses.append(f"{tag} OK LSUB completed")
        return responses

    def _handle_create(self, session: IMAPSession, tag: str, args: str) -> str:
        """Handle CREATE command."""
        if session.state == IMAPState.NOT_AUTHENTICATED:
            return f"{tag} NO Not authenticated"
        name = args.strip().strip('"')
        try:
            self._storage.create_mailbox(session.authenticated_user, name)
            return f"{tag} OK CREATE completed"
        except FizzMailMailboxExistsError:
            return f"{tag} NO Mailbox already exists"

    def _handle_delete(self, session: IMAPSession, tag: str, args: str) -> str:
        """Handle DELETE command."""
        if session.state == IMAPState.NOT_AUTHENTICATED:
            return f"{tag} NO Not authenticated"
        name = args.strip().strip('"')
        try:
            self._storage.delete_mailbox(session.authenticated_user, name)
            return f"{tag} OK DELETE completed"
        except FizzMailMailboxError as e:
            return f"{tag} NO {e}"

    def _handle_rename(self, session: IMAPSession, tag: str, args: str) -> str:
        """Handle RENAME command."""
        if session.state == IMAPState.NOT_AUTHENTICATED:
            return f"{tag} NO Not authenticated"
        parts = args.split(None, 1)
        if len(parts) < 2:
            return f"{tag} BAD RENAME requires old and new name"
        old_name = parts[0].strip('"')
        new_name = parts[1].strip('"')
        try:
            self._storage.rename_mailbox(session.authenticated_user, old_name, new_name)
            return f"{tag} OK RENAME completed"
        except FizzMailMailboxError as e:
            return f"{tag} NO {e}"

    def _handle_subscribe(self, session: IMAPSession, tag: str, args: str) -> str:
        """Handle SUBSCRIBE command."""
        if session.state == IMAPState.NOT_AUTHENTICATED:
            return f"{tag} NO Not authenticated"
        name = args.strip().strip('"')
        try:
            mb = self._storage.get_mailbox(session.authenticated_user, name)
            mb.subscribed = True
            return f"{tag} OK SUBSCRIBE completed"
        except FizzMailMailboxNotFoundError:
            return f"{tag} NO Mailbox not found"

    def _handle_unsubscribe(self, session: IMAPSession, tag: str, args: str) -> str:
        """Handle UNSUBSCRIBE command."""
        if session.state == IMAPState.NOT_AUTHENTICATED:
            return f"{tag} NO Not authenticated"
        name = args.strip().strip('"')
        try:
            mb = self._storage.get_mailbox(session.authenticated_user, name)
            mb.subscribed = False
            return f"{tag} OK UNSUBSCRIBE completed"
        except FizzMailMailboxNotFoundError:
            return f"{tag} NO Mailbox not found"

    def _handle_status(self, session: IMAPSession, tag: str, args: str) -> List[str]:
        """Handle STATUS command."""
        if session.state == IMAPState.NOT_AUTHENTICATED:
            return [f"{tag} NO Not authenticated"]

        # Parse mailbox name and status items
        match = re.match(r'"?([^"]+)"?\s+\(([^)]+)\)', args)
        if not match:
            return [f"{tag} BAD Invalid STATUS syntax"]

        name = match.group(1)
        items = match.group(2).upper().split()

        try:
            mb = self._storage.get_mailbox(session.authenticated_user, name)
        except FizzMailMailboxNotFoundError:
            return [f"{tag} NO Mailbox not found"]

        status_parts = []
        for item in items:
            if item == "MESSAGES":
                status_parts.append(f"MESSAGES {mb.exists}")
            elif item == "RECENT":
                status_parts.append(f"RECENT {mb.recent_count}")
            elif item == "UIDNEXT":
                status_parts.append(f"UIDNEXT {mb.uidnext}")
            elif item == "UIDVALIDITY":
                status_parts.append(f"UIDVALIDITY {mb.uidvalidity}")
            elif item == "UNSEEN":
                unseen = sum(1 for m in mb.messages if r"\Seen" not in m.flags)
                status_parts.append(f"UNSEEN {unseen}")

        status_str = " ".join(status_parts)
        return [
            f'* STATUS "{name}" ({status_str})',
            f"{tag} OK STATUS completed",
        ]

    def _handle_select(self, session: IMAPSession, tag: str, args: str) -> List[str]:
        """Handle SELECT command."""
        return self._select_mailbox(session, tag, args, readonly=False)

    def _handle_examine(self, session: IMAPSession, tag: str, args: str) -> List[str]:
        """Handle EXAMINE command (read-only SELECT)."""
        return self._select_mailbox(session, tag, args, readonly=True)

    def _select_mailbox(self, session: IMAPSession, tag: str, args: str,
                        readonly: bool) -> List[str]:
        """Select or examine a mailbox."""
        if session.state == IMAPState.NOT_AUTHENTICATED:
            return [f"{tag} NO Not authenticated"]

        name = args.strip().strip('"')
        try:
            mb = self._storage.get_mailbox(session.authenticated_user, name)
        except FizzMailMailboxNotFoundError:
            return [f"{tag} NO Mailbox not found"]

        session.state = IMAPState.SELECTED
        session.selected_mailbox = name
        session.selected_readonly = readonly

        unseen = 0
        for i, msg in enumerate(mb.messages, 1):
            if r"\Seen" not in msg.flags:
                unseen = i
                break

        flags_str = " ".join(sorted(IMAP_SYSTEM_FLAGS))
        perm_flags_str = " ".join(sorted(IMAP_PERMANENT_FLAGS)) + r" \*"

        responses = [
            f"* {mb.exists} EXISTS",
            f"* {mb.recent_count} RECENT",
            f"* OK [UNSEEN {unseen}] First unseen message",
            f"* OK [UIDVALIDITY {mb.uidvalidity}] UIDs valid",
            f"* OK [UIDNEXT {mb.uidnext}] Predicted next UID",
            f"* FLAGS ({flags_str})",
            f"* OK [PERMANENTFLAGS ({perm_flags_str})] Flags permitted",
        ]

        mode = "EXAMINE" if readonly else "SELECT"
        access = "[READ-ONLY]" if readonly else "[READ-WRITE]"
        responses.append(f"{tag} OK {access} {mode} completed")

        return responses

    def _handle_fetch(self, session: IMAPSession, tag: str, args: str) -> List[str]:
        """Handle FETCH command."""
        if session.state != IMAPState.SELECTED:
            return [f"{tag} NO No mailbox selected"]

        parts = args.split(None, 1)
        if len(parts) < 2:
            return [f"{tag} BAD FETCH requires sequence set and data items"]

        seq_set_str = parts[0]
        data_items_str = parts[1].strip("()")

        mb = self._storage.get_mailbox(session.authenticated_user, session.selected_mailbox)
        seq_nums = self._parse_sequence_set(seq_set_str, len(mb.messages))

        responses = []
        for seq_num in seq_nums:
            if seq_num < 1 or seq_num > len(mb.messages):
                continue
            msg = mb.messages[seq_num - 1]
            fetch_data = self._build_fetch_response(msg, data_items_str, seq_num)
            responses.append(f"* {seq_num} FETCH ({fetch_data})")

        responses.append(f"{tag} OK FETCH completed")
        return responses

    def _build_fetch_response(self, msg: MaildirMessage, items_str: str,
                              seq_num: int) -> str:
        """Build FETCH response data for a message."""
        parts = []
        items = items_str.upper().split()

        for item in items:
            if item == "FLAGS":
                flags_str = " ".join(sorted(msg.flags))
                parts.append(f"FLAGS ({flags_str})")
            elif item == "UID":
                parts.append(f"UID {msg.uid}")
            elif item == "INTERNALDATE":
                if msg.internal_date:
                    date_str = msg.internal_date.strftime("%d-%b-%Y %H:%M:%S %z")
                    if not date_str.endswith("+0000") and "+" not in date_str and "-" not in date_str[-5:]:
                        date_str += " +0000"
                    parts.append(f'INTERNALDATE "{date_str}"')
            elif item == "RFC822.SIZE":
                parts.append(f"RFC822.SIZE {msg.size}")
            elif item == "RFC822" or item == "BODY[]":
                raw = msg.raw or ""
                parts.append(f"RFC822 {{{len(raw)}}}\r\n{raw}")
                # Auto-set \Seen flag
                msg.flags.add(r"\Seen")
            elif item == "RFC822.HEADER" or item == "BODY[HEADER]":
                raw = msg.raw or ""
                header_end = raw.find("\r\n\r\n")
                if header_end == -1:
                    header_end = raw.find("\n\n")
                headers = raw[:header_end] if header_end >= 0 else raw
                parts.append(f"RFC822.HEADER {{{len(headers)}}}\r\n{headers}")
            elif item == "RFC822.TEXT" or item == "BODY[TEXT]":
                raw = msg.raw or ""
                body_start = raw.find("\r\n\r\n")
                if body_start == -1:
                    body_start = raw.find("\n\n")
                body = raw[body_start + 2:] if body_start >= 0 else ""
                parts.append(f"RFC822.TEXT {{{len(body)}}}\r\n{body}")
            elif item == "ENVELOPE":
                env = self._build_envelope(msg)
                parts.append(f"ENVELOPE {env}")
            elif item == "BODYSTRUCTURE" or item == "BODY":
                mime_builder = MIMEBuilder()
                if msg.raw:
                    mime_part = mime_builder.parse_mime(msg.raw)
                    bs = mime_builder.build_bodystructure(mime_part)
                else:
                    bs = '("TEXT" "PLAIN" ("CHARSET" "UTF-8") NIL NIL "7BIT" 0 0)'
                if item == "BODYSTRUCTURE":
                    parts.append(f"BODYSTRUCTURE {bs}")
                else:
                    parts.append(f"BODY {bs}")

        return " ".join(parts)

    def _build_envelope(self, msg: MaildirMessage) -> str:
        """Build IMAP ENVELOPE response for a message."""
        date = msg.headers.get("Date", "")
        subject = msg.subject or msg.headers.get("Subject", "")
        from_addr = msg.from_addr or msg.headers.get("From", "")
        to_addr = msg.to_addr or msg.headers.get("To", "")
        message_id = msg.headers.get("Message-ID", "")

        def _quote(s):
            if not s:
                return "NIL"
            return f'"{s}"'

        return (
            f"({_quote(date)} {_quote(subject)} "
            f"(({_quote(from_addr)} NIL NIL NIL)) "  # from
            f"(({_quote(from_addr)} NIL NIL NIL)) "  # sender
            f"(({_quote(from_addr)} NIL NIL NIL)) "  # reply-to
            f"(({_quote(to_addr)} NIL NIL NIL)) "    # to
            f"NIL NIL NIL "                           # cc, bcc, in-reply-to
            f"{_quote(message_id)})"
        )

    def _handle_store(self, session: IMAPSession, tag: str, args: str) -> List[str]:
        """Handle STORE command."""
        if session.state != IMAPState.SELECTED:
            return [f"{tag} NO No mailbox selected"]
        if session.selected_readonly:
            return [f"{tag} NO Mailbox is read-only"]

        # Parse: sequence_set action (flags)
        match = re.match(r'(\S+)\s+([+-]?FLAGS(?:\.SILENT)?)\s+\(([^)]*)\)', args, re.IGNORECASE)
        if not match:
            return [f"{tag} BAD Invalid STORE syntax"]

        seq_set_str = match.group(1)
        action_str = match.group(2).upper()
        flags_str = match.group(3)

        flags = {f.strip() for f in flags_str.split() if f.strip()}
        silent = ".SILENT" in action_str
        action_str = action_str.replace(".SILENT", "")

        if action_str == "+FLAGS":
            action = IMAPFlagAction.ADD
        elif action_str == "-FLAGS":
            action = IMAPFlagAction.REMOVE
        else:
            action = IMAPFlagAction.SET

        mb = self._storage.get_mailbox(session.authenticated_user, session.selected_mailbox)
        seq_nums = self._parse_sequence_set(seq_set_str, len(mb.messages))

        responses = []
        for seq_num in seq_nums:
            if seq_num < 1 or seq_num > len(mb.messages):
                continue
            msg = mb.messages[seq_num - 1]
            new_flags = self._storage.update_flags(
                session.authenticated_user, session.selected_mailbox,
                msg.uid, flags, action
            )
            if not silent:
                flags_str = " ".join(sorted(new_flags))
                responses.append(f"* {seq_num} FETCH (FLAGS ({flags_str}))")

        responses.append(f"{tag} OK STORE completed")
        return responses

    def _handle_copy(self, session: IMAPSession, tag: str, args: str) -> str:
        """Handle COPY command."""
        if session.state != IMAPState.SELECTED:
            return f"{tag} NO No mailbox selected"

        parts = args.split(None, 1)
        if len(parts) < 2:
            return f"{tag} BAD COPY requires sequence set and mailbox"

        seq_set_str = parts[0]
        target_name = parts[1].strip().strip('"')

        mb = self._storage.get_mailbox(session.authenticated_user, session.selected_mailbox)
        seq_nums = self._parse_sequence_set(seq_set_str, len(mb.messages))

        try:
            self._storage.get_mailbox(session.authenticated_user, target_name)
        except FizzMailMailboxNotFoundError:
            return f"{tag} NO [TRYCREATE] Target mailbox does not exist"

        for seq_num in seq_nums:
            if seq_num < 1 or seq_num > len(mb.messages):
                continue
            msg = mb.messages[seq_num - 1]
            # Create a MailMessage from MaildirMessage for delivery
            mail_msg = MailMessage(
                message_id=msg.headers.get("Message-ID", ""),
                subject=msg.subject,
                from_addr=RFC5322HeaderParser().parse_address(msg.from_addr) if msg.from_addr else None,
                to_addrs=[RFC5322HeaderParser().parse_address(msg.to_addr)] if msg.to_addr else [],
                headers=dict(msg.headers),
                raw=msg.raw,
                size=msg.size,
            )
            self._storage.deliver(session.authenticated_user, target_name, mail_msg)

        return f"{tag} OK COPY completed"

    def _handle_move(self, session: IMAPSession, tag: str, args: str) -> List[str]:
        """Handle MOVE command (COPY + delete + expunge)."""
        if session.state != IMAPState.SELECTED:
            return [f"{tag} NO No mailbox selected"]

        copy_result = self._handle_copy(session, tag, args)
        if "NO" in copy_result:
            return [copy_result]

        # Mark source messages as deleted
        parts = args.split(None, 1)
        seq_set_str = parts[0]
        mb = self._storage.get_mailbox(session.authenticated_user, session.selected_mailbox)
        seq_nums = self._parse_sequence_set(seq_set_str, len(mb.messages))

        for seq_num in seq_nums:
            if seq_num < 1 or seq_num > len(mb.messages):
                continue
            mb.messages[seq_num - 1].flags.add(r"\Deleted")

        # Expunge
        expunged = self._storage.expunge(session.authenticated_user, session.selected_mailbox)
        responses = [f"* {n} EXPUNGE" for n in expunged]
        responses.append(f"{tag} OK MOVE completed")
        return responses

    def _handle_search(self, session: IMAPSession, tag: str, args: str) -> List[str]:
        """Handle SEARCH command."""
        if session.state != IMAPState.SELECTED:
            return [f"{tag} NO No mailbox selected"]

        mb = self._storage.get_mailbox(session.authenticated_user, session.selected_mailbox)
        results = self._search.search(mb, args, use_uid=False)

        result_str = " ".join(str(n) for n in results)
        return [
            f"* SEARCH {result_str}" if results else "* SEARCH",
            f"{tag} OK SEARCH completed",
        ]

    def _handle_uid(self, session: IMAPSession, tag: str, args: str) -> Union[str, List[str]]:
        """Handle UID command prefix."""
        if session.state != IMAPState.SELECTED:
            return f"{tag} NO No mailbox selected"

        parts = args.split(None, 1)
        if not parts:
            return f"{tag} BAD UID requires subcommand"

        sub_cmd = parts[0].upper()
        sub_args = parts[1] if len(parts) > 1 else ""

        if sub_cmd == "FETCH":
            return self._handle_uid_fetch(session, tag, sub_args)
        elif sub_cmd == "STORE":
            return self._handle_uid_store(session, tag, sub_args)
        elif sub_cmd == "COPY":
            return self._handle_uid_copy(session, tag, sub_args)
        elif sub_cmd == "SEARCH":
            return self._handle_uid_search(session, tag, sub_args)
        else:
            return f"{tag} BAD Unknown UID subcommand: {sub_cmd}"

    def _handle_uid_fetch(self, session: IMAPSession, tag: str, args: str) -> List[str]:
        """Handle UID FETCH command."""
        parts = args.split(None, 1)
        if len(parts) < 2:
            return [f"{tag} BAD UID FETCH requires UID set and data items"]

        uid_set_str = parts[0]
        data_items_str = parts[1].strip("()")

        mb = self._storage.get_mailbox(session.authenticated_user, session.selected_mailbox)

        responses = []
        for seq_num, msg in enumerate(mb.messages, 1):
            if self._uid_in_set(msg.uid, uid_set_str):
                # Always include UID in response
                items = data_items_str
                if "UID" not in items.upper():
                    items = f"UID {items}"
                fetch_data = self._build_fetch_response(msg, items, seq_num)
                responses.append(f"* {seq_num} FETCH ({fetch_data})")

        responses.append(f"{tag} OK UID FETCH completed")
        return responses

    def _handle_uid_store(self, session: IMAPSession, tag: str, args: str) -> List[str]:
        """Handle UID STORE command."""
        # Rewrite UID ranges to sequence numbers
        match = re.match(r'(\S+)\s+(.*)', args)
        if not match:
            return [f"{tag} BAD Invalid UID STORE syntax"]

        uid_set_str = match.group(1)
        rest = match.group(2)

        mb = self._storage.get_mailbox(session.authenticated_user, session.selected_mailbox)

        # Find sequence numbers for matching UIDs
        seq_nums = []
        for seq_num, msg in enumerate(mb.messages, 1):
            if self._uid_in_set(msg.uid, uid_set_str):
                seq_nums.append(seq_num)

        # Delegate to regular STORE with modified sequence set
        if seq_nums:
            seq_set = ",".join(str(n) for n in seq_nums)
            return self._handle_store(session, tag, f"{seq_set} {rest}")

        return [f"{tag} OK UID STORE completed"]

    def _handle_uid_copy(self, session: IMAPSession, tag: str, args: str) -> str:
        """Handle UID COPY command."""
        parts = args.split(None, 1)
        if len(parts) < 2:
            return f"{tag} BAD UID COPY requires UID set and mailbox"

        uid_set_str = parts[0]
        target = parts[1]

        mb = self._storage.get_mailbox(session.authenticated_user, session.selected_mailbox)
        seq_nums = []
        for seq_num, msg in enumerate(mb.messages, 1):
            if self._uid_in_set(msg.uid, uid_set_str):
                seq_nums.append(seq_num)

        if seq_nums:
            seq_set = ",".join(str(n) for n in seq_nums)
            return self._handle_copy(session, tag, f"{seq_set} {target}")

        return f"{tag} OK UID COPY completed"

    def _handle_uid_search(self, session: IMAPSession, tag: str, args: str) -> List[str]:
        """Handle UID SEARCH command."""
        if session.state != IMAPState.SELECTED:
            return [f"{tag} NO No mailbox selected"]

        mb = self._storage.get_mailbox(session.authenticated_user, session.selected_mailbox)
        results = self._search.search(mb, args, use_uid=True)

        result_str = " ".join(str(n) for n in results)
        return [
            f"* SEARCH {result_str}" if results else "* SEARCH",
            f"{tag} OK UID SEARCH completed",
        ]

    def _handle_expunge(self, session: IMAPSession, tag: str) -> List[str]:
        """Handle EXPUNGE command."""
        if session.state != IMAPState.SELECTED:
            return [f"{tag} NO No mailbox selected"]
        if session.selected_readonly:
            return [f"{tag} NO Mailbox is read-only"]

        expunged = self._storage.expunge(
            session.authenticated_user, session.selected_mailbox
        )
        responses = [f"* {n} EXPUNGE" for n in expunged]
        responses.append(f"{tag} OK EXPUNGE completed")
        return responses

    def _handle_close(self, session: IMAPSession, tag: str) -> str:
        """Handle CLOSE command."""
        if session.state != IMAPState.SELECTED:
            return f"{tag} NO No mailbox selected"

        if not session.selected_readonly:
            self._storage.expunge(
                session.authenticated_user, session.selected_mailbox
            )

        session.state = IMAPState.AUTHENTICATED
        session.selected_mailbox = ""
        return f"{tag} OK CLOSE completed"

    def _handle_idle(self, session: IMAPSession, tag: str) -> List[str]:
        """Handle IDLE command."""
        if session.state != IMAPState.SELECTED:
            return [f"{tag} NO No mailbox selected"]

        mb = self._storage.get_mailbox(session.authenticated_user, session.selected_mailbox)
        return [
            "+ idling",
            f"* {mb.exists} EXISTS",
            f"* {mb.recent_count} RECENT",
            f"{tag} OK IDLE terminated",
        ]

    def _handle_namespace(self, session: IMAPSession, tag: str) -> List[str]:
        """Handle NAMESPACE command."""
        if session.state == IMAPState.NOT_AUTHENTICATED:
            return [f"{tag} NO Not authenticated"]

        return [
            '* NAMESPACE (("" ".")) NIL NIL',
            f"{tag} OK NAMESPACE completed",
        ]

    def _handle_noop(self, session: IMAPSession, tag: str) -> str:
        """Handle NOOP command."""
        return f"{tag} OK NOOP completed"

    def _handle_logout(self, session: IMAPSession, tag: str) -> List[str]:
        """Handle LOGOUT command."""
        session.state = IMAPState.LOGOUT
        return [
            f"* BYE {FIZZMAIL_SERVER_NAME} closing connection",
            f"{tag} OK LOGOUT completed",
        ]

    def _parse_sequence_set(self, text: str, total: int) -> List[int]:
        """Parse IMAP sequence set notation (e.g., '1:3,5,7:*')."""
        result = []
        for part in text.split(","):
            if ":" in part:
                start_str, end_str = part.split(":", 1)
                start = int(start_str) if start_str != "*" else total
                end = int(end_str) if end_str != "*" else total
                for i in range(min(start, end), max(start, end) + 1):
                    if 1 <= i <= total:
                        result.append(i)
            else:
                val = total if part == "*" else int(part)
                if 1 <= val <= total:
                    result.append(val)
        return sorted(set(result))

    def _uid_in_set(self, uid: int, uid_set_str: str) -> bool:
        """Check if a UID is in a UID set expression."""
        for part in uid_set_str.split(","):
            if ":" in part:
                start_str, end_str = part.split(":", 1)
                start = int(start_str) if start_str != "*" else uid
                end = int(end_str) if end_str != "*" else 999999999
                if min(start, end) <= uid <= max(start, end):
                    return True
            else:
                val = uid if part == "*" else int(part)
                if uid == val:
                    return True
        return False

    def get_metrics(self) -> ServerMetrics:
        """Return current server metrics."""
        return copy.copy(self._metrics)

    @property
    def uptime(self) -> float:
        """Server uptime in seconds."""
        if not self._started:
            return 0.0
        return time.time() - self._start_time


# ============================================================
# Dashboard
# ============================================================


class FizzMailDashboard:
    """ASCII dashboard for FizzMail server status display.

    Renders SMTP status, IMAP status, queue statistics, security
    module status, and storage metrics in a fixed-width terminal
    format.
    """

    def __init__(self, smtp_server: SMTPServer, imap_server: IMAPServer,
                 queue: MessageQueue, storage: MaildirStorage,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._smtp = smtp_server
        self._imap = imap_server
        self._queue = queue
        self._storage = storage
        self._width = width

    def render(self) -> str:
        """Render the complete FizzMail dashboard."""
        sections = [
            self._render_header("FizzMail Server Dashboard"),
            self._render_smtp_status(),
            self._render_imap_status(),
            self._render_queue_status(),
            self._render_storage_status(),
        ]
        return "\n".join(sections)

    def _render_header(self, title: str) -> str:
        """Render a section header."""
        line = "=" * self._width
        centered = title.center(self._width)
        return f"{line}\n{centered}\n{line}"

    def _render_smtp_status(self) -> str:
        """Render SMTP server status section."""
        m = self._smtp.get_metrics()
        lines = [
            f"  SMTP Server ({FIZZMAIL_VERSION})",
            f"  {'─' * (self._width - 4)}",
            f"  Status:        {'RUNNING' if self._smtp.is_running else 'STOPPED'}",
            f"  Uptime:        {self._smtp.uptime:.1f}s",
            f"  Received:      {m.messages_received}",
            f"  Sent:          {m.messages_sent}",
            f"  Bounced:       {m.messages_bounced}",
            f"  Active:        {m.active_smtp_sessions} sessions",
            f"  Auth OK/Fail:  {m.auth_successes}/{m.auth_failures}",
            f"  Bytes In:      {m.bytes_received}",
        ]
        return "\n".join(lines)

    def _render_imap_status(self) -> str:
        """Render IMAP server status section."""
        m = self._imap.get_metrics()
        lines = [
            f"  IMAP Server",
            f"  {'─' * (self._width - 4)}",
            f"  Status:        {'RUNNING' if self._imap._started else 'STOPPED'}",
            f"  Uptime:        {self._imap.uptime:.1f}s",
            f"  Active:        {m.active_imap_sessions} sessions",
            f"  Auth OK/Fail:  {m.auth_successes}/{m.auth_failures}",
        ]
        return "\n".join(lines)

    def _render_queue_status(self) -> str:
        """Render message queue status section."""
        stats = self._queue.get_queue_stats()
        lines = [
            f"  Message Queue",
            f"  {'─' * (self._width - 4)}",
            f"  Total Enqueued: {stats.get('total_enqueued', 0)}",
            f"  Pending:        {stats.get('PENDING', 0)}",
            f"  Sending:        {stats.get('SENDING', 0)}",
            f"  Deferred:       {stats.get('DEFERRED', 0)}",
            f"  Sent:           {stats.get('total_sent', 0)}",
            f"  Bounced:        {stats.get('total_bounced', 0)}",
            f"  Failed:         {stats.get('total_failed', 0)}",
        ]
        return "\n".join(lines)

    def _render_storage_status(self) -> str:
        """Render storage status section."""
        users = self._storage.get_all_users()
        total_messages = 0
        total_size = 0
        for user in users:
            for mb in self._storage.list_mailboxes(user):
                total_messages += mb.exists
                for msg in mb.messages:
                    total_size += msg.size

        lines = [
            f"  Storage (Maildir)",
            f"  {'─' * (self._width - 4)}",
            f"  Users:          {len(users)}",
            f"  Total Messages: {total_messages}",
            f"  Total Size:     {total_size} bytes",
        ]
        return "\n".join(lines)


# ============================================================
# Middleware
# ============================================================


class FizzMailMiddleware(IMiddleware):
    """Middleware integration for the FizzMail email server.

    Connects FizzMail to the platform's middleware pipeline, recording
    server metrics in the processing context and providing dashboard
    rendering capabilities.
    """

    def __init__(self, smtp_server: SMTPServer, imap_server: IMAPServer,
                 dashboard: FizzMailDashboard, queue: MessageQueue,
                 storage: MaildirStorage, config: FizzMailConfig) -> None:
        self._smtp = smtp_server
        self._imap = imap_server
        self._dashboard = dashboard
        self._queue = queue
        self._storage = storage
        self._config = config

    def get_name(self) -> str:
        """Return the middleware name."""
        return "fizzmail"

    def process(self, context: ProcessingContext, next_handler: Any) -> ProcessingContext:
        """Record FizzMail metrics and delegate to the next handler."""
        smtp_metrics = self._smtp.get_metrics()
        imap_metrics = self._imap.get_metrics()

        context.metadata["fizzmail_version"] = FIZZMAIL_VERSION
        context.metadata["fizzmail_smtp_running"] = self._smtp.is_running
        context.metadata["fizzmail_imap_running"] = self._imap._started
        context.metadata["fizzmail_messages_received"] = smtp_metrics.messages_received
        context.metadata["fizzmail_messages_sent"] = smtp_metrics.messages_sent
        context.metadata["fizzmail_messages_bounced"] = smtp_metrics.messages_bounced
        context.metadata["fizzmail_queue_size"] = self._queue.size
        context.metadata["fizzmail_spf_checks"] = smtp_metrics.spf_checks
        context.metadata["fizzmail_dkim_checks"] = smtp_metrics.dkim_checks

        if next_handler is not None:
            return next_handler(context)
        return context

    def get_priority(self) -> int:
        """Return the middleware priority."""
        return MIDDLEWARE_PRIORITY

    def render_dashboard(self) -> str:
        """Render the FizzMail dashboard."""
        return self._dashboard.render()

    def render_status(self) -> str:
        """Render a one-line status summary."""
        m = self._smtp.get_metrics()
        return (
            f"FizzMail {FIZZMAIL_VERSION} | "
            f"SMTP: {'UP' if self._smtp.is_running else 'DOWN'} | "
            f"IMAP: {'UP' if self._imap._started else 'DOWN'} | "
            f"Recv: {m.messages_received} | Queue: {self._queue.size}"
        )

    def render_mailboxes(self) -> str:
        """Render a list of all mailboxes across all users."""
        lines = [
            "=" * self._config.dashboard_width,
            "FizzMail Mailbox Listing".center(self._config.dashboard_width),
            "=" * self._config.dashboard_width,
        ]
        for user in self._storage.get_all_users():
            lines.append(f"\n  User: {user}")
            lines.append(f"  {'─' * (self._config.dashboard_width - 4)}")
            for mb in self._storage.list_mailboxes(user):
                unseen = sum(1 for m in mb.messages if r"\Seen" not in m.flags)
                lines.append(
                    f"  {mb.name:<20} {mb.exists:>5} messages ({unseen} unseen)"
                )
            usage = self._storage.get_quota_usage(user)
            quota = self._storage.get_quota(user)
            pct = (usage / quota * 100) if quota > 0 else 0
            lines.append(f"  Quota: {usage}/{quota} bytes ({pct:.1f}%)")
        return "\n".join(lines)

    def render_send_result(self, send_spec: str) -> str:
        """Simulate sending a test email and return the result."""
        parts = send_spec.split(",", 3)
        if len(parts) < 4:
            return "Error: --fizzmail-send format: from,to,subject,body"

        from_addr, to_addr, subject, body = parts

        parser = RFC5322HeaderParser()
        message = MailMessage(
            message_id=parser.generate_message_id(self._config.domain),
            date=datetime.now(timezone.utc),
            from_addr=parser.parse_address(from_addr),
            to_addrs=[parser.parse_address(to_addr)],
            subject=subject,
            body_text=body,
        )

        mime_builder = MIMEBuilder()
        message.raw = mime_builder.build_message(message, self._config)

        envelope = Envelope(
            mail_from=from_addr.strip(),
            rcpt_to=[to_addr.strip()],
            size=message.size,
        )

        msg_id = self._queue.enqueue(envelope, message)
        delivered = self._queue.process_queue(self._smtp._relay)

        status = "DELIVERED" if msg_id in delivered else "QUEUED"

        return (
            f"FizzMail Send Result\n"
            f"  From:       {from_addr}\n"
            f"  To:         {to_addr}\n"
            f"  Subject:    {subject}\n"
            f"  Message-ID: {message.message_id}\n"
            f"  Status:     {status}\n"
            f"  Size:       {message.size} bytes"
        )

    def render_search_result(self, query: str) -> str:
        """Simulate searching mailboxes and return results."""
        lines = [f"FizzMail Search: \"{query}\"", ""]
        total_matches = 0

        for user in self._storage.get_all_users():
            for mb in self._storage.list_mailboxes(user):
                for msg in mb.messages:
                    if (query.lower() in msg.subject.lower() or
                            query.lower() in msg.from_addr.lower() or
                            query.lower() in (msg.raw or "").lower()):
                        total_matches += 1
                        lines.append(
                            f"  [{user}/{mb.name}] UID={msg.uid} "
                            f"From={msg.from_addr} Subject={msg.subject}"
                        )

        lines.append(f"\n  Total matches: {total_matches}")
        return "\n".join(lines)

    def render_idle_simulation(self) -> str:
        """Simulate IMAP IDLE push notifications."""
        lines = [
            "FizzMail IDLE Simulation",
            "  + idling",
        ]
        for user in self._storage.get_all_users():
            try:
                mb = self._storage.get_mailbox(user, "INBOX")
                lines.append(f"  * {mb.exists} EXISTS (user={user})")
                lines.append(f"  * {mb.recent_count} RECENT (user={user})")
            except FizzMailMailboxNotFoundError:
                pass
        lines.append("  DONE")
        return "\n".join(lines)


# ============================================================
# Factory Function
# ============================================================


def create_fizzmail_subsystem(
    smtp_port: int = DEFAULT_SMTP_PORT,
    imap_port: int = DEFAULT_IMAP_PORT,
    domain: str = DEFAULT_DOMAIN,
    hostname: str = DEFAULT_HOSTNAME,
    enable_tls: bool = True,
    enable_auth: bool = True,
    enable_dkim_sign: bool = True,
    enable_dkim_verify: bool = True,
    enable_spf: bool = True,
    enable_dmarc: bool = True,
    enable_greylist: bool = False,
    enable_rbl: bool = False,
    max_message_size: int = DEFAULT_MAX_MESSAGE_SIZE,
    quota_default: int = DEFAULT_QUOTA,
    retry_max_attempts: int = DEFAULT_RETRY_MAX_ATTEMPTS,
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[SMTPServer, IMAPServer, FizzMailDashboard, FizzMailMiddleware]:
    """Factory function for creating the FizzMail subsystem.

    Constructs a fully wired SMTP server, IMAP server, message queue,
    storage backend, and all security modules.  Creates default user
    accounts with standard mailbox hierarchies and delivers a welcome
    message to each.
    """
    config = FizzMailConfig(
        smtp_port=smtp_port,
        imap_port=imap_port,
        domain=domain,
        hostname=hostname,
        enable_tls=enable_tls,
        enable_auth=enable_auth,
        enable_dkim_sign=enable_dkim_sign,
        enable_dkim_verify=enable_dkim_verify,
        enable_spf=enable_spf,
        enable_dmarc=enable_dmarc,
        enable_greylist=enable_greylist,
        enable_rbl=enable_rbl,
        max_message_size=max_message_size,
        quota_default=quota_default,
        retry_max_attempts=retry_max_attempts,
        dashboard_width=dashboard_width,
    )

    # Storage
    storage = MaildirStorage(config)

    # Security modules
    authenticator = SMTPAuthenticator(config.credentials)
    tls_handler = SMTPTLSHandler(config)
    spf_validator = SPFValidator() if enable_spf else None
    dkim_signer = DKIMSigner(domain, config.dkim_selector) if enable_dkim_sign else None
    dkim_verifier = DKIMVerifier() if enable_dkim_verify else None
    dmarc_evaluator = DMARCEvaluator() if enable_dmarc else None
    greylister = Greylister(config) if enable_greylist else None
    rbl_checker = RBLChecker(config.rbl_zones) if enable_rbl else None

    # Queue and relay
    queue = MessageQueue(config)
    relay_router = RelayRouter(config, storage)

    # SMTP server
    smtp_server = SMTPServer(
        config=config,
        authenticator=authenticator,
        tls_handler=tls_handler,
        queue=queue,
        relay_router=relay_router,
        spf_validator=spf_validator,
        dkim_signer=dkim_signer,
        dkim_verifier=dkim_verifier,
        dmarc_evaluator=dmarc_evaluator,
        greylister=greylister,
        rbl_checker=rbl_checker,
        storage=storage,
    )

    # IMAP server
    search_engine = IMAPSearchEngine()
    imap_server = IMAPServer(
        config=config,
        storage=storage,
        credentials=config.credentials,
        search_engine=search_engine,
    )

    # Dashboard
    dashboard = FizzMailDashboard(smtp_server, imap_server, queue, storage, dashboard_width)

    # Middleware
    middleware = FizzMailMiddleware(smtp_server, imap_server, dashboard, queue, storage, config)

    # Start servers
    smtp_server.start()
    imap_server.start()

    # Create default accounts and deliver welcome messages
    parser = RFC5322HeaderParser()
    mime_builder = MIMEBuilder()

    for username in config.credentials:
        user = f"{username}@{domain}"
        storage.create_user(user)

        welcome = MailMessage(
            message_id=parser.generate_message_id(domain),
            date=datetime.now(timezone.utc),
            from_addr=EmailAddress(
                display_name="FizzMail System",
                local_part="postmaster",
                domain=domain,
            ),
            to_addrs=[EmailAddress(local_part=username, domain=domain)],
            subject=f"Welcome to {FIZZMAIL_SERVER_NAME}",
            body_text=(
                f"Welcome to the Enterprise FizzBuzz Platform mail system.\n\n"
                f"Your account {username}@{domain} has been provisioned with\n"
                f"the following mailboxes: {', '.join(DEFAULT_MAILBOXES)}.\n\n"
                f"Storage quota: {quota_default // (1024 * 1024)} MB\n\n"
                f"This message was generated automatically by FizzMail {FIZZMAIL_VERSION}."
            ),
        )
        welcome.raw = mime_builder.build_message(welcome, config)
        storage.deliver(user, "INBOX", welcome)

    logger.info(
        "FizzMail subsystem initialized: SMTP=%s:%d IMAP=%s:%d domain=%s users=%d",
        hostname, smtp_port, hostname, imap_port, domain, len(config.credentials),
    )

    return smtp_server, imap_server, dashboard, middleware
