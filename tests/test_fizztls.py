"""
Enterprise FizzBuzz Platform - FizzTLS Test Suite

Validates the Transport Layer Security subsystem responsible for encrypted
inter-module communication. TLS handshakes, certificate management, and
session encryption are mission-critical for ensuring that no unauthorized
party can observe intermediate FizzBuzz computations in transit.
"""

from __future__ import annotations

import base64
from datetime import datetime, timedelta

import pytest

from enterprise_fizzbuzz.domain.exceptions.fizztls import (
    FizzTLSCertificateError,
    FizzTLSError,
    FizzTLSHandshakeError,
    FizzTLSNotFoundError,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext
from enterprise_fizzbuzz.infrastructure.fizztls import (
    FIZZTLS_VERSION,
    MIDDLEWARE_PRIORITY,
    Certificate,
    CertificateStore,
    CipherSuite,
    FizzTLSDashboard,
    FizzTLSMiddleware,
    HandshakeState,
    TLSConfig,
    TLSEngine,
    TLSSession,
    TLSVersion,
    create_fizztls_subsystem,
)


# ============================================================
# Constants
# ============================================================


class TestFizzTLSConstants:
    """Verify module-level constants conform to platform integration requirements."""

    def test_version_string(self):
        """The TLS subsystem version must follow semver for dependency resolution."""
        assert FIZZTLS_VERSION == "1.0.0"

    def test_middleware_priority(self):
        """Middleware priority 215 places TLS after authentication but before logging."""
        assert MIDDLEWARE_PRIORITY == 215


# ============================================================
# TLSVersion Enum
# ============================================================


class TestTLSVersion:
    """Protocol version negotiation depends on correct enum membership."""

    def test_tls_1_2_exists(self):
        """TLS 1.2 support is required for backward compatibility with legacy modules."""
        assert TLSVersion.TLS_1_2.value == "tls_1_2"

    def test_tls_1_3_exists(self):
        """TLS 1.3 is the preferred protocol version for all new sessions."""
        assert TLSVersion.TLS_1_3.value == "tls_1_3"

    def test_versions_are_distinct(self):
        """Version confusion between 1.2 and 1.3 would cause cipher mismatch errors."""
        assert TLSVersion.TLS_1_2 != TLSVersion.TLS_1_3


# ============================================================
# CipherSuite Enum
# ============================================================


class TestCipherSuite:
    """Cipher suite availability determines the security posture of each session."""

    def test_aes_128_gcm(self):
        """AES-128-GCM provides authenticated encryption with minimal overhead."""
        assert CipherSuite.AES_128_GCM_SHA256.value == "TLS_AES_128_GCM_SHA256"

    def test_aes_256_gcm(self):
        """AES-256-GCM offers higher security margin for sensitive FizzBuzz data."""
        assert CipherSuite.AES_256_GCM_SHA384.value == "TLS_AES_256_GCM_SHA384"

    def test_chacha20_poly1305(self):
        """ChaCha20-Poly1305 is essential for deployments without AES-NI support."""
        assert CipherSuite.CHACHA20_POLY1305_SHA256.value == "TLS_CHACHA20_POLY1305_SHA256"


# ============================================================
# HandshakeState Enum
# ============================================================


class TestHandshakeState:
    """Handshake state machine correctness prevents man-in-the-middle attacks."""

    def test_all_states_exist(self):
        """The full TLS handshake requires exactly eight distinct states."""
        expected = {
            "INITIAL",
            "CLIENT_HELLO",
            "SERVER_HELLO",
            "CERTIFICATE",
            "KEY_EXCHANGE",
            "FINISHED",
            "ESTABLISHED",
            "CLOSED",
        }
        actual = {s.name for s in HandshakeState}
        assert expected == actual


# ============================================================
# TLSConfig Dataclass
# ============================================================


class TestTLSConfig:
    """Configuration defaults must match deployment specifications."""

    def test_default_version_is_tls_1_3(self):
        """TLS 1.3 is the mandated default per enterprise security policy."""
        config = TLSConfig(dashboard_width=120)
        assert config.default_version == TLSVersion.TLS_1_3

    def test_dashboard_width_stored(self):
        """Dashboard width propagates to the rendering subsystem."""
        config = TLSConfig(dashboard_width=80)
        assert config.dashboard_width == 80


# ============================================================
# Certificate & CertificateStore
# ============================================================


class TestCertificateStore:
    """Certificate lifecycle management underpins the entire trust model."""

    def setup_method(self):
        self.store = CertificateStore()

    def test_add_certificate_returns_certificate(self):
        """Adding a certificate must return a fully populated Certificate object."""
        cert = self.store.add_certificate("fizzbuzz.local", "FizzCA")
        assert isinstance(cert, Certificate)
        assert cert.subject == "fizzbuzz.local"
        assert cert.issuer == "FizzCA"

    def test_certificate_has_id_and_fingerprint(self):
        """Each certificate requires a unique identifier and cryptographic fingerprint."""
        cert = self.store.add_certificate("node-1.fizz", "FizzCA")
        assert isinstance(cert.cert_id, str)
        assert len(cert.cert_id) > 0
        assert isinstance(cert.fingerprint, str)
        assert len(cert.fingerprint) > 0

    def test_certificate_validity_dates(self):
        """Validity window must be parseable and span the requested duration."""
        cert = self.store.add_certificate("node-2.fizz", "FizzCA", valid_days=30)
        valid_from = datetime.fromisoformat(cert.valid_from)
        valid_to = datetime.fromisoformat(cert.valid_to)
        delta = valid_to - valid_from
        assert 29 <= delta.days <= 31

    def test_get_certificate_by_id(self):
        """Certificate retrieval by ID is required for session binding."""
        cert = self.store.add_certificate("lookup.fizz", "FizzCA")
        retrieved = self.store.get_certificate(cert.cert_id)
        assert retrieved.cert_id == cert.cert_id
        assert retrieved.subject == "lookup.fizz"

    def test_get_certificate_not_found_raises(self):
        """Querying a nonexistent certificate must raise a domain exception."""
        with pytest.raises((FizzTLSNotFoundError, FizzTLSCertificateError)):
            self.store.get_certificate("nonexistent-id")

    def test_list_certificates(self):
        """Listing must return all certificates in the store."""
        self.store.add_certificate("a.fizz", "FizzCA")
        self.store.add_certificate("b.fizz", "FizzCA")
        certs = self.store.list_certificates()
        assert len(certs) == 2
        subjects = {c.subject for c in certs}
        assert subjects == {"a.fizz", "b.fizz"}

    def test_verify_valid_certificate(self):
        """A non-expired certificate must pass verification."""
        cert = self.store.add_certificate("valid.fizz", "FizzCA", valid_days=365)
        assert self.store.verify(cert.cert_id) is True

    def test_verify_expired_certificate(self):
        """An expired certificate must fail verification to prevent insecure sessions."""
        cert = self.store.add_certificate("expired.fizz", "FizzCA", valid_days=0)
        assert self.store.verify(cert.cert_id) is False


# ============================================================
# TLSEngine - Session Management
# ============================================================


class TestTLSEngine:
    """The TLS engine manages session lifecycle from creation to termination."""

    def setup_method(self):
        self.engine = TLSEngine()

    def test_create_session_default_version(self):
        """New sessions default to TLS 1.3 per enterprise policy."""
        session = self.engine.create_session()
        assert isinstance(session, TLSSession)
        assert session.version == TLSVersion.TLS_1_3
        assert session.state == HandshakeState.INITIAL

    def test_create_session_tls_1_2(self):
        """Legacy modules may request TLS 1.2 sessions explicitly."""
        session = self.engine.create_session(version=TLSVersion.TLS_1_2)
        assert session.version == TLSVersion.TLS_1_2

    def test_session_has_unique_id(self):
        """Session IDs must be unique to prevent cross-session data leakage."""
        s1 = self.engine.create_session()
        s2 = self.engine.create_session()
        assert s1.session_id != s2.session_id

    def test_get_session(self):
        """Session retrieval by ID is required for encrypt/decrypt operations."""
        session = self.engine.create_session()
        retrieved = self.engine.get_session(session.session_id)
        assert retrieved.session_id == session.session_id

    def test_get_session_not_found_raises(self):
        """Querying a nonexistent session must raise a domain exception."""
        with pytest.raises(FizzTLSNotFoundError):
            self.engine.get_session("nonexistent-session-id")

    def test_list_sessions(self):
        """Session listing is required for the operations dashboard."""
        self.engine.create_session()
        self.engine.create_session()
        sessions = self.engine.list_sessions()
        assert len(sessions) == 2


# ============================================================
# TLSEngine - Handshake Lifecycle
# ============================================================


class TestTLSHandshake:
    """The TLS handshake protocol must advance through all states in sequence."""

    def setup_method(self):
        self.engine = TLSEngine()

    def test_handshake_reaches_established(self):
        """A successful handshake transitions the session to ESTABLISHED state."""
        session = self.engine.create_session()
        result = self.engine.handshake(session.session_id)
        assert result.state == HandshakeState.ESTABLISHED

    def test_handshake_assigns_cipher_suite(self):
        """Cipher suite negotiation must select a valid suite during handshake."""
        session = self.engine.create_session()
        result = self.engine.handshake(session.session_id)
        assert result.cipher_suite is not None
        assert isinstance(result.cipher_suite, CipherSuite)

    def test_handshake_on_nonexistent_session_raises(self):
        """Handshaking a nonexistent session indicates a protocol violation."""
        with pytest.raises((FizzTLSNotFoundError, FizzTLSHandshakeError)):
            self.engine.handshake("ghost-session")

    def test_close_session(self):
        """Closing a session must transition it to CLOSED state."""
        session = self.engine.create_session()
        self.engine.handshake(session.session_id)
        closed = self.engine.close(session.session_id)
        assert closed.state == HandshakeState.CLOSED

    def test_close_nonexistent_session_raises(self):
        """Closing a nonexistent session must raise a domain exception."""
        with pytest.raises(FizzTLSNotFoundError):
            self.engine.close("nonexistent-session")


# ============================================================
# TLSEngine - Encrypt / Decrypt
# ============================================================


class TestTLSEncryption:
    """Encryption and decryption ensure confidentiality of FizzBuzz results in transit."""

    def setup_method(self):
        self.engine = TLSEngine()
        self.session = self.engine.create_session()
        self.engine.handshake(self.session.session_id)

    def test_encrypt_returns_string(self):
        """Encrypted output must be a string suitable for wire transport."""
        ciphertext = self.engine.encrypt(self.session.session_id, "FizzBuzz")
        assert isinstance(ciphertext, str)
        assert len(ciphertext) > 0

    def test_encrypt_differs_from_plaintext(self):
        """Encryption must transform the plaintext; identity is not encryption."""
        ciphertext = self.engine.encrypt(self.session.session_id, "FizzBuzz")
        assert ciphertext != "FizzBuzz"

    def test_decrypt_roundtrip(self):
        """Decryption of encrypted data must recover the original plaintext exactly."""
        plaintext = "The number 15 is FizzBuzz"
        ciphertext = self.engine.encrypt(self.session.session_id, plaintext)
        recovered = self.engine.decrypt(self.session.session_id, ciphertext)
        assert recovered == plaintext

    def test_encrypt_on_non_established_session_raises(self):
        """Encrypting on a session that has not completed handshake is a protocol error."""
        fresh = self.engine.create_session()
        with pytest.raises((FizzTLSHandshakeError, FizzTLSError)):
            self.engine.encrypt(fresh.session_id, "secret")

    def test_decrypt_on_non_established_session_raises(self):
        """Decrypting on a session that has not completed handshake is a protocol error."""
        fresh = self.engine.create_session()
        with pytest.raises((FizzTLSHandshakeError, FizzTLSError)):
            self.engine.decrypt(fresh.session_id, "data")


# ============================================================
# FizzTLSDashboard
# ============================================================


class TestFizzTLSDashboard:
    """The TLS dashboard provides operational visibility into session and certificate state."""

    def test_render_returns_string(self):
        """Dashboard output must be renderable as a terminal-compatible string."""
        dashboard = FizzTLSDashboard()
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_contains_tls_header(self):
        """The dashboard must identify itself as the TLS subsystem display."""
        dashboard = FizzTLSDashboard()
        output = dashboard.render()
        assert "TLS" in output.upper()


# ============================================================
# FizzTLSMiddleware
# ============================================================


class TestFizzTLSMiddleware:
    """Middleware integration enables transparent TLS for all pipeline traffic."""

    def setup_method(self):
        self.middleware = FizzTLSMiddleware()

    def test_get_name(self):
        """The middleware name is used for pipeline registration and logging."""
        assert self.middleware.get_name() == "fizztls"

    def test_get_priority(self):
        """Priority must match the module constant for consistent ordering."""
        assert self.middleware.get_priority() == 215

    def test_process_passes_context_through(self):
        """The middleware must invoke the next handler and return a valid context."""
        ctx = ProcessingContext(number=15, session_id="test-session-001")
        called = []

        def next_handler(c: ProcessingContext) -> ProcessingContext:
            called.append(True)
            return c

        result = self.middleware.process(ctx, next_handler)
        assert isinstance(result, ProcessingContext)
        assert len(called) == 1
        assert result.number == 15


# ============================================================
# Factory Function
# ============================================================


class TestCreateFizzTLSSubsystem:
    """The factory function assembles the complete TLS subsystem for dependency injection."""

    def test_factory_returns_four_components(self):
        """The subsystem factory must return engine, store, dashboard, and middleware."""
        result = create_fizztls_subsystem()
        assert len(result) == 4

    def test_factory_component_types(self):
        """Each returned component must be the correct type for wiring."""
        engine, store, dashboard, middleware = create_fizztls_subsystem()
        assert isinstance(engine, TLSEngine)
        assert isinstance(store, CertificateStore)
        assert isinstance(dashboard, FizzTLSDashboard)
        assert isinstance(middleware, FizzTLSMiddleware)


# ============================================================
# Exception Hierarchy
# ============================================================


class TestFizzTLSExceptions:
    """Exception hierarchy must support granular error handling in calling code."""

    def test_base_error_is_exception(self):
        """FizzTLSError must be catchable as a standard Exception."""
        assert issubclass(FizzTLSError, Exception)

    def test_not_found_inherits_base(self):
        """NotFound errors must be catchable via the base FizzTLS exception."""
        assert issubclass(FizzTLSNotFoundError, FizzTLSError)

    def test_handshake_error_inherits_base(self):
        """Handshake errors must be catchable via the base FizzTLS exception."""
        assert issubclass(FizzTLSHandshakeError, FizzTLSError)

    def test_certificate_error_inherits_base(self):
        """Certificate errors must be catchable via the base FizzTLS exception."""
        assert issubclass(FizzTLSCertificateError, FizzTLSError)
