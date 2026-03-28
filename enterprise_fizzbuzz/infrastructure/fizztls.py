"""Enterprise FizzBuzz Platform - FizzTLS: Transport Layer Security"""
from __future__ import annotations
import base64, hashlib, logging, uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from enterprise_fizzbuzz.domain.exceptions.fizztls import *
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizztls")
EVENT_TLS = EventType.register("FIZZTLS_HANDSHAKE")
FIZZTLS_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 215


class TLSVersion(Enum):
    TLS_1_2 = "tls_1_2"
    TLS_1_3 = "tls_1_3"


class CipherSuite(Enum):
    AES_128_GCM_SHA256 = "TLS_AES_128_GCM_SHA256"
    AES_256_GCM_SHA384 = "TLS_AES_256_GCM_SHA384"
    CHACHA20_POLY1305_SHA256 = "TLS_CHACHA20_POLY1305_SHA256"


class HandshakeState(Enum):
    INITIAL = "initial"
    CLIENT_HELLO = "client_hello"
    SERVER_HELLO = "server_hello"
    CERTIFICATE = "certificate"
    KEY_EXCHANGE = "key_exchange"
    FINISHED = "finished"
    ESTABLISHED = "established"
    CLOSED = "closed"


@dataclass
class TLSConfig:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH
    default_version: TLSVersion = TLSVersion.TLS_1_3


@dataclass
class Certificate:
    """An X.509-style certificate for peer authentication."""
    cert_id: str = ""
    subject: str = ""
    issuer: str = ""
    valid_from: str = ""
    valid_to: str = ""
    fingerprint: str = ""


@dataclass
class TLSSession:
    """A TLS session tracking handshake state and negotiated parameters."""
    session_id: str = ""
    state: HandshakeState = HandshakeState.INITIAL
    version: TLSVersion = TLSVersion.TLS_1_3
    cipher_suite: Optional[CipherSuite] = None
    peer_certificate: Optional[Certificate] = None
    _session_key: str = ""


class CertificateStore:
    """Stores and manages X.509 certificates for TLS peer authentication."""

    def __init__(self) -> None:
        self._certificates: OrderedDict[str, Certificate] = OrderedDict()

    def add_certificate(self, subject: str, issuer: str,
                        valid_days: int = 365) -> Certificate:
        """Create and store a new certificate."""
        cert_id = f"cert-{uuid.uuid4().hex[:8]}"
        now = datetime.utcnow()
        fingerprint = hashlib.sha256(f"{cert_id}:{subject}:{issuer}".encode()).hexdigest()[:40]
        cert = Certificate(
            cert_id=cert_id,
            subject=subject,
            issuer=issuer,
            valid_from=now.isoformat(),
            valid_to=(now + timedelta(days=valid_days)).isoformat(),
            fingerprint=fingerprint,
        )
        self._certificates[cert_id] = cert
        logger.debug("Added certificate %s for %s", cert_id, subject)
        return cert

    def get_certificate(self, cert_id: str) -> Certificate:
        cert = self._certificates.get(cert_id)
        if cert is None:
            raise FizzTLSNotFoundError(cert_id)
        return cert

    def list_certificates(self) -> List[Certificate]:
        return list(self._certificates.values())

    def verify(self, cert_id: str) -> bool:
        """Verify a certificate has not expired."""
        cert = self.get_certificate(cert_id)
        now = datetime.utcnow().isoformat()
        return cert.valid_from <= now <= cert.valid_to


