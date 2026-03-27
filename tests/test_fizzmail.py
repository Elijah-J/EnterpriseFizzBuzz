"""
Tests for enterprise_fizzbuzz.infrastructure.fizzmail

Comprehensive test suite for the FizzMail SMTP/IMAP email server
subsystem covering RFC 5322 header parsing, MIME construction,
SMTP command processing, authentication (PLAIN/LOGIN/CRAM-MD5),
STARTTLS, message queue with exponential backoff, relay routing,
SPF validation, DKIM signing/verification, DMARC evaluation,
greylisting, RBL/DNSBL checking, bounce handling, IMAP command
processing, Maildir storage, quota enforcement, IMAP SEARCH,
UID operations, and middleware integration.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from unittest.mock import MagicMock, patch

import pytest

from enterprise_fizzbuzz.infrastructure.fizzmail import (
    # Constants
    FIZZMAIL_VERSION,
    FIZZMAIL_SERVER_NAME,
    DEFAULT_SMTP_PORT,
    DEFAULT_IMAP_PORT,
    DEFAULT_DOMAIN,
    DEFAULT_HOSTNAME,
    DEFAULT_MAX_MESSAGE_SIZE,
    DEFAULT_MAX_RECIPIENTS,
    DEFAULT_QUOTA,
    DEFAULT_DKIM_SELECTOR,
    DEFAULT_DASHBOARD_WIDTH,
    MIDDLEWARE_PRIORITY,
    SMTP_REPLIES,
    IMAP_SYSTEM_FLAGS,
    IMAP_PERMANENT_FLAGS,
    MAILDIR_FLAG_MAP,
    MAILDIR_FLAG_REVERSE,
    DEFAULT_MAILBOXES,
    DEFAULT_CREDENTIALS,
    DKIM_SIMULATED_PRIVATE_KEY,
    DKIM_SIMULATED_PUBLIC_KEY,
    # Enums
    SMTPState,
    IMAPState,
    SMTPCommand,
    IMAPCommand,
    AuthMechanism,
    QueueStatus,
    SPFResult,
    DKIMResult,
    DMARCPolicy,
    DMARCAlignment,
    MIMEMultipartType,
    ContentTransferEncoding,
    FetchDataItem,
    IMAPFlagAction,
    # Dataclasses
    FizzMailConfig,
    EmailAddress,
    SMTPResponse,
    Envelope,
    MIMEPart,
    MailMessage,
    QueueEntry,
    MaildirMessage,
    Mailbox,
    SMTPSession,
    IMAPSession,
    GreylistEntry,
    SPFRecord,
    SPFMechanism,
    DKIMSignatureData,
    DMARCRecord,
    DSNRecipient,
    DSNReport,
    ServerMetrics,
    # Classes
    RFC5322HeaderParser,
    MIMEBuilder,
    SMTPTLSHandler,
    SMTPAuthenticator,
    MessageQueue,
    RelayRouter,
    SPFValidator,
    DKIMSigner,
    DKIMVerifier,
    DMARCEvaluator,
    Greylister,
    RBLChecker,
    BounceHandler,
    MaildirStorage,
    QuotaEnforcer,
    IMAPSearchEngine,
    SMTPServer,
    IMAPServer,
    FizzMailDashboard,
    FizzMailMiddleware,
    create_fizzmail_subsystem,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def config():
    """Default FizzMail configuration."""
    return FizzMailConfig()


@pytest.fixture
def storage(config):
    """Maildir storage with default user."""
    s = MaildirStorage(config)
    s.create_user(f"postmaster@{config.domain}")
    return s


@pytest.fixture
def parser():
    """RFC 5322 header parser."""
    return RFC5322HeaderParser()


@pytest.fixture
def mime_builder():
    """MIME builder."""
    return MIMEBuilder()


@pytest.fixture
def authenticator():
    """SMTP authenticator with default credentials."""
    return SMTPAuthenticator(dict(DEFAULT_CREDENTIALS))


@pytest.fixture
def queue(config):
    """Message queue."""
    return MessageQueue(config)


@pytest.fixture
def subsystem():
    """Complete FizzMail subsystem."""
    return create_fizzmail_subsystem()


def _make_message(from_addr="test@fizzbuzz.local", to_addr="user@fizzbuzz.local",
                  subject="Test", body="Hello", config=None):
    """Helper to create a test MailMessage."""
    if config is None:
        config = FizzMailConfig()
    parser = RFC5322HeaderParser()
    msg = MailMessage(
        message_id=parser.generate_message_id(config.domain),
        date=datetime.now(timezone.utc),
        from_addr=parser.parse_address(from_addr),
        to_addrs=[parser.parse_address(to_addr)],
        subject=subject,
        body_text=body,
    )
    builder = MIMEBuilder()
    msg.raw = builder.build_message(msg, config)
    return msg


# ============================================================
# TestRFC5322HeaderParser
# ============================================================


class TestRFC5322HeaderParser:
    """Tests for RFC 5322 header parsing."""

    def test_parse_simple_headers(self, parser):
        raw = "From: alice@example.com\nTo: bob@example.com\nSubject: Hello"
        headers = parser.parse_headers(raw)
        assert headers["From"] == "alice@example.com"
        assert headers["To"] == "bob@example.com"
        assert headers["Subject"] == "Hello"

    def test_parse_folded_headers(self, parser):
        raw = "Subject: This is a very long\n subject that wraps"
        headers = parser.parse_headers(raw)
        assert "very long" in headers["Subject"]
        assert "wraps" in headers["Subject"]

    def test_parse_address_bare(self, parser):
        addr = parser.parse_address("user@example.com")
        assert addr.local_part == "user"
        assert addr.domain == "example.com"
        assert addr.display_name == ""

    def test_parse_address_with_display_name(self, parser):
        addr = parser.parse_address("Alice Smith <alice@example.com>")
        assert addr.local_part == "alice"
        assert addr.domain == "example.com"
        assert addr.display_name == "Alice Smith"

    def test_parse_address_quoted_name(self, parser):
        addr = parser.parse_address('"Alice Smith" <alice@example.com>')
        assert addr.display_name == "Alice Smith"
        assert addr.local_part == "alice"

    def test_parse_address_list(self, parser):
        text = "alice@example.com, Bob <bob@example.com>, charlie@test.com"
        addrs = parser.parse_address_list(text)
        assert len(addrs) == 3
        assert addrs[0].local_part == "alice"
        assert addrs[1].display_name == "Bob"
        assert addrs[2].domain == "test.com"

    def test_parse_address_list_single(self, parser):
        addrs = parser.parse_address_list("user@test.com")
        assert len(addrs) == 1

    def test_parse_date_full(self, parser):
        dt = parser.parse_date("Mon, 15 Mar 2026 10:30:45 +0000")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 3
        assert dt.day == 15
        assert dt.hour == 10
        assert dt.minute == 30
        assert dt.second == 45

    def test_parse_date_no_day_of_week(self, parser):
        dt = parser.parse_date("15 Mar 2026 10:30:45 +0000")
        assert dt is not None
        assert dt.day == 15

    def test_parse_date_no_seconds(self, parser):
        dt = parser.parse_date("Mon, 15 Mar 2026 10:30 +0000")
        assert dt is not None
        assert dt.second == 0

    def test_parse_date_timezone_name(self, parser):
        dt = parser.parse_date("Mon, 15 Mar 2026 10:30:00 EST")
        assert dt is not None

    def test_parse_date_invalid(self, parser):
        assert parser.parse_date("not a date") is None

    def test_format_date(self, parser):
        dt = datetime(2026, 3, 15, 10, 30, 45, tzinfo=timezone.utc)
        formatted = parser.format_date(dt)
        assert "2026" in formatted
        assert "Mar" in formatted
        assert "10:30:45" in formatted

    def test_format_date_default_now(self, parser):
        formatted = parser.format_date()
        assert len(formatted) > 10

    def test_generate_message_id(self, parser):
        mid = parser.generate_message_id("example.com")
        assert mid.startswith("<")
        assert mid.endswith(">")
        assert "@example.com" in mid

    def test_generate_message_id_unique(self, parser):
        mid1 = parser.generate_message_id("example.com")
        mid2 = parser.generate_message_id("example.com")
        assert mid1 != mid2

    def test_fold_header_short(self, parser):
        result = parser.fold_header("Subject", "Short")
        assert result == "Subject: Short"

    def test_fold_header_long(self, parser):
        value = "A" * 200
        result = parser.fold_header("Subject", value, max_line=78)
        assert "Subject:" in result

    def test_unfold_header(self, parser):
        text = "This is\r\n a folded\r\n header"
        result = parser.unfold_header(text)
        assert "\n" not in result

    def test_encode_header_ascii(self, parser):
        result = parser.encode_header("Subject", "Hello World")
        assert result == "Subject: Hello World"

    def test_encode_header_unicode(self, parser):
        result = parser.encode_header("Subject", "Grüße")
        assert "=?" in result
        assert "?B?" in result

    def test_decode_encoded_word_base64(self, parser):
        encoded = "=?utf-8?B?R3LDvMOfZQ==?="
        decoded = parser.decode_encoded_word(encoded)
        assert "Grüße" == decoded

    def test_email_address_str_with_display(self):
        addr = EmailAddress(display_name="Alice", local_part="alice", domain="example.com")
        assert str(addr) == "Alice <alice@example.com>"

    def test_email_address_str_bare(self):
        addr = EmailAddress(local_part="alice", domain="example.com")
        assert str(addr) == "alice@example.com"

    def test_email_address_property(self):
        addr = EmailAddress(local_part="alice", domain="example.com")
        assert addr.address == "alice@example.com"

    def test_parse_headers_empty(self, parser):
        headers = parser.parse_headers("")
        assert headers == {}

    def test_parse_headers_colon_in_value(self, parser):
        raw = "Subject: Re: Hello: World"
        headers = parser.parse_headers(raw)
        assert headers["Subject"] == "Re: Hello: World"

    def test_parse_address_empty(self, parser):
        addr = parser.parse_address("")
        assert addr.raw == ""

    def test_parse_address_list_empty(self, parser):
        addrs = parser.parse_address_list("")
        assert len(addrs) == 0

    def test_parse_address_angle_brackets_only(self, parser):
        addr = parser.parse_address("<user@test.com>")
        assert addr.local_part == "user"
        assert addr.domain == "test.com"


# ============================================================
# TestMIMEBuilder
# ============================================================


class TestMIMEBuilder:
    """Tests for MIME construction and parsing."""

    def test_generate_boundary(self, mime_builder):
        b = mime_builder.generate_boundary()
        assert "FizzMail" in b
        assert len(b) > 10

    def test_generate_boundary_unique(self, mime_builder):
        b1 = mime_builder.generate_boundary()
        b2 = mime_builder.generate_boundary()
        assert b1 != b2

    def test_build_simple_ascii(self, mime_builder):
        part = mime_builder.build_simple("text/plain", "Hello World")
        assert part.content_type == "text/plain"
        assert part.content_transfer_encoding == "7bit"
        assert part.body == "Hello World"

    def test_build_simple_unicode(self, mime_builder):
        part = mime_builder.build_simple("text/plain", "Grüße")
        assert part.content_transfer_encoding == "quoted-printable"

    def test_build_multipart_mixed(self, mime_builder):
        p1 = MIMEPart(content_type="text/plain", body="Hello")
        p2 = MIMEPart(content_type="text/html", body="<p>Hello</p>")
        multi = mime_builder.build_multipart(MIMEMultipartType.MIXED, [p1, p2])
        assert multi.content_type == "multipart/mixed"
        assert len(multi.parts) == 2
        assert multi.boundary

    def test_build_multipart_alternative(self, mime_builder):
        p1 = MIMEPart(content_type="text/plain", body="Hello")
        p2 = MIMEPart(content_type="text/html", body="<p>Hello</p>")
        multi = mime_builder.build_multipart(MIMEMultipartType.ALTERNATIVE, [p1, p2])
        assert multi.content_type == "multipart/alternative"

    def test_build_multipart_related(self, mime_builder):
        p1 = MIMEPart(content_type="text/html", body="<img>")
        p2 = MIMEPart(content_type="image/png", body="PNG_DATA")
        multi = mime_builder.build_multipart(MIMEMultipartType.RELATED, [p1, p2])
        assert multi.content_type == "multipart/related"

    def test_build_attachment(self, mime_builder):
        part = mime_builder.build_attachment("test.pdf", b"PDF_CONTENT")
        assert part.content_type == "application/octet-stream"
        assert part.content_transfer_encoding == "base64"
        assert part.filename == "test.pdf"
        assert "attachment" in part.content_disposition

    def test_encode_base64(self, mime_builder):
        result = mime_builder.encode_base64(b"Hello World")
        decoded = base64.b64decode(result.replace("\r\n", ""))
        assert decoded == b"Hello World"

    def test_encode_base64_string(self, mime_builder):
        result = mime_builder.encode_base64("Hello")
        assert len(result) > 0

    def test_decode_base64(self, mime_builder):
        encoded = base64.b64encode(b"Test Data").decode()
        result = mime_builder.decode_base64(encoded)
        assert result == b"Test Data"

    def test_decode_base64_with_whitespace(self, mime_builder):
        encoded = "SGVs\r\nbG8=\r\n"
        result = mime_builder.decode_base64(encoded)
        assert result == b"Hello"

    def test_encode_quoted_printable_ascii(self, mime_builder):
        result = mime_builder.encode_quoted_printable("Hello World")
        assert result == "Hello World"

    def test_encode_quoted_printable_special(self, mime_builder):
        result = mime_builder.encode_quoted_printable("=test=")
        assert "=3D" in result

    def test_decode_quoted_printable(self, mime_builder):
        result = mime_builder.decode_quoted_printable("=3D")
        assert result == "="

    def test_decode_quoted_printable_soft_break(self, mime_builder):
        result = mime_builder.decode_quoted_printable("hello=\r\nworld")
        assert result == "helloworld"

    def test_build_message_text_only(self, mime_builder, config):
        msg = MailMessage(
            from_addr=EmailAddress(local_part="test", domain="example.com"),
            to_addrs=[EmailAddress(local_part="user", domain="example.com")],
            subject="Test",
            body_text="Hello World",
        )
        raw = mime_builder.build_message(msg, config)
        assert "Content-Type: text/plain" in raw
        assert "Hello World" in raw
        assert msg.raw == raw
        assert msg.size > 0

    def test_build_message_html_only(self, mime_builder, config):
        msg = MailMessage(
            from_addr=EmailAddress(local_part="test", domain="example.com"),
            to_addrs=[EmailAddress(local_part="user", domain="example.com")],
            subject="Test",
            body_html="<p>Hello</p>",
        )
        raw = mime_builder.build_message(msg, config)
        assert "Content-Type: text/html" in raw

    def test_build_message_multipart_alternative(self, mime_builder, config):
        msg = MailMessage(
            from_addr=EmailAddress(local_part="test", domain="example.com"),
            to_addrs=[EmailAddress(local_part="user", domain="example.com")],
            subject="Test",
            body_text="Hello",
            body_html="<p>Hello</p>",
        )
        raw = mime_builder.build_message(msg, config)
        assert "multipart/alternative" in raw
        assert "text/plain" in raw
        assert "text/html" in raw

    def test_build_message_generates_message_id(self, mime_builder, config):
        msg = MailMessage(
            from_addr=EmailAddress(local_part="test", domain="example.com"),
            subject="Test",
            body_text="Hello",
        )
        mime_builder.build_message(msg, config)
        assert msg.message_id.startswith("<")

    def test_build_message_generates_date(self, mime_builder, config):
        msg = MailMessage(
            from_addr=EmailAddress(local_part="test", domain="example.com"),
            subject="Test",
            body_text="Hello",
        )
        mime_builder.build_message(msg, config)
        assert msg.date is not None

    def test_parse_mime_simple(self, mime_builder):
        raw = "Content-Type: text/plain\r\n\r\nHello"
        part = mime_builder.parse_mime(raw)
        assert part.content_type == "text/plain"
        assert "Hello" in part.body

    def test_parse_mime_multipart(self, mime_builder):
        boundary = "BOUNDARY123"
        raw = (
            f'Content-Type: multipart/mixed; boundary="{boundary}"\r\n\r\n'
            f"--{boundary}\r\n"
            f"Content-Type: text/plain\r\n\r\n"
            f"Part 1\r\n"
            f"--{boundary}\r\n"
            f"Content-Type: text/html\r\n\r\n"
            f"<p>Part 2</p>\r\n"
            f"--{boundary}--"
        )
        part = mime_builder.parse_mime(raw)
        assert part.is_multipart
        assert len(part.parts) == 2

    def test_build_bodystructure_simple(self, mime_builder):
        part = MIMEPart(content_type="text/plain", charset="utf-8",
                        content_transfer_encoding="7bit", body="Hello")
        bs = mime_builder.build_bodystructure(part)
        assert '"TEXT"' in bs
        assert '"PLAIN"' in bs

    def test_build_bodystructure_multipart(self, mime_builder):
        child1 = MIMEPart(content_type="text/plain", body="Hello")
        child2 = MIMEPart(content_type="text/html", body="<p>Hi</p>")
        parent = MIMEPart(content_type="multipart/alternative", parts=[child1, child2])
        bs = mime_builder.build_bodystructure(parent)
        assert '"ALTERNATIVE"' in bs

    def test_mime_part_is_multipart(self):
        part = MIMEPart(content_type="multipart/mixed")
        assert part.is_multipart
        part2 = MIMEPart(content_type="text/plain")
        assert not part2.is_multipart

    def test_encode_base64_long_wraps(self, mime_builder):
        data = b"A" * 200
        result = mime_builder.encode_base64(data)
        lines = result.split("\r\n")
        for line in lines:
            assert len(line) <= 76


# ============================================================
# TestSMTPAuthenticator
# ============================================================


class TestSMTPAuthenticator:
    """Tests for SMTP authentication mechanisms."""

    def test_plain_valid(self, authenticator):
        encoded = base64.b64encode(b"\0postmaster\0postmaster").decode()
        success, username = authenticator.authenticate_plain(encoded)
        assert success is True
        assert username == "postmaster"

    def test_plain_invalid_password(self, authenticator):
        encoded = base64.b64encode(b"\0postmaster\0wrong").decode()
        success, _ = authenticator.authenticate_plain(encoded)
        assert success is False

    def test_plain_invalid_user(self, authenticator):
        encoded = base64.b64encode(b"\0nobody\0password").decode()
        success, _ = authenticator.authenticate_plain(encoded)
        assert success is False

    def test_plain_malformed_base64(self, authenticator):
        success, _ = authenticator.authenticate_plain("not-base64!!!")
        assert success is False

    def test_plain_wrong_format(self, authenticator):
        encoded = base64.b64encode(b"no-nulls").decode()
        success, _ = authenticator.authenticate_plain(encoded)
        assert success is False

    def test_login_valid(self, authenticator):
        user_b64 = base64.b64encode(b"admin").decode()
        pass_b64 = base64.b64encode(b"admin").decode()
        success, username = authenticator.authenticate_login(user_b64, pass_b64)
        assert success is True
        assert username == "admin"

    def test_login_invalid(self, authenticator):
        user_b64 = base64.b64encode(b"admin").decode()
        pass_b64 = base64.b64encode(b"wrong").decode()
        success, _ = authenticator.authenticate_login(user_b64, pass_b64)
        assert success is False

    def test_login_challenge(self, authenticator):
        challenge = authenticator.authenticate_login_challenge()
        decoded = base64.b64decode(challenge).decode()
        assert decoded == "Username:"

    def test_login_password_challenge(self, authenticator):
        challenge = authenticator.authenticate_login_password_challenge()
        decoded = base64.b64decode(challenge).decode()
        assert decoded == "Password:"

    def test_cram_md5_challenge_generation(self, authenticator):
        challenge_b64, challenge_id = authenticator.generate_cram_md5_challenge()
        assert len(challenge_b64) > 0
        assert len(challenge_id) > 0
        decoded = base64.b64decode(challenge_b64).decode()
        assert "@" in decoded

    def test_cram_md5_valid(self, authenticator):
        challenge_b64, challenge_id = authenticator.generate_cram_md5_challenge()
        challenge = base64.b64decode(challenge_b64).decode()
        digest = hmac.new(
            b"postmaster", challenge.encode(), hashlib.md5
        ).hexdigest()
        response = base64.b64encode(f"postmaster {digest}".encode()).decode()
        success, username = authenticator.authenticate_cram_md5(challenge_id, response)
        assert success is True
        assert username == "postmaster"

    def test_cram_md5_invalid_challenge(self, authenticator):
        response = base64.b64encode(b"user digest").decode()
        success, _ = authenticator.authenticate_cram_md5("nonexistent", response)
        assert success is False

    def test_cram_md5_wrong_digest(self, authenticator):
        _, challenge_id = authenticator.generate_cram_md5_challenge()
        response = base64.b64encode(b"postmaster wrongdigest").decode()
        success, _ = authenticator.authenticate_cram_md5(challenge_id, response)
        assert success is False

    def test_verify_all_default_users(self, authenticator):
        for user, passwd in DEFAULT_CREDENTIALS.items():
            assert authenticator._verify_credentials(user, passwd) is True

    def test_verify_wrong_password(self, authenticator):
        assert authenticator._verify_credentials("postmaster", "wrong") is False

    def test_verify_nonexistent_user(self, authenticator):
        assert authenticator._verify_credentials("nobody", "anything") is False

    def test_login_malformed_base64(self, authenticator):
        success, _ = authenticator.authenticate_login("!!!!", "!!!!")
        assert success is False


# ============================================================
# TestSMTPTLSHandler
# ============================================================


class TestSMTPTLSHandler:
    """Tests for STARTTLS handling."""

    def test_starttls_success(self, config):
        handler = SMTPTLSHandler(config)
        session = SMTPSession(state=SMTPState.GREETED)
        result = handler.handle_starttls(session)
        assert result.tls_active is True
        assert result.state == SMTPState.TLS_NEGOTIATED
        assert result.ehlo_domain == ""

    def test_starttls_already_active(self, config):
        handler = SMTPTLSHandler(config)
        session = SMTPSession(state=SMTPState.GREETED, tls_active=True)
        with pytest.raises(Exception):
            handler.handle_starttls(session)

    def test_is_tls_active(self, config):
        handler = SMTPTLSHandler(config)
        session = SMTPSession(tls_active=False)
        assert handler.is_tls_active(session) is False
        session.tls_active = True
        assert handler.is_tls_active(session) is True

    def test_starttls_resets_auth(self, config):
        handler = SMTPTLSHandler(config)
        session = SMTPSession(
            state=SMTPState.GREETED,
            authenticated_user="test",
            ehlo_domain="client.test",
        )
        handler.handle_starttls(session)
        assert session.authenticated_user == ""
        assert session.ehlo_domain == ""

    def test_starttls_resets_envelope(self, config):
        handler = SMTPTLSHandler(config)
        session = SMTPSession(
            state=SMTPState.GREETED,
            envelope=Envelope(mail_from="test@test.com"),
        )
        handler.handle_starttls(session)
        assert session.envelope is None


# ============================================================
# TestMessageQueue
# ============================================================


class TestMessageQueue:
    """Tests for the message queue."""

    def test_enqueue(self, queue):
        env = Envelope(mail_from="a@b.com", rcpt_to=["c@d.com"])
        msg = _make_message()
        msg_id = queue.enqueue(env, msg)
        assert queue.size == 1
        assert msg_id

    def test_dequeue(self, queue):
        env = Envelope(mail_from="a@b.com", rcpt_to=["c@d.com"])
        msg = _make_message()
        msg_id = queue.enqueue(env, msg)
        entry = queue.dequeue(msg_id)
        assert entry is not None
        assert queue.size == 0

    def test_dequeue_nonexistent(self, queue):
        assert queue.dequeue("nonexistent") is None

    def test_get_entry(self, queue):
        env = Envelope(mail_from="a@b.com", rcpt_to=["c@d.com"])
        msg = _make_message()
        msg_id = queue.enqueue(env, msg)
        entry = queue.get_entry(msg_id)
        assert entry is not None
        assert entry.status == QueueStatus.PENDING

    def test_mark_sent(self, queue):
        env = Envelope(mail_from="a@b.com", rcpt_to=["c@d.com"])
        msg = _make_message()
        msg_id = queue.enqueue(env, msg)
        queue.mark_sent(msg_id)
        assert queue.get_entry(msg_id).status == QueueStatus.SENT

    def test_mark_deferred(self, queue):
        env = Envelope(mail_from="a@b.com", rcpt_to=["c@d.com"])
        msg = _make_message()
        msg_id = queue.enqueue(env, msg)
        queue.mark_deferred(msg_id, "temporary failure")
        assert queue.get_entry(msg_id).status == QueueStatus.DEFERRED

    def test_mark_bounced(self, queue):
        env = Envelope(mail_from="a@b.com", rcpt_to=["c@d.com"])
        msg = _make_message()
        msg_id = queue.enqueue(env, msg)
        queue.mark_bounced(msg_id, "permanent failure")
        assert queue.get_entry(msg_id).status == QueueStatus.BOUNCED

    def test_mark_failed(self, queue):
        env = Envelope(mail_from="a@b.com", rcpt_to=["c@d.com"])
        msg = _make_message()
        msg_id = queue.enqueue(env, msg)
        queue.mark_failed(msg_id, "fatal error")
        assert queue.get_entry(msg_id).status == QueueStatus.FAILED

    def test_get_pending(self, queue):
        for i in range(3):
            queue.enqueue(Envelope(mail_from=f"a{i}@b.com"), _make_message())
        assert len(queue.get_pending()) == 3

    def test_get_queue_stats(self, queue):
        queue.enqueue(Envelope(mail_from="a@b.com"), _make_message())
        stats = queue.get_queue_stats()
        assert stats["PENDING"] == 1
        assert stats["total_enqueued"] == 1

    def test_calculate_backoff(self, queue):
        delay1 = queue._calculate_backoff(1)
        delay2 = queue._calculate_backoff(2)
        assert delay2 > delay1

    def test_backoff_capped(self, queue):
        delay = queue._calculate_backoff(100)
        assert delay <= queue._config.retry_max_delay * 1.1  # Allow jitter

    def test_schedule_retry(self, queue):
        env = Envelope(mail_from="a@b.com", rcpt_to=["c@d.com"])
        msg = _make_message()
        msg_id = queue.enqueue(env, msg)
        entry = queue.get_entry(msg_id)
        queue.schedule_retry(entry)
        assert entry.status == QueueStatus.DEFERRED
        assert entry.retry_count == 1
        assert entry.next_retry > time.time()


# ============================================================
# TestSPFValidator
# ============================================================


class TestSPFValidator:
    """Tests for SPF validation."""

    def test_spf_pass_local(self):
        validator = SPFValidator()
        result = validator.validate("10.0.0.1", "user@fizzbuzz.local")
        assert result == SPFResult.PASS

    def test_spf_pass_ip_range(self):
        validator = SPFValidator()
        result = validator.validate("10.5.5.5", "user@fizzbuzz.local")
        assert result == SPFResult.PASS

    def test_spf_softfail(self):
        validator = SPFValidator()
        result = validator.validate("1.2.3.4", "user@fizzbuzz.local")
        assert result == SPFResult.SOFTFAIL

    def test_spf_none_no_record(self):
        validator = SPFValidator()
        result = validator.validate("1.2.3.4", "user@unknown-domain-xyz.com")
        assert result == SPFResult.NONE

    def test_spf_none_no_address(self):
        validator = SPFValidator()
        result = validator.validate("1.2.3.4", "")
        assert result == SPFResult.NONE

    def test_spf_none_no_at(self):
        validator = SPFValidator()
        result = validator.validate("1.2.3.4", "local-only")
        assert result == SPFResult.NONE

    def test_parse_spf_record(self):
        validator = SPFValidator()
        record = validator._parse_spf_record("v=spf1 ip4:10.0.0.0/8 ~all")
        assert record.version == "spf1"
        assert len(record.mechanisms) == 2
        assert record.mechanisms[0].mechanism_type == "ip4"
        assert record.mechanisms[1].mechanism_type == "all"

    def test_parse_spf_redirect(self):
        validator = SPFValidator()
        record = validator._parse_spf_record("v=spf1 redirect=_spf.example.com")
        assert record.redirect == "_spf.example.com"

    def test_ip_in_network(self):
        validator = SPFValidator()
        assert validator._ip_in_network("10.0.0.1", "10.0.0.0", 8) is True
        assert validator._ip_in_network("10.255.255.255", "10.0.0.0", 8) is True
        assert validator._ip_in_network("11.0.0.1", "10.0.0.0", 8) is False

    def test_ip_in_network_32(self):
        validator = SPFValidator()
        assert validator._ip_in_network("10.0.0.1", "10.0.0.1", 32) is True
        assert validator._ip_in_network("10.0.0.2", "10.0.0.1", 32) is False

    def test_ip_in_network_24(self):
        validator = SPFValidator()
        assert validator._ip_in_network("192.168.1.100", "192.168.1.0", 24) is True
        assert validator._ip_in_network("192.168.2.1", "192.168.1.0", 24) is False

    def test_qualifier_to_result(self):
        assert SPFValidator._qualifier_to_result("+") == SPFResult.PASS
        assert SPFValidator._qualifier_to_result("-") == SPFResult.FAIL
        assert SPFValidator._qualifier_to_result("~") == SPFResult.SOFTFAIL
        assert SPFValidator._qualifier_to_result("?") == SPFResult.NEUTRAL

    def test_spf_example_com_pass(self):
        validator = SPFValidator()
        result = validator.validate("203.0.113.1", "user@example.com")
        assert result == SPFResult.PASS

    def test_spf_example_com_fail(self):
        validator = SPFValidator()
        result = validator.validate("1.2.3.4", "user@example.com")
        assert result == SPFResult.FAIL


# ============================================================
# TestDKIMSigner
# ============================================================


class TestDKIMSigner:
    """Tests for DKIM message signing."""

    def test_sign_produces_signature(self):
        signer = DKIMSigner("fizzbuzz.local", "fizzbuzz")
        msg = _make_message()
        sig = signer.sign(msg)
        assert "v=1" in sig
        assert "a=rsa-sha256" in sig
        assert "d=fizzbuzz.local" in sig
        assert "s=fizzbuzz" in sig
        assert "bh=" in sig
        assert "b=" in sig

    def test_sign_different_messages_different_signatures(self):
        signer = DKIMSigner("fizzbuzz.local", "fizzbuzz")
        msg1 = _make_message(subject="Test 1", body="Body 1")
        msg2 = _make_message(subject="Test 2", body="Body 2")
        sig1 = signer.sign(msg1)
        sig2 = signer.sign(msg2)
        assert sig1 != sig2

    def test_canonicalize_header_relaxed(self):
        signer = DKIMSigner("test.com", "sel")
        result = signer._canonicalize_header_relaxed("Subject", "  Hello   World  ")
        assert result == "subject:Hello World"

    def test_canonicalize_body_relaxed(self):
        signer = DKIMSigner("test.com", "sel")
        result = signer._canonicalize_body_relaxed("Hello  World  \n\n\n")
        assert result.endswith("\r\n")
        assert "  " not in result.split("\r\n")[0]

    def test_canonicalize_body_simple(self):
        signer = DKIMSigner("test.com", "sel")
        result = signer._canonicalize_body_simple("Hello\n\n\n")
        assert result.endswith("\r\n")
        # Should remove trailing empty lines
        assert not result.endswith("\r\n\r\n")

    def test_sign_custom_headers(self):
        signer = DKIMSigner("fizzbuzz.local", "fizzbuzz")
        msg = _make_message()
        sig = signer.sign(msg, headers_to_sign=["From", "Subject"])
        assert "h=from:subject" in sig


# ============================================================
# TestDKIMVerifier
# ============================================================


class TestDKIMVerifier:
    """Tests for DKIM signature verification."""

    def test_verify_no_signature(self):
        verifier = DKIMVerifier()
        msg = _make_message()
        result = verifier.verify(msg)
        assert result == DKIMResult.NONE

    def test_extract_dkim_signature(self):
        verifier = DKIMVerifier()
        header = "v=1; a=rsa-sha256; d=example.com; s=sel; h=from:to; bh=abc; b=xyz"
        sig = verifier._extract_dkim_signature(header)
        assert sig.domain == "example.com"
        assert sig.selector == "sel"
        assert sig.body_hash == "abc"
        assert sig.signature == "xyz"

    def test_lookup_public_key_known(self):
        verifier = DKIMVerifier()
        key = verifier._lookup_public_key("fizzbuzz.local", "fizzbuzz")
        assert key is not None
        assert "p=" in key

    def test_lookup_public_key_unknown(self):
        verifier = DKIMVerifier()
        key = verifier._lookup_public_key("unknown-domain.xyz", "unknown")
        assert key is None


# ============================================================
# TestDMARCEvaluator
# ============================================================


class TestDMARCEvaluator:
    """Tests for DMARC evaluation."""

    def test_dmarc_pass_spf_aligned(self):
        evaluator = DMARCEvaluator()
        policy, passed = evaluator.evaluate(
            "fizzbuzz.local", SPFResult.PASS, "fizzbuzz.local",
            DKIMResult.NONE, "",
        )
        assert passed is True

    def test_dmarc_pass_dkim_aligned(self):
        evaluator = DMARCEvaluator()
        policy, passed = evaluator.evaluate(
            "fizzbuzz.local", SPFResult.FAIL, "",
            DKIMResult.PASS, "fizzbuzz.local",
        )
        assert passed is True

    def test_dmarc_fail_both(self):
        evaluator = DMARCEvaluator()
        policy, passed = evaluator.evaluate(
            "fizzbuzz.local", SPFResult.FAIL, "other.com",
            DKIMResult.FAIL, "other.com",
        )
        assert passed is False
        assert policy == DMARCPolicy.QUARANTINE

    def test_dmarc_no_record(self):
        evaluator = DMARCEvaluator()
        policy, passed = evaluator.evaluate(
            "unknown-xyz.com", SPFResult.FAIL, "",
            DKIMResult.FAIL, "",
        )
        assert policy == DMARCPolicy.NONE
        assert passed is True

    def test_parse_dmarc_record(self):
        evaluator = DMARCEvaluator()
        record = evaluator._parse_dmarc_record(
            "v=DMARC1; p=reject; rua=mailto:dmarc@test.com; adkim=s; aspf=s; pct=50"
        )
        assert record.policy == DMARCPolicy.REJECT
        assert record.adkim == DMARCAlignment.STRICT
        assert record.aspf == DMARCAlignment.STRICT
        assert record.pct == 50

    def test_check_alignment_relaxed(self):
        evaluator = DMARCEvaluator()
        assert evaluator._check_alignment("sub.example.com", "example.com", DMARCAlignment.RELAXED)
        assert evaluator._check_alignment("example.com", "sub.example.com", DMARCAlignment.RELAXED)

    def test_check_alignment_strict(self):
        evaluator = DMARCEvaluator()
        assert evaluator._check_alignment("example.com", "example.com", DMARCAlignment.STRICT)
        assert not evaluator._check_alignment("sub.example.com", "example.com", DMARCAlignment.STRICT)

    def test_get_organizational_domain(self):
        evaluator = DMARCEvaluator()
        assert evaluator._get_organizational_domain("sub.example.com") == "example.com"
        assert evaluator._get_organizational_domain("example.com") == "example.com"
        assert evaluator._get_organizational_domain("a.b.example.com") == "example.com"

    def test_generate_aggregate_report(self):
        evaluator = DMARCEvaluator()
        results = [{"source_ip": "1.2.3.4", "count": 5, "disposition": "none",
                     "dkim": "pass", "spf": "pass"}]
        report = evaluator.generate_aggregate_report(results)
        assert "<?xml" in report
        assert "<feedback>" in report
        assert "1.2.3.4" in report

    def test_example_com_reject_policy(self):
        evaluator = DMARCEvaluator()
        policy, passed = evaluator.evaluate(
            "example.com", SPFResult.FAIL, "other.com",
            DKIMResult.FAIL, "other.com",
        )
        assert policy == DMARCPolicy.REJECT
        assert passed is False


# ============================================================
# TestGreylister
# ============================================================


class TestGreylister:
    """Tests for greylisting."""

    def test_first_attempt_deferred(self, config):
        gl = Greylister(config)
        allow, msg = gl.check("1.2.3.4", "sender@test.com", "rcpt@test.com")
        assert allow is False
        assert "Greylisted" in msg

    def test_retry_before_delay_deferred(self, config):
        config.greylist_delay = 300.0
        gl = Greylister(config)
        gl.check("1.2.3.4", "sender@test.com", "rcpt@test.com")
        allow, _ = gl.check("1.2.3.4", "sender@test.com", "rcpt@test.com")
        assert allow is False

    def test_retry_after_delay_accepted(self, config):
        config.greylist_delay = 0.0  # Instant accept for testing
        gl = Greylister(config)
        gl.check("1.2.3.4", "sender@test.com", "rcpt@test.com")
        allow, _ = gl.check("1.2.3.4", "sender@test.com", "rcpt@test.com")
        assert allow is True

    def test_different_triplets_independent(self, config):
        gl = Greylister(config)
        gl.check("1.2.3.4", "a@test.com", "b@test.com")
        gl.check("5.6.7.8", "c@test.com", "d@test.com")
        stats = gl.get_stats()
        assert stats["total_entries"] == 2

    def test_cleanup(self, config):
        config.greylist_ttl = 0.0
        gl = Greylister(config)
        gl.check("1.2.3.4", "a@test.com", "b@test.com")
        removed = gl.cleanup(time.time() + 1)
        assert removed == 1
        assert gl.get_stats()["total_entries"] == 0

    def test_auto_whitelist(self, config):
        config.greylist_delay = 0.0
        config.greylist_whitelist_threshold = 2
        gl = Greylister(config)
        gl.check("1.2.3.4", "a@t.com", "b@t.com")
        gl.check("1.2.3.4", "a@t.com", "b@t.com")
        gl.check("1.2.3.4", "a@t.com", "b@t.com")
        stats = gl.get_stats()
        assert stats["whitelisted"] == 1

    def test_stats(self, config):
        gl = Greylister(config)
        gl.check("1.2.3.4", "a@t.com", "b@t.com")
        stats = gl.get_stats()
        assert stats["deferred"] == 1
        assert stats["total_entries"] == 1


# ============================================================
# TestRBLChecker
# ============================================================


class TestRBLChecker:
    """Tests for RBL/DNSBL checking."""

    def test_clean_ip(self):
        checker = RBLChecker(["zen.spamhaus.org"])
        listed, zones = checker.check("10.0.0.1")
        assert listed is False

    def test_blocked_ip(self):
        checker = RBLChecker(["zen.spamhaus.org"])
        listed, zones = checker.check("192.0.2.1")
        assert listed is True
        assert len(zones) > 0

    def test_reverse_ip(self):
        checker = RBLChecker([])
        assert checker._reverse_ip("1.2.3.4") == "4.3.2.1"
        assert checker._reverse_ip("10.0.0.1") == "1.0.0.10"

    def test_multiple_zones(self):
        checker = RBLChecker(["zone1.example.com", "zone2.example.com"])
        listed, zones = checker.check("192.0.2.1")
        assert listed is True


# ============================================================
# TestBounceHandler
# ============================================================


class TestBounceHandler:
    """Tests for DSN bounce generation."""

    def test_generate_dsn(self, config):
        handler = BounceHandler(config)
        env = Envelope(mail_from="sender@test.com", rcpt_to=["rcpt@test.com"])
        recipients = [DSNRecipient(
            final_recipient="rcpt@test.com",
            action="failed",
            status_code="5.1.1",
            diagnostic_code="Mailbox does not exist",
        )]
        dsn = handler.generate_dsn(env, recipients, "From: sender@test.com")
        assert dsn.from_addr.local_part == "MAILER-DAEMON"
        assert "Undelivered" in dsn.subject
        assert "failed" in dsn.body_text

    def test_dsn_has_status_header(self, config):
        handler = BounceHandler(config)
        env = Envelope(mail_from="sender@test.com")
        recipients = [DSNRecipient(final_recipient="rcpt@test.com", status_code="5.0.0")]
        dsn = handler.generate_dsn(env, recipients)
        assert "X-DSN-Status" in dsn.headers

    def test_dsn_multiple_recipients(self, config):
        handler = BounceHandler(config)
        env = Envelope(mail_from="sender@test.com")
        recipients = [
            DSNRecipient(final_recipient="a@test.com", action="failed", status_code="5.1.1"),
            DSNRecipient(final_recipient="b@test.com", action="delayed", status_code="4.2.2"),
        ]
        dsn = handler.generate_dsn(env, recipients)
        assert "a@test.com" in dsn.body_text
        assert "b@test.com" in dsn.body_text


# ============================================================
# TestMaildirStorage
# ============================================================


class TestMaildirStorage:
    """Tests for Maildir storage backend."""

    def test_create_user(self, storage):
        storage.create_user("new@fizzbuzz.local")
        mailboxes = storage.list_mailboxes("new@fizzbuzz.local")
        assert len(mailboxes) == len(DEFAULT_MAILBOXES)

    def test_create_mailbox(self, storage):
        user = "postmaster@fizzbuzz.local"
        mb = storage.create_mailbox(user, "CustomFolder")
        assert mb.name == "CustomFolder"
        assert mb.uidnext == 1

    def test_create_mailbox_duplicate(self, storage):
        user = "postmaster@fizzbuzz.local"
        with pytest.raises(Exception):
            storage.create_mailbox(user, "INBOX")

    def test_delete_mailbox(self, storage):
        user = "postmaster@fizzbuzz.local"
        storage.create_mailbox(user, "Temp")
        storage.delete_mailbox(user, "Temp")
        with pytest.raises(Exception):
            storage.get_mailbox(user, "Temp")

    def test_delete_inbox_fails(self, storage):
        with pytest.raises(Exception):
            storage.delete_mailbox("postmaster@fizzbuzz.local", "INBOX")

    def test_rename_mailbox(self, storage):
        user = "postmaster@fizzbuzz.local"
        storage.create_mailbox(user, "OldName")
        storage.rename_mailbox(user, "OldName", "NewName")
        mb = storage.get_mailbox(user, "NewName")
        assert mb.name == "NewName"

    def test_rename_inbox_fails(self, storage):
        with pytest.raises(Exception):
            storage.rename_mailbox("postmaster@fizzbuzz.local", "INBOX", "NotInbox")

    def test_get_mailbox(self, storage):
        mb = storage.get_mailbox("postmaster@fizzbuzz.local", "INBOX")
        assert mb.name == "INBOX"

    def test_get_mailbox_not_found(self, storage):
        with pytest.raises(Exception):
            storage.get_mailbox("postmaster@fizzbuzz.local", "Nonexistent")

    def test_list_mailboxes(self, storage):
        mailboxes = storage.list_mailboxes("postmaster@fizzbuzz.local")
        names = [mb.name for mb in mailboxes]
        assert "INBOX" in names
        assert "Sent" in names

    def test_deliver(self, storage):
        msg = _make_message()
        uid = storage.deliver("postmaster@fizzbuzz.local", "INBOX", msg)
        assert uid == 1
        mb = storage.get_mailbox("postmaster@fizzbuzz.local", "INBOX")
        assert mb.exists == 1

    def test_deliver_multiple(self, storage):
        for i in range(5):
            storage.deliver("postmaster@fizzbuzz.local", "INBOX", _make_message(subject=f"Msg {i}"))
        mb = storage.get_mailbox("postmaster@fizzbuzz.local", "INBOX")
        assert mb.exists == 5

    def test_deliver_auto_creates_user(self, config):
        s = MaildirStorage(config)
        msg = _make_message()
        s.deliver("new@fizzbuzz.local", "INBOX", msg)
        mb = s.get_mailbox("new@fizzbuzz.local", "INBOX")
        assert mb.exists == 1

    def test_fetch_message(self, storage):
        msg = _make_message(subject="Findme")
        uid = storage.deliver("postmaster@fizzbuzz.local", "INBOX", msg)
        fetched = storage.fetch_message("postmaster@fizzbuzz.local", "INBOX", uid)
        assert fetched is not None
        assert fetched.subject == "Findme"

    def test_fetch_message_not_found(self, storage):
        result = storage.fetch_message("postmaster@fizzbuzz.local", "INBOX", 999)
        assert result is None

    def test_update_flags_add(self, storage):
        msg = _make_message()
        uid = storage.deliver("postmaster@fizzbuzz.local", "INBOX", msg)
        flags = storage.update_flags("postmaster@fizzbuzz.local", "INBOX", uid,
                                     {r"\Seen"}, IMAPFlagAction.ADD)
        assert r"\Seen" in flags

    def test_update_flags_remove(self, storage):
        msg = _make_message()
        uid = storage.deliver("postmaster@fizzbuzz.local", "INBOX", msg)
        storage.update_flags("postmaster@fizzbuzz.local", "INBOX", uid,
                             {r"\Seen"}, IMAPFlagAction.ADD)
        flags = storage.update_flags("postmaster@fizzbuzz.local", "INBOX", uid,
                                     {r"\Seen"}, IMAPFlagAction.REMOVE)
        assert r"\Seen" not in flags

    def test_update_flags_set(self, storage):
        msg = _make_message()
        uid = storage.deliver("postmaster@fizzbuzz.local", "INBOX", msg)
        flags = storage.update_flags("postmaster@fizzbuzz.local", "INBOX", uid,
                                     {r"\Flagged", r"\Seen"}, IMAPFlagAction.SET)
        assert flags == {r"\Flagged", r"\Seen"}

    def test_expunge(self, storage):
        user = "postmaster@fizzbuzz.local"
        uid1 = storage.deliver(user, "INBOX", _make_message())
        uid2 = storage.deliver(user, "INBOX", _make_message())
        storage.update_flags(user, "INBOX", uid1, {r"\Deleted"}, IMAPFlagAction.ADD)
        expunged = storage.expunge(user, "INBOX")
        assert len(expunged) == 1
        mb = storage.get_mailbox(user, "INBOX")
        assert mb.exists == 1

    def test_get_quota_usage(self, storage):
        msg = _make_message(body="A" * 1000)
        storage.deliver("postmaster@fizzbuzz.local", "INBOX", msg)
        usage = storage.get_quota_usage("postmaster@fizzbuzz.local")
        assert usage > 0

    def test_set_and_get_quota(self, storage):
        storage.set_quota("postmaster@fizzbuzz.local", 50000)
        assert storage.get_quota("postmaster@fizzbuzz.local") == 50000

    def test_get_all_users(self, storage):
        users = storage.get_all_users()
        assert "postmaster@fizzbuzz.local" in users


# ============================================================
# TestQuotaEnforcer
# ============================================================


class TestQuotaEnforcer:
    """Tests for quota enforcement."""

    def test_within_quota(self, config, storage):
        enforcer = QuotaEnforcer(config, storage)
        allowed, usage, quota = enforcer.check_quota("postmaster@fizzbuzz.local", 100)
        assert allowed is True

    def test_exceeds_quota(self, config, storage):
        storage.set_quota("postmaster@fizzbuzz.local", 10)
        enforcer = QuotaEnforcer(config, storage)
        allowed, usage, quota = enforcer.check_quota("postmaster@fizzbuzz.local", 100)
        assert allowed is False

    def test_get_usage(self, config, storage):
        enforcer = QuotaEnforcer(config, storage)
        assert enforcer.get_usage("postmaster@fizzbuzz.local") == 0

    def test_set_quota(self, config, storage):
        enforcer = QuotaEnforcer(config, storage)
        enforcer.set_quota("postmaster@fizzbuzz.local", 999)
        assert enforcer.get_quota("postmaster@fizzbuzz.local") == 999


# ============================================================
# TestIMAPSearchEngine
# ============================================================


class TestIMAPSearchEngine:
    """Tests for IMAP SEARCH criteria evaluation."""

    def _make_mailbox_with_messages(self):
        config = FizzMailConfig()
        storage = MaildirStorage(config)
        user = "test@fizzbuzz.local"
        storage.create_user(user)
        now = datetime.now(timezone.utc)

        msgs = [
            _make_message(from_addr="alice@test.com", subject="Meeting notes", body="Let's meet"),
            _make_message(from_addr="bob@test.com", subject="FizzBuzz report", body="15 is FizzBuzz"),
            _make_message(from_addr="charlie@test.com", subject="Urgent update", body="Critical issue"),
        ]
        for msg in msgs:
            storage.deliver(user, "INBOX", msg)

        # Mark first as seen
        storage.update_flags(user, "INBOX", 1, {r"\Seen"}, IMAPFlagAction.ADD)
        # Flag second
        storage.update_flags(user, "INBOX", 2, {r"\Flagged"}, IMAPFlagAction.ADD)

        return storage.get_mailbox(user, "INBOX")

    def test_search_all(self):
        mb = self._make_mailbox_with_messages()
        engine = IMAPSearchEngine()
        results = engine.search(mb, "ALL")
        assert len(results) == 3

    def test_search_from(self):
        mb = self._make_mailbox_with_messages()
        engine = IMAPSearchEngine()
        results = engine.search(mb, 'FROM "alice"')
        assert len(results) == 1

    def test_search_to(self):
        mb = self._make_mailbox_with_messages()
        engine = IMAPSearchEngine()
        results = engine.search(mb, 'TO "fizzbuzz.local"')
        assert len(results) == 3

    def test_search_subject(self):
        mb = self._make_mailbox_with_messages()
        engine = IMAPSearchEngine()
        results = engine.search(mb, 'SUBJECT "FizzBuzz"')
        assert len(results) == 1

    def test_search_body(self):
        mb = self._make_mailbox_with_messages()
        engine = IMAPSearchEngine()
        results = engine.search(mb, 'BODY "Critical"')
        assert len(results) == 1

    def test_search_seen(self):
        mb = self._make_mailbox_with_messages()
        engine = IMAPSearchEngine()
        results = engine.search(mb, "SEEN")
        assert len(results) == 1

    def test_search_unseen(self):
        mb = self._make_mailbox_with_messages()
        engine = IMAPSearchEngine()
        results = engine.search(mb, "UNSEEN")
        assert len(results) == 2

    def test_search_flagged(self):
        mb = self._make_mailbox_with_messages()
        engine = IMAPSearchEngine()
        results = engine.search(mb, "FLAGGED")
        assert len(results) == 1

    def test_search_unflagged(self):
        mb = self._make_mailbox_with_messages()
        engine = IMAPSearchEngine()
        results = engine.search(mb, "UNFLAGGED")
        assert len(results) == 2

    def test_search_not(self):
        mb = self._make_mailbox_with_messages()
        engine = IMAPSearchEngine()
        results = engine.search(mb, "NOT SEEN")
        assert len(results) == 2

    def test_search_or(self):
        mb = self._make_mailbox_with_messages()
        engine = IMAPSearchEngine()
        results = engine.search(mb, 'OR FROM "alice" FROM "bob"')
        assert len(results) == 2

    def test_search_larger(self):
        mb = self._make_mailbox_with_messages()
        engine = IMAPSearchEngine()
        results = engine.search(mb, "LARGER 1")
        assert len(results) == 3

    def test_search_smaller(self):
        mb = self._make_mailbox_with_messages()
        engine = IMAPSearchEngine()
        results = engine.search(mb, "SMALLER 1")
        assert len(results) == 0

    def test_search_uid(self):
        mb = self._make_mailbox_with_messages()
        engine = IMAPSearchEngine()
        results = engine.search(mb, "ALL", use_uid=True)
        assert 1 in results
        assert 2 in results
        assert 3 in results


# ============================================================
# TestSMTPServer
# ============================================================


class TestSMTPServer:
    """Tests for SMTP protocol processing."""

    def test_greeting(self, subsystem):
        smtp, imap, dashboard, mw = subsystem
        responses = smtp.handle_connection("10.0.0.1", [])
        assert responses[0].code == 220
        assert "ESMTP" in responses[0].message

    def test_ehlo(self, subsystem):
        smtp, _, _, _ = subsystem
        responses = smtp.handle_connection("10.0.0.1", ["EHLO client.test"])
        assert responses[1].code == 250
        assert "SIZE" in responses[1].message

    def test_helo(self, subsystem):
        smtp, _, _, _ = subsystem
        responses = smtp.handle_connection("10.0.0.1", ["HELO client.test"])
        assert responses[1].code == 250

    def test_ehlo_without_domain(self, subsystem):
        smtp, _, _, _ = subsystem
        responses = smtp.handle_connection("10.0.0.1", ["EHLO"])
        assert responses[1].code == 501

    def test_auth_plain(self, subsystem):
        smtp, _, _, _ = subsystem
        creds = base64.b64encode(b"\0postmaster\0postmaster").decode()
        responses = smtp.handle_connection("10.0.0.1", [
            "EHLO client.test",
            f"AUTH PLAIN {creds}",
        ])
        assert responses[2].code == 235

    def test_auth_plain_invalid(self, subsystem):
        smtp, _, _, _ = subsystem
        creds = base64.b64encode(b"\0postmaster\0wrong").decode()
        responses = smtp.handle_connection("10.0.0.1", [
            "EHLO client.test",
            f"AUTH PLAIN {creds}",
        ])
        assert responses[2].code == 535

    def test_mail_from(self, subsystem):
        smtp, _, _, _ = subsystem
        responses = smtp.handle_connection("10.0.0.1", [
            "EHLO client.test",
            "MAIL FROM:<test@fizzbuzz.local>",
        ])
        assert responses[2].code == 250

    def test_mail_from_bad_syntax(self, subsystem):
        smtp, _, _, _ = subsystem
        responses = smtp.handle_connection("10.0.0.1", [
            "EHLO client.test",
            "MAIL test@fizzbuzz.local",
        ])
        assert responses[2].code == 501

    def test_rcpt_to(self, subsystem):
        smtp, _, _, _ = subsystem
        responses = smtp.handle_connection("10.0.0.1", [
            "EHLO client.test",
            "MAIL FROM:<test@fizzbuzz.local>",
            "RCPT TO:<user@fizzbuzz.local>",
        ])
        assert responses[3].code == 250

    def test_rcpt_to_before_mail(self, subsystem):
        smtp, _, _, _ = subsystem
        responses = smtp.handle_connection("10.0.0.1", [
            "EHLO client.test",
            "RCPT TO:<user@fizzbuzz.local>",
        ])
        assert responses[2].code == 503

    def test_data_delivery(self, subsystem):
        smtp, _, _, _ = subsystem
        responses = smtp.handle_connection("10.0.0.1", [
            "EHLO client.test",
            "MAIL FROM:<test@fizzbuzz.local>",
            "RCPT TO:<postmaster@fizzbuzz.local>",
            "DATA Subject: Test\r\nFrom: test@fizzbuzz.local\r\n\r\nHello\r\n.",
        ])
        assert responses[4].code == 250
        assert "accepted" in responses[4].message

    def test_quit(self, subsystem):
        smtp, _, _, _ = subsystem
        responses = smtp.handle_connection("10.0.0.1", [
            "EHLO client.test",
            "QUIT",
        ])
        assert responses[2].code == 221

    def test_rset(self, subsystem):
        smtp, _, _, _ = subsystem
        responses = smtp.handle_connection("10.0.0.1", [
            "EHLO client.test",
            "MAIL FROM:<test@fizzbuzz.local>",
            "RSET",
        ])
        assert responses[3].code == 250

    def test_noop(self, subsystem):
        smtp, _, _, _ = subsystem
        responses = smtp.handle_connection("10.0.0.1", [
            "EHLO client.test",
            "NOOP",
        ])
        assert responses[2].code == 250

    def test_vrfy(self, subsystem):
        smtp, _, _, _ = subsystem
        responses = smtp.handle_connection("10.0.0.1", [
            "EHLO client.test",
            "VRFY postmaster",
        ])
        assert responses[2].code == 252

    def test_unknown_command(self, subsystem):
        smtp, _, _, _ = subsystem
        responses = smtp.handle_connection("10.0.0.1", [
            "EHLO client.test",
            "BLAHBLAH",
        ])
        assert responses[2].code == 500

    def test_empty_command(self, subsystem):
        smtp, _, _, _ = subsystem
        responses = smtp.handle_connection("10.0.0.1", ["EHLO client.test", ""])
        assert responses[2].code == 500

    def test_starttls(self, subsystem):
        smtp, _, _, _ = subsystem
        responses = smtp.handle_connection("10.0.0.1", [
            "EHLO client.test",
            "STARTTLS",
        ])
        assert responses[2].code == 220

    def test_full_smtp_session(self, subsystem):
        smtp, _, _, _ = subsystem
        creds = base64.b64encode(b"\0admin\0admin").decode()
        responses = smtp.handle_connection("10.0.0.1", [
            "EHLO client.test",
            "STARTTLS",
            "EHLO client.test",
            f"AUTH PLAIN {creds}",
            "MAIL FROM:<admin@fizzbuzz.local>",
            "RCPT TO:<postmaster@fizzbuzz.local>",
            "DATA Subject: Full Test\r\nFrom: admin@fizzbuzz.local\r\nTo: postmaster@fizzbuzz.local\r\n\r\nFull session test\r\n.",
            "QUIT",
        ])
        # 220 greeting, 250 EHLO, 220 STARTTLS, 250 EHLO, 235 AUTH, 250 MAIL, 250 RCPT, 250 DATA, 221 QUIT
        assert responses[0].code == 220   # greeting
        assert responses[4].code == 235   # auth success
        assert responses[7].code == 250   # data accepted

    def test_data_remote_queued(self, subsystem):
        smtp, _, _, _ = subsystem
        responses = smtp.handle_connection("10.0.0.1", [
            "EHLO client.test",
            "MAIL FROM:<test@fizzbuzz.local>",
            "RCPT TO:<user@example.com>",
            "DATA Subject: Remote\r\nFrom: test@fizzbuzz.local\r\n\r\nRemote delivery\r\n.",
        ])
        assert responses[4].code == 250

    def test_metrics_incremented(self, subsystem):
        smtp, _, _, _ = subsystem
        smtp.handle_connection("10.0.0.1", [
            "EHLO client.test",
            "MAIL FROM:<test@fizzbuzz.local>",
            "RCPT TO:<postmaster@fizzbuzz.local>",
            "DATA Subject: Test\r\n\r\nBody\r\n.",
        ])
        metrics = smtp.get_metrics()
        assert metrics.messages_received >= 1

    def test_uptime(self, subsystem):
        smtp, _, _, _ = subsystem
        assert smtp.uptime > 0
        assert smtp.is_running


# ============================================================
# TestIMAPServer
# ============================================================


class TestIMAPServer:
    """Tests for IMAP protocol processing."""

    def test_greeting(self, subsystem):
        _, imap, _, _ = subsystem
        responses = imap.handle_connection("client1", [])
        assert "OK" in responses[0]

    def test_login(self, subsystem):
        _, imap, _, _ = subsystem
        responses = imap.handle_connection("client1", [
            "A001 LOGIN postmaster postmaster",
        ])
        assert "OK" in responses[1]

    def test_login_invalid(self, subsystem):
        _, imap, _, _ = subsystem
        responses = imap.handle_connection("client1", [
            "A001 LOGIN postmaster wrong",
        ])
        assert "NO" in responses[1]

    def test_capability(self, subsystem):
        _, imap, _, _ = subsystem
        responses = imap.handle_connection("client1", [
            "A001 CAPABILITY",
        ])
        assert "IMAP4rev1" in responses[1]

    def test_select_inbox(self, subsystem):
        _, imap, _, _ = subsystem
        responses = imap.handle_connection("client1", [
            "A001 LOGIN postmaster postmaster",
            "A002 SELECT INBOX",
        ])
        found_exists = any("EXISTS" in r for r in responses)
        found_flags = any("FLAGS" in r for r in responses)
        assert found_exists
        assert found_flags

    def test_examine(self, subsystem):
        _, imap, _, _ = subsystem
        responses = imap.handle_connection("client1", [
            "A001 LOGIN postmaster postmaster",
            "A002 EXAMINE INBOX",
        ])
        found_readonly = any("READ-ONLY" in r for r in responses)
        assert found_readonly

    def test_list(self, subsystem):
        _, imap, _, _ = subsystem
        responses = imap.handle_connection("client1", [
            "A001 LOGIN postmaster postmaster",
            'A002 LIST "" "*"',
        ])
        found_inbox = any("INBOX" in r for r in responses)
        assert found_inbox

    def test_lsub(self, subsystem):
        _, imap, _, _ = subsystem
        responses = imap.handle_connection("client1", [
            "A001 LOGIN postmaster postmaster",
            'A002 LSUB "" "*"',
        ])
        found_inbox = any("INBOX" in r for r in responses)
        assert found_inbox

    def test_create_delete(self, subsystem):
        _, imap, _, _ = subsystem
        responses = imap.handle_connection("client1", [
            "A001 LOGIN postmaster postmaster",
            'A002 CREATE "TestFolder"',
            'A003 DELETE "TestFolder"',
        ])
        assert "OK" in responses[2]  # create
        assert "OK" in responses[3]  # delete

    def test_status(self, subsystem):
        _, imap, _, _ = subsystem
        responses = imap.handle_connection("client1", [
            "A001 LOGIN postmaster postmaster",
            'A002 STATUS "INBOX" (MESSAGES RECENT UNSEEN)',
        ])
        found_status = any("STATUS" in r and "MESSAGES" in r for r in responses)
        assert found_status

    def test_fetch_flags(self, subsystem):
        _, imap, _, _ = subsystem
        responses = imap.handle_connection("client1", [
            "A001 LOGIN postmaster postmaster",
            "A002 SELECT INBOX",
            "A003 FETCH 1 (FLAGS UID)",
        ])
        found_fetch = any("FETCH" in r and "FLAGS" in r for r in responses)
        assert found_fetch

    def test_fetch_envelope(self, subsystem):
        _, imap, _, _ = subsystem
        responses = imap.handle_connection("client1", [
            "A001 LOGIN postmaster postmaster",
            "A002 SELECT INBOX",
            "A003 FETCH 1 (ENVELOPE)",
        ])
        found_envelope = any("ENVELOPE" in r for r in responses)
        assert found_envelope

    def test_store_flags(self, subsystem):
        _, imap, _, _ = subsystem
        responses = imap.handle_connection("client1", [
            "A001 LOGIN postmaster postmaster",
            "A002 SELECT INBOX",
            r'A003 STORE 1 +FLAGS (\Seen)',
        ])
        found_fetch = any("FETCH" in r and r"\Seen" in r for r in responses)
        assert found_fetch

    def test_search(self, subsystem):
        _, imap, _, _ = subsystem
        responses = imap.handle_connection("client1", [
            "A001 LOGIN postmaster postmaster",
            "A002 SELECT INBOX",
            "A003 SEARCH ALL",
        ])
        found_search = any("SEARCH" in r for r in responses)
        assert found_search

    def test_copy(self, subsystem):
        _, imap, _, _ = subsystem
        responses = imap.handle_connection("client1", [
            "A001 LOGIN postmaster postmaster",
            "A002 SELECT INBOX",
            'A003 COPY 1 "Sent"',
        ])
        assert any("OK" in r and "COPY" in r for r in responses)

    def test_expunge(self, subsystem):
        _, imap, _, _ = subsystem
        responses = imap.handle_connection("client1", [
            "A001 LOGIN postmaster postmaster",
            "A002 SELECT INBOX",
            r"A003 STORE 1 +FLAGS (\Deleted)",
            "A004 EXPUNGE",
        ])
        assert any("OK" in r and "EXPUNGE" in r for r in responses)

    def test_idle(self, subsystem):
        _, imap, _, _ = subsystem
        responses = imap.handle_connection("client1", [
            "A001 LOGIN postmaster postmaster",
            "A002 SELECT INBOX",
            "A003 IDLE",
        ])
        found_idle = any("idling" in r for r in responses)
        assert found_idle

    def test_namespace(self, subsystem):
        _, imap, _, _ = subsystem
        responses = imap.handle_connection("client1", [
            "A001 LOGIN postmaster postmaster",
            "A002 NAMESPACE",
        ])
        found_ns = any("NAMESPACE" in r and '""' in r for r in responses)
        assert found_ns

    def test_close(self, subsystem):
        _, imap, _, _ = subsystem
        responses = imap.handle_connection("client1", [
            "A001 LOGIN postmaster postmaster",
            "A002 SELECT INBOX",
            "A003 CLOSE",
        ])
        assert any("OK" in r and "CLOSE" in r for r in responses)

    def test_logout(self, subsystem):
        _, imap, _, _ = subsystem
        responses = imap.handle_connection("client1", [
            "A001 LOGIN postmaster postmaster",
            "A002 LOGOUT",
        ])
        found_bye = any("BYE" in r for r in responses)
        assert found_bye

    def test_noop(self, subsystem):
        _, imap, _, _ = subsystem
        responses = imap.handle_connection("client1", [
            "A001 LOGIN postmaster postmaster",
            "A002 NOOP",
        ])
        assert any("OK" in r and "NOOP" in r for r in responses)

    def test_uid_fetch(self, subsystem):
        _, imap, _, _ = subsystem
        responses = imap.handle_connection("client1", [
            "A001 LOGIN postmaster postmaster",
            "A002 SELECT INBOX",
            "A003 UID FETCH 1 (FLAGS)",
        ])
        found = any("FETCH" in r and "UID" in r for r in responses)
        assert found

    def test_uid_search(self, subsystem):
        _, imap, _, _ = subsystem
        responses = imap.handle_connection("client1", [
            "A001 LOGIN postmaster postmaster",
            "A002 SELECT INBOX",
            "A003 UID SEARCH ALL",
        ])
        found = any("SEARCH" in r for r in responses)
        assert found

    def test_select_not_authenticated(self, subsystem):
        _, imap, _, _ = subsystem
        responses = imap.handle_connection("client1", [
            "A001 SELECT INBOX",
        ])
        assert any("NO" in r for r in responses)

    def test_unknown_command(self, subsystem):
        _, imap, _, _ = subsystem
        responses = imap.handle_connection("client1", [
            "A001 LOGIN postmaster postmaster",
            "A002 FOOBAR",
        ])
        assert any("BAD" in r for r in responses)

    def test_rename(self, subsystem):
        _, imap, _, _ = subsystem
        responses = imap.handle_connection("client1", [
            "A001 LOGIN postmaster postmaster",
            'A002 CREATE "TempBox"',
            'A003 RENAME "TempBox" "RenamedBox"',
        ])
        assert any("OK" in r and "RENAME" in r for r in responses)

    def test_subscribe_unsubscribe(self, subsystem):
        _, imap, _, _ = subsystem
        responses = imap.handle_connection("client1", [
            "A001 LOGIN postmaster postmaster",
            'A002 UNSUBSCRIBE "Junk"',
            'A003 SUBSCRIBE "Junk"',
        ])
        assert any("OK" in r and "UNSUBSCRIBE" in r for r in responses)
        assert any("OK" in r and "SUBSCRIBE" in r for r in responses)


# ============================================================
# TestFizzMailMiddleware
# ============================================================


class TestFizzMailMiddleware:
    """Tests for middleware integration."""

    def test_get_name(self, subsystem):
        _, _, _, mw = subsystem
        assert mw.get_name() == "fizzmail"

    def test_get_priority(self, subsystem):
        _, _, _, mw = subsystem
        assert mw.get_priority() == MIDDLEWARE_PRIORITY

    def test_process(self, subsystem):
        _, _, _, mw = subsystem
        ctx = MagicMock()
        ctx.metadata = {}
        result = mw.process(ctx, None)
        assert "fizzmail_version" in ctx.metadata
        assert ctx.metadata["fizzmail_version"] == FIZZMAIL_VERSION

    def test_process_delegates(self, subsystem):
        _, _, _, mw = subsystem
        ctx = MagicMock()
        ctx.metadata = {}
        next_handler = MagicMock(return_value=ctx)
        mw.process(ctx, next_handler)
        next_handler.assert_called_once_with(ctx)

    def test_render_status(self, subsystem):
        _, _, _, mw = subsystem
        status = mw.render_status()
        assert "FizzMail" in status
        assert "SMTP" in status
        assert "IMAP" in status

    def test_render_dashboard(self, subsystem):
        _, _, _, mw = subsystem
        dashboard = mw.render_dashboard()
        assert "FizzMail" in dashboard
        assert "SMTP" in dashboard
        assert "Queue" in dashboard

    def test_render_mailboxes(self, subsystem):
        _, _, _, mw = subsystem
        result = mw.render_mailboxes()
        assert "INBOX" in result
        assert "postmaster" in result

    def test_render_send_result(self, subsystem):
        _, _, _, mw = subsystem
        result = mw.render_send_result("test@fizzbuzz.local,user@fizzbuzz.local,Test,Hello World")
        assert "From:" in result
        assert "To:" in result
        assert "Message-ID:" in result

    def test_render_send_result_invalid(self, subsystem):
        _, _, _, mw = subsystem
        result = mw.render_send_result("invalid")
        assert "Error" in result

    def test_render_search_result(self, subsystem):
        _, _, _, mw = subsystem
        result = mw.render_search_result("Welcome")
        assert "Welcome" in result
        assert "Total matches" in result

    def test_render_idle_simulation(self, subsystem):
        _, _, _, mw = subsystem
        result = mw.render_idle_simulation()
        assert "idling" in result
        assert "DONE" in result


# ============================================================
# TestCreateSubsystem
# ============================================================


class TestCreateSubsystem:
    """Tests for the factory function."""

    def test_returns_tuple(self):
        result = create_fizzmail_subsystem()
        assert len(result) == 4
        smtp, imap, dashboard, mw = result
        assert isinstance(smtp, SMTPServer)
        assert isinstance(imap, IMAPServer)
        assert isinstance(dashboard, FizzMailDashboard)
        assert isinstance(mw, FizzMailMiddleware)

    def test_servers_started(self):
        smtp, imap, _, _ = create_fizzmail_subsystem()
        assert smtp.is_running
        assert imap._started

    def test_default_users_created(self):
        smtp, imap, _, mw = create_fizzmail_subsystem()
        mailboxes_output = mw.render_mailboxes()
        assert "postmaster" in mailboxes_output
        assert "admin" in mailboxes_output
        assert "fizzbuzz" in mailboxes_output

    def test_welcome_messages_delivered(self):
        _, imap, _, _ = create_fizzmail_subsystem()
        responses = imap.handle_connection("test", [
            "A001 LOGIN postmaster postmaster",
            "A002 SELECT INBOX",
        ])
        found_exists = False
        for r in responses:
            if "EXISTS" in r:
                # Should have at least 1 message (welcome)
                count = int(r.split()[1])
                assert count >= 1
                found_exists = True
        assert found_exists

    def test_custom_config(self):
        smtp, _, _, _ = create_fizzmail_subsystem(
            smtp_port=3025,
            domain="custom.local",
            enable_tls=False,
        )
        assert smtp._config.smtp_port == 3025
        assert smtp._config.domain == "custom.local"

    def test_all_default_mailboxes_exist(self):
        _, imap, _, _ = create_fizzmail_subsystem()
        responses = imap.handle_connection("test", [
            "A001 LOGIN postmaster postmaster",
            'A002 LIST "" "*"',
        ])
        for name in DEFAULT_MAILBOXES:
            found = any(name in r for r in responses)
            assert found, f"Mailbox {name} not found"

    def test_email_to_user(self):
        """Simulate sending an email to elijukanovich@gmail.com."""
        smtp, _, _, mw = create_fizzmail_subsystem()
        result = mw.render_send_result(
            "fizzbuzz@fizzbuzz.local,"
            "elijukanovich@gmail.com,"
            "Enterprise FizzBuzz Evaluation Report,"
            "Your FizzBuzz evaluation for integers 1-100 is complete. "
            "Results: 27 Fizz 14 Buzz 6 FizzBuzz 53 plain. "
            "All 137 infrastructure modules operational."
        )
        assert "elijukanovich@gmail.com" in result
        assert "DELIVERED" in result or "QUEUED" in result


# ============================================================
# TestRelayRouter
# ============================================================


class TestRelayRouter:
    """Tests for relay routing."""

    def test_local_delivery(self, config):
        storage = MaildirStorage(config)
        storage.create_user(f"user@{config.domain}")
        router = RelayRouter(config, storage)
        env = Envelope(mail_from="sender@fizzbuzz.local", rcpt_to=[f"user@{config.domain}"])
        msg = _make_message()
        router.deliver(env, msg)
        mb = storage.get_mailbox(f"user@{config.domain}", "INBOX")
        assert mb.exists == 1

    def test_remote_delivery(self, config):
        storage = MaildirStorage(config)
        router = RelayRouter(config, storage)
        env = Envelope(mail_from="sender@fizzbuzz.local", rcpt_to=["user@example.com"])
        msg = _make_message()
        router.deliver(env, msg)
        assert len(router.delivery_log) == 1
        assert router.delivery_log[0]["method"] == "relay"

    def test_lookup_mx(self, config):
        storage = MaildirStorage(config)
        router = RelayRouter(config, storage)
        records = router._lookup_mx("fizzbuzz.local")
        assert len(records) > 0
        assert records[0][1] == "mail.fizzbuzz.local"

    def test_lookup_mx_unknown(self, config):
        storage = MaildirStorage(config)
        router = RelayRouter(config, storage)
        records = router._lookup_mx("unknown-xyz-123.com")
        assert len(records) > 0  # Falls back to mail.domain

    def test_smart_host(self, config):
        config.smart_host = "relay.example.com"
        storage = MaildirStorage(config)
        router = RelayRouter(config, storage)
        env = Envelope(mail_from="a@b.com", rcpt_to=["user@remote.com"])
        msg = _make_message()
        router.deliver(env, msg)
        assert router.delivery_log[0]["mx_host"] == "relay.example.com"

    def test_delivery_log(self, config):
        storage = MaildirStorage(config)
        router = RelayRouter(config, storage)
        assert len(router.delivery_log) == 0


# ============================================================
# Constants and Enum Tests
# ============================================================


class TestConstants:
    """Tests for module constants and enums."""

    def test_version(self):
        assert FIZZMAIL_VERSION == "1.0.0"

    def test_server_name(self):
        assert "FizzMail" in FIZZMAIL_SERVER_NAME

    def test_default_ports(self):
        assert DEFAULT_SMTP_PORT == 2525
        assert DEFAULT_IMAP_PORT == 1143

    def test_smtp_replies(self):
        assert 220 in SMTP_REPLIES
        assert 250 in SMTP_REPLIES
        assert 550 in SMTP_REPLIES

    def test_system_flags(self):
        assert r"\Seen" in IMAP_SYSTEM_FLAGS
        assert r"\Deleted" in IMAP_SYSTEM_FLAGS

    def test_maildir_flag_map_roundtrip(self):
        for flag, char in MAILDIR_FLAG_MAP.items():
            assert MAILDIR_FLAG_REVERSE[char] == flag

    def test_smtp_states(self):
        assert len(SMTPState) == 8

    def test_imap_states(self):
        assert len(IMAPState) == 4

    def test_queue_statuses(self):
        assert QueueStatus.PENDING.name == "PENDING"
        assert QueueStatus.SENT.name == "SENT"

    def test_spf_results(self):
        assert SPFResult.PASS.value == "pass"
        assert SPFResult.FAIL.value == "fail"

    def test_dkim_results(self):
        assert DKIMResult.PASS.value == "pass"

    def test_dmarc_policies(self):
        assert DMARCPolicy.REJECT.value == "reject"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 120

    def test_default_credentials(self):
        assert "postmaster" in DEFAULT_CREDENTIALS
        assert "admin" in DEFAULT_CREDENTIALS
        assert "fizzbuzz" in DEFAULT_CREDENTIALS