class TLSEngine:
    """Manages TLS sessions including handshake negotiation, cipher selection,
    and symmetric encryption/decryption of inter-module traffic."""

    HANDSHAKE_SEQUENCE = [
        HandshakeState.CLIENT_HELLO,
        HandshakeState.SERVER_HELLO,
        HandshakeState.CERTIFICATE,
        HandshakeState.KEY_EXCHANGE,
        HandshakeState.FINISHED,
        HandshakeState.ESTABLISHED,
    ]

    def __init__(self, cert_store: Optional[CertificateStore] = None) -> None:
        self._sessions: OrderedDict[str, TLSSession] = OrderedDict()
        self._cert_store = cert_store or CertificateStore()

    def create_session(self, version: TLSVersion = TLSVersion.TLS_1_3) -> TLSSession:
        """Create a new TLS session in INITIAL state."""
        session_id = f"tls-{uuid.uuid4().hex[:8]}"
        session = TLSSession(
            session_id=session_id,
            state=HandshakeState.INITIAL,
            version=version,
        )
        self._sessions[session_id] = session
        return session

    def handshake(self, session_id: str) -> TLSSession:
        """Perform the full TLS handshake, advancing through all states
        until the session is ESTABLISHED."""
        session = self.get_session(session_id)
        if session.state == HandshakeState.ESTABLISHED:
            return session
        if session.state == HandshakeState.CLOSED:
            raise FizzTLSHandshakeError("Cannot handshake on closed session")

        # Advance through handshake states
        for state in self.HANDSHAKE_SEQUENCE:
            session.state = state
            if state == HandshakeState.SERVER_HELLO:
                # Negotiate cipher suite
                session.cipher_suite = CipherSuite.AES_256_GCM_SHA384
            elif state == HandshakeState.CERTIFICATE:
                # Assign peer certificate if available
                certs = self._cert_store.list_certificates()
                if certs:
                    session.peer_certificate = certs[0]
            elif state == HandshakeState.KEY_EXCHANGE:
                # Generate session key
                session._session_key = hashlib.sha256(
                    f"{session_id}:{uuid.uuid4().hex}".encode()
                ).hexdigest()

        logger.info("TLS handshake completed for session %s (cipher=%s)",
                     session_id, session.cipher_suite.value if session.cipher_suite else "none")
        return session

    def close(self, session_id: str) -> TLSSession:
        """Close a TLS session."""
        session = self.get_session(session_id)
        session.state = HandshakeState.CLOSED
        session._session_key = ""
        return session

    def get_session(self, session_id: str) -> TLSSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise FizzTLSNotFoundError(session_id)
        return session

    def list_sessions(self) -> List[TLSSession]:
        return list(self._sessions.values())

    def encrypt(self, session_id: str, plaintext: str) -> str:
        """Encrypt plaintext using the session's negotiated cipher.

        Simulates authenticated encryption by producing a base64-encoded
        ciphertext with an appended HMAC tag."""
        session = self.get_session(session_id)
        if session.state != HandshakeState.ESTABLISHED:
            raise FizzTLSHandshakeError(
                f"Session not established (state={session.state.value})"
            )
        # Simulated encryption: XOR-based stream cipher with HMAC tag
        key_bytes = session._session_key.encode()[:32]
        encrypted = bytearray()
        for i, ch in enumerate(plaintext.encode()):
            encrypted.append(ch ^ key_bytes[i % len(key_bytes)])
        tag = hashlib.sha256(bytes(encrypted) + key_bytes).hexdigest()[:16]
        return base64.b64encode(bytes(encrypted)).decode() + "." + tag

    def decrypt(self, session_id: str, ciphertext: str) -> str:
        """Decrypt ciphertext using the session's negotiated cipher."""
        session = self.get_session(session_id)
        if session.state != HandshakeState.ESTABLISHED:
            raise FizzTLSHandshakeError(
                f"Session not established (state={session.state.value})"
            )
        parts = ciphertext.split(".")
        if len(parts) != 2:
            raise FizzTLSError("Invalid ciphertext format")
        encrypted = base64.b64decode(parts[0])
        key_bytes = session._session_key.encode()[:32]
        # Verify tag
        expected_tag = hashlib.sha256(encrypted + key_bytes).hexdigest()[:16]
        if parts[1] != expected_tag:
            raise FizzTLSError("Authentication tag mismatch")
        decrypted = bytearray()
        for i, b in enumerate(encrypted):
            decrypted.append(b ^ key_bytes[i % len(key_bytes)])
        return decrypted.decode()


class FizzTLSDashboard:
    def __init__(self, engine: Optional[TLSEngine] = None,
                 cert_store: Optional[CertificateStore] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._engine = engine
        self._cert_store = cert_store
        self._width = width

    def render(self) -> str:
        lines = ["=" * self._width, "FizzTLS Dashboard".center(self._width),
                 "=" * self._width, f"  Version: {FIZZTLS_VERSION}"]
        if self._engine:
            sessions = self._engine.list_sessions()
            lines.append(f"  Sessions: {len(sessions)}")
            established = sum(1 for s in sessions if s.state == HandshakeState.ESTABLISHED)
            lines.append(f"  Established: {established}")
        if self._cert_store:
            certs = self._cert_store.list_certificates()
            lines.append(f"  Certificates: {len(certs)}")
            for c in certs[:5]:
                lines.append(f"  {c.subject:<25} issuer={c.issuer}")
        return "\n".join(lines)


class FizzTLSMiddleware(IMiddleware):
    def __init__(self, engine: Optional[TLSEngine] = None,
                 dashboard: Optional[FizzTLSDashboard] = None) -> None:
        self._engine = engine
        self._dashboard = dashboard

    def get_name(self) -> str: return "fizztls"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY

    def process(self, ctx: Any, next_handler: Any) -> Any:
        if next_handler:
            return next_handler(ctx)
        return ctx

    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "Not initialized"


def create_fizztls_subsystem(
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[TLSEngine, CertificateStore, FizzTLSDashboard, FizzTLSMiddleware]:
    """Factory function that creates and wires the FizzTLS subsystem."""
    cert_store = CertificateStore()
    cert_store.add_certificate("fizzbuzz.enterprise.local", "FizzBuzz Root CA", 365)
    cert_store.add_certificate("api.fizzbuzz.enterprise.local", "FizzBuzz Root CA", 365)

    engine = TLSEngine(cert_store)
    dashboard = FizzTLSDashboard(engine, cert_store, dashboard_width)
    middleware = FizzTLSMiddleware(engine, dashboard)
    logger.info("FizzTLS initialized: %d certificates", len(cert_store.list_certificates()))
    return engine, cert_store, dashboard, middleware
