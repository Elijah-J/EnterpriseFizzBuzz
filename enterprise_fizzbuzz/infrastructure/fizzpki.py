"""
Enterprise FizzBuzz Platform - FizzPKI: Public Key Infrastructure & Certificate Authority

Production-grade PKI and Certificate Authority for the Enterprise FizzBuzz
Platform.  Implements a Root/Intermediate CA hierarchy, X.509v3 certificate
generation (RSA-2048/4096, ECDSA P-256/P-384), Certificate Signing Request
processing, ACME server (RFC 8555) for automated issuance with http-01 and
dns-01 challenges, Certificate Revocation List generation (RFC 5280),
OCSP responder (RFC 6960), certificate transparency logging, automatic
renewal tracking, and certificate inventory management.

FizzPKI fills the cryptographic trust gap -- every TLS-using module generates
self-signed certificates independently.  A platform with 148 infrastructure
modules and no certificate authority is a platform built on unsigned trust.

Architecture reference: Let's Encrypt / Boulder, EJBCA, HashiCorp Vault PKI, RFC 5280/6960/8555.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import logging
import os
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple, Union

from enterprise_fizzbuzz.domain.exceptions.fizzpki import (
    FizzPKIError, FizzPKIKeyGenerationError, FizzPKICSRInvalidError,
    FizzPKICertificateError, FizzPKICertificateExpiredError,
    FizzPKICertificateRevokedError, FizzPKICertificateNotFoundError,
    FizzPKICANotInitializedError, FizzPKICAChainError, FizzPKICRLError,
    FizzPKIOCSPError, FizzPKIACMEError, FizzPKIACMEChallengeError,
    FizzPKIACMEOrderError, FizzPKITransparencyError, FizzPKIRenewalError,
    FizzPKIInventoryError, FizzPKIVaultIntegrationError, FizzPKIConfigError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, FizzBuzzResult, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzpki")

EVENT_PKI_CERT_ISSUED = EventType.register("FIZZPKI_CERT_ISSUED")
EVENT_PKI_CERT_REVOKED = EventType.register("FIZZPKI_CERT_REVOKED")
EVENT_PKI_CRL_GENERATED = EventType.register("FIZZPKI_CRL_GENERATED")
EVENT_PKI_OCSP_QUERY = EventType.register("FIZZPKI_OCSP_QUERY")

FIZZPKI_VERSION = "1.0.0"
FIZZPKI_SERVER_NAME = f"FizzPKI/{FIZZPKI_VERSION} (Enterprise FizzBuzz Platform)"

DEFAULT_ROOT_CA_CN = "Enterprise FizzBuzz Root CA"
DEFAULT_INTERMEDIATE_CA_CN = "Enterprise FizzBuzz Intermediate CA"
DEFAULT_ROOT_VALIDITY_DAYS = 3650
DEFAULT_INTERMEDIATE_VALIDITY_DAYS = 1825
DEFAULT_CERT_VALIDITY_DAYS = 365
DEFAULT_CRL_VALIDITY_HOURS = 24
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 134


class KeyAlgorithm(Enum):
    RSA_2048 = "RSA-2048"
    RSA_4096 = "RSA-4096"
    ECDSA_P256 = "ECDSA-P256"
    ECDSA_P384 = "ECDSA-P384"

class CertificateStatus(Enum):
    VALID = auto()
    EXPIRED = auto()
    REVOKED = auto()
    PENDING = auto()

class RevocationReason(Enum):
    UNSPECIFIED = 0
    KEY_COMPROMISE = 1
    CA_COMPROMISE = 2
    AFFILIATION_CHANGED = 3
    SUPERSEDED = 4
    CESSATION_OF_OPERATION = 5

class ACMEOrderStatus(Enum):
    PENDING = "pending"
    READY = "ready"
    PROCESSING = "processing"
    VALID = "valid"
    INVALID = "invalid"

class ACMEChallengeType(Enum):
    HTTP_01 = "http-01"
    DNS_01 = "dns-01"

class ACMEChallengeStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    VALID = "valid"
    INVALID = "invalid"

class OCSPResponseStatus(Enum):
    GOOD = "good"
    REVOKED = "revoked"
    UNKNOWN = "unknown"


@dataclass
class FizzPKIConfig:
    root_ca_cn: str = DEFAULT_ROOT_CA_CN
    intermediate_ca_cn: str = DEFAULT_INTERMEDIATE_CA_CN
    root_validity_days: int = DEFAULT_ROOT_VALIDITY_DAYS
    intermediate_validity_days: int = DEFAULT_INTERMEDIATE_VALIDITY_DAYS
    cert_validity_days: int = DEFAULT_CERT_VALIDITY_DAYS
    default_key_algorithm: KeyAlgorithm = KeyAlgorithm.ECDSA_P256
    crl_validity_hours: int = DEFAULT_CRL_VALIDITY_HOURS
    acme_enabled: bool = True
    transparency_log_enabled: bool = True
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH

@dataclass
class KeyPair:
    algorithm: KeyAlgorithm = KeyAlgorithm.RSA_2048
    public_key_pem: bytes = b""
    private_key_pem: bytes = b""
    fingerprint: str = ""
    created_at: Optional[datetime] = None

@dataclass
class X509Certificate:
    serial_number: str = ""
    subject_cn: str = ""
    issuer_cn: str = ""
    not_before: Optional[datetime] = None
    not_after: Optional[datetime] = None
    subject_alt_names: List[str] = field(default_factory=list)
    key_usage: List[str] = field(default_factory=list)
    extended_key_usage: List[str] = field(default_factory=list)
    basic_constraints_ca: bool = False
    basic_constraints_path_len: Optional[int] = None
    public_key_fingerprint: str = ""
    signature_algorithm: str = "sha256WithRSAEncryption"
    status: CertificateStatus = CertificateStatus.VALID
    revocation_reason: Optional[RevocationReason] = None
    revoked_at: Optional[datetime] = None
    certificate_pem: bytes = b""

@dataclass
class CertificateSigningRequest:
    subject_cn: str = ""
    subject_alt_names: List[str] = field(default_factory=list)
    key_algorithm: KeyAlgorithm = KeyAlgorithm.RSA_2048
    public_key_fingerprint: str = ""
    requested_at: Optional[datetime] = None
    csr_pem: bytes = b""

@dataclass
class CRLEntry:
    serial_number: str = ""
    revocation_date: Optional[datetime] = None
    reason: RevocationReason = RevocationReason.UNSPECIFIED

@dataclass
class CRLDocument:
    issuer_cn: str = ""
    this_update: Optional[datetime] = None
    next_update: Optional[datetime] = None
    entries: List[CRLEntry] = field(default_factory=list)
    crl_number: int = 0
    signature: str = ""

@dataclass
class OCSPRequest:
    serial_number: str = ""
    issuer_cn: str = ""

@dataclass
class OCSPResponse:
    serial_number: str = ""
    status: OCSPResponseStatus = OCSPResponseStatus.UNKNOWN
    this_update: Optional[datetime] = None
    next_update: Optional[datetime] = None
    revocation_time: Optional[datetime] = None
    revocation_reason: Optional[RevocationReason] = None

@dataclass
class ACMEAccount:
    account_id: str = ""
    contact_email: str = ""
    created_at: Optional[datetime] = None
    status: str = "valid"

@dataclass
class ACMEOrder:
    order_id: str = ""
    account_id: str = ""
    identifiers: List[str] = field(default_factory=list)
    status: ACMEOrderStatus = ACMEOrderStatus.PENDING
    challenges: List["ACMEChallenge"] = field(default_factory=list)
    certificate_serial: Optional[str] = None
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

@dataclass
class ACMEChallenge:
    challenge_id: str = ""
    challenge_type: ACMEChallengeType = ACMEChallengeType.HTTP_01
    token: str = ""
    key_authorization: str = ""
    status: ACMEChallengeStatus = ACMEChallengeStatus.PENDING
    validated_at: Optional[datetime] = None

@dataclass
class TransparencyLogEntry:
    log_index: int = 0
    certificate_serial: str = ""
    issuer_cn: str = ""
    subject_cn: str = ""
    logged_at: Optional[datetime] = None
    merkle_hash: str = ""


# ============================================================
# Key Generator
# ============================================================

class KeyGenerator:
    """Generates RSA and ECDSA key pairs (simulated)."""

    def generate(self, algorithm: KeyAlgorithm) -> KeyPair:
        unique = os.urandom(32)
        if algorithm in (KeyAlgorithm.RSA_2048, KeyAlgorithm.RSA_4096):
            bits = 2048 if algorithm == KeyAlgorithm.RSA_2048 else 4096
            pub = b"-----BEGIN PUBLIC KEY-----\n" + base64.b64encode(
                hashlib.sha256(b"rsa-pub-" + unique).digest() * (bits // 256)
            ) + b"\n-----END PUBLIC KEY-----\n"
            priv = b"-----BEGIN PRIVATE KEY-----\n" + base64.b64encode(
                hashlib.sha256(b"rsa-priv-" + unique).digest() * (bits // 256)
            ) + b"\n-----END PRIVATE KEY-----\n"
        else:
            curve = "P-256" if algorithm == KeyAlgorithm.ECDSA_P256 else "P-384"
            pub = b"-----BEGIN PUBLIC KEY-----\n" + base64.b64encode(
                hashlib.sha256(f"ecdsa-pub-{curve}-".encode() + unique).digest()
            ) + b"\n-----END PUBLIC KEY-----\n"
            priv = b"-----BEGIN PRIVATE KEY-----\n" + base64.b64encode(
                hashlib.sha256(f"ecdsa-priv-{curve}-".encode() + unique).digest()
            ) + b"\n-----END PRIVATE KEY-----\n"

        fingerprint = hashlib.sha256(pub).hexdigest()

        return KeyPair(
            algorithm=algorithm, public_key_pem=pub, private_key_pem=priv,
            fingerprint=fingerprint, created_at=datetime.now(timezone.utc),
        )


# ============================================================
# X.509 Certificate Builder
# ============================================================

class X509CertificateBuilder:
    """Builds X.509v3 certificates with proper extensions."""

    def build_root_ca(self, config: FizzPKIConfig, key_pair: KeyPair) -> X509Certificate:
        now = datetime.utcnow()
        serial = self._generate_serial()
        return X509Certificate(
            serial_number=serial,
            subject_cn=config.root_ca_cn,
            issuer_cn=config.root_ca_cn,  # self-signed
            not_before=now,
            not_after=now + timedelta(days=config.root_validity_days),
            key_usage=["keyCertSign", "cRLSign"],
            basic_constraints_ca=True,
            basic_constraints_path_len=1,
            public_key_fingerprint=key_pair.fingerprint,
            status=CertificateStatus.VALID,
            certificate_pem=self._build_pem(serial, config.root_ca_cn),
        )

    def build_intermediate_ca(self, config: FizzPKIConfig, key_pair: KeyPair,
                               root_cert: X509Certificate, root_key: KeyPair) -> X509Certificate:
        now = datetime.utcnow()
        serial = self._generate_serial()
        return X509Certificate(
            serial_number=serial,
            subject_cn=config.intermediate_ca_cn,
            issuer_cn=root_cert.subject_cn,
            not_before=now,
            not_after=now + timedelta(days=config.intermediate_validity_days),
            key_usage=["keyCertSign", "cRLSign"],
            basic_constraints_ca=True,
            basic_constraints_path_len=0,
            public_key_fingerprint=key_pair.fingerprint,
            status=CertificateStatus.VALID,
            certificate_pem=self._build_pem(serial, config.intermediate_ca_cn),
        )

    def build_end_entity(self, csr: CertificateSigningRequest,
                         issuer_cert: X509Certificate, issuer_key: KeyPair,
                         validity_days: int = DEFAULT_CERT_VALIDITY_DAYS) -> X509Certificate:
        now = datetime.utcnow()
        serial = self._generate_serial()
        return X509Certificate(
            serial_number=serial,
            subject_cn=csr.subject_cn,
            issuer_cn=issuer_cert.subject_cn,
            not_before=now,
            not_after=now + timedelta(days=validity_days),
            subject_alt_names=list(csr.subject_alt_names),
            key_usage=["digitalSignature", "keyEncipherment"],
            extended_key_usage=["serverAuth", "clientAuth"],
            basic_constraints_ca=False,
            public_key_fingerprint=csr.public_key_fingerprint,
            status=CertificateStatus.VALID,
            certificate_pem=self._build_pem(serial, csr.subject_cn),
        )

    def _generate_serial(self) -> str:
        return os.urandom(16).hex()

    def _build_pem(self, serial: str, cn: str) -> bytes:
        content = base64.b64encode(f"{serial}:{cn}:{time.time()}".encode())
        return b"-----BEGIN CERTIFICATE-----\n" + content + b"\n-----END CERTIFICATE-----\n"


# ============================================================
# CSR Processor
# ============================================================

class CSRProcessor:
    """Validates and processes Certificate Signing Requests."""

    def create_csr(self, subject_cn: str, san: List[str], key_pair: KeyPair) -> CertificateSigningRequest:
        content = base64.b64encode(f"{subject_cn}:{','.join(san)}:{key_pair.fingerprint}".encode())
        return CertificateSigningRequest(
            subject_cn=subject_cn,
            subject_alt_names=list(san),
            key_algorithm=key_pair.algorithm,
            public_key_fingerprint=key_pair.fingerprint,
            requested_at=datetime.now(timezone.utc),
            csr_pem=b"-----BEGIN CERTIFICATE REQUEST-----\n" + content + b"\n-----END CERTIFICATE REQUEST-----\n",
        )

    def validate_csr(self, csr: CertificateSigningRequest) -> bool:
        if not csr.subject_cn:
            return False
        if not csr.csr_pem or b"CERTIFICATE REQUEST" not in csr.csr_pem:
            return False
        return True


# ============================================================
# Certificate Authority
# ============================================================

class CertificateAuthority:
    """Central CA managing the Root/Intermediate hierarchy and certificate lifecycle."""

    def __init__(self, config: FizzPKIConfig) -> None:
        self._config = config
        self._key_gen = KeyGenerator()
        self._builder = X509CertificateBuilder()
        self._root_cert: Optional[X509Certificate] = None
        self._root_key: Optional[KeyPair] = None
        self._intermediate_cert: Optional[X509Certificate] = None
        self._intermediate_key: Optional[KeyPair] = None
        self._store: OrderedDict[str, X509Certificate] = OrderedDict()
        self._revocation_list: List[CRLEntry] = []
        self._initialized = False
        self._issued_count = 0
        self._revoked_count = 0

    def initialize(self) -> None:
        self._root_key = self._key_gen.generate(KeyAlgorithm.RSA_4096)
        self._root_cert = self._builder.build_root_ca(self._config, self._root_key)
        self._store[self._root_cert.serial_number] = self._root_cert

        self._intermediate_key = self._key_gen.generate(self._config.default_key_algorithm)
        self._intermediate_cert = self._builder.build_intermediate_ca(
            self._config, self._intermediate_key, self._root_cert, self._root_key
        )
        self._store[self._intermediate_cert.serial_number] = self._intermediate_cert
        self._initialized = True
        logger.info("CA initialized: root=%s intermediate=%s",
                     self._root_cert.subject_cn, self._intermediate_cert.subject_cn)

    def is_initialized(self) -> bool:
        return self._initialized

    def issue_certificate(self, csr: CertificateSigningRequest,
                          validity_days: Optional[int] = None) -> X509Certificate:
        if not self._initialized:
            raise FizzPKICANotInitializedError("CA not initialized")
        vd = validity_days or self._config.cert_validity_days
        cert = self._builder.build_end_entity(csr, self._intermediate_cert, self._intermediate_key, vd)
        self._store[cert.serial_number] = cert
        self._issued_count += 1
        return cert

    def revoke_certificate(self, serial: str, reason: RevocationReason = RevocationReason.UNSPECIFIED) -> None:
        cert = self._store.get(serial)
        if cert is None:
            raise FizzPKICertificateNotFoundError(serial)
        cert.status = CertificateStatus.REVOKED
        cert.revocation_reason = reason
        cert.revoked_at = datetime.now(timezone.utc)
        self._revocation_list.append(CRLEntry(
            serial_number=serial,
            revocation_date=cert.revoked_at,
            reason=reason,
        ))
        self._revoked_count += 1

    def get_certificate(self, serial: str) -> X509Certificate:
        cert = self._store.get(serial)
        if cert is None:
            raise FizzPKICertificateNotFoundError(serial)
        return cert

    def get_chain(self) -> List[X509Certificate]:
        chain = []
        if self._intermediate_cert:
            chain.append(self._intermediate_cert)
        if self._root_cert:
            chain.append(self._root_cert)
        return chain

    def get_metrics(self) -> Dict[str, Any]:
        return {
            "initialized": self._initialized,
            "certificates_issued": self._issued_count,
            "certificates_revoked": self._revoked_count,
            "total_certificates": len(self._store),
            "crl_entries": len(self._revocation_list),
        }

    @property
    def revocation_list(self) -> List[CRLEntry]:
        return list(self._revocation_list)

    @property
    def certificate_store(self) -> Dict[str, X509Certificate]:
        return dict(self._store)


# ============================================================
# CRL Generator
# ============================================================

class CRLGenerator:
    """Generates Certificate Revocation Lists per RFC 5280."""

    _crl_counter = 0

    def generate(self, ca: CertificateAuthority) -> CRLDocument:
        CRLGenerator._crl_counter += 1
        now = datetime.now(timezone.utc)
        return CRLDocument(
            issuer_cn=ca._intermediate_cert.subject_cn if ca._intermediate_cert else "",
            this_update=now,
            next_update=now + timedelta(hours=DEFAULT_CRL_VALIDITY_HOURS),
            entries=list(ca.revocation_list),
            crl_number=CRLGenerator._crl_counter,
            signature=hashlib.sha256(f"crl-{CRLGenerator._crl_counter}".encode()).hexdigest()[:16],
        )

    def is_revoked(self, serial: str, crl: CRLDocument) -> bool:
        return any(e.serial_number == serial for e in crl.entries)


# ============================================================
# OCSP Responder
# ============================================================

class OCSPResponder:
    """Online Certificate Status Protocol responder per RFC 6960."""

    def __init__(self) -> None:
        self._query_count = 0

    def handle_request(self, request: OCSPRequest, ca: CertificateAuthority) -> OCSPResponse:
        self._query_count += 1
        now = datetime.now(timezone.utc)

        try:
            cert = ca.get_certificate(request.serial_number)
        except FizzPKICertificateNotFoundError:
            return OCSPResponse(
                serial_number=request.serial_number,
                status=OCSPResponseStatus.UNKNOWN,
                this_update=now,
            )

        if cert.status == CertificateStatus.REVOKED:
            return OCSPResponse(
                serial_number=request.serial_number,
                status=OCSPResponseStatus.REVOKED,
                this_update=now,
                revocation_time=cert.revoked_at,
                revocation_reason=cert.revocation_reason,
            )

        return OCSPResponse(
            serial_number=request.serial_number,
            status=OCSPResponseStatus.GOOD,
            this_update=now,
            next_update=now + timedelta(minutes=60),
        )

    def get_query_count(self) -> int:
        return self._query_count


# ============================================================
# ACME Server
# ============================================================

class ACMEServer:
    """ACME protocol server per RFC 8555."""

    def __init__(self, config: FizzPKIConfig) -> None:
        self._config = config
        self._ca: Optional[CertificateAuthority] = None
        self._accounts: Dict[str, ACMEAccount] = {}
        self._orders: Dict[str, ACMEOrder] = {}
        self._challenges: Dict[str, ACMEChallenge] = {}
        # Auto-initialize a CA if none provided
        self._own_ca = CertificateAuthority(config)
        self._own_ca.initialize()
        self._ca = self._own_ca

    def set_ca(self, ca: CertificateAuthority) -> None:
        self._ca = ca

    def create_account(self, contact_email: str) -> ACMEAccount:
        acct = ACMEAccount(
            account_id=f"acct-{uuid.uuid4().hex[:8]}",
            contact_email=contact_email,
            created_at=datetime.now(timezone.utc),
        )
        self._accounts[acct.account_id] = acct
        return acct

    def create_order(self, account_id: str, identifiers: List[str]) -> ACMEOrder:
        if account_id not in self._accounts:
            raise FizzPKIACMEError(f"Unknown account: {account_id}")

        token = uuid.uuid4().hex[:16]
        key_auth = hashlib.sha256(f"{token}.fizzbuzz-thumbprint".encode()).hexdigest()

        challenge = ACMEChallenge(
            challenge_id=f"chall-{uuid.uuid4().hex[:8]}",
            challenge_type=ACMEChallengeType.HTTP_01,
            token=token,
            key_authorization=key_auth,
            status=ACMEChallengeStatus.PENDING,
        )
        self._challenges[challenge.challenge_id] = challenge

        order = ACMEOrder(
            order_id=f"order-{uuid.uuid4().hex[:8]}",
            account_id=account_id,
            identifiers=list(identifiers),
            status=ACMEOrderStatus.PENDING,
            challenges=[challenge],
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        self._orders[order.order_id] = order
        return order

    def get_challenge(self, order_id: str) -> ACMEChallenge:
        order = self._orders.get(order_id)
        if order is None:
            raise FizzPKIACMEOrderError(f"Unknown order: {order_id}")
        if not order.challenges:
            raise FizzPKIACMEChallengeError("No challenges for order")
        return order.challenges[0]

    def validate_challenge(self, challenge_id: str, response: str) -> bool:
        challenge = self._challenges.get(challenge_id)
        if challenge is None:
            raise FizzPKIACMEChallengeError(f"Unknown challenge: {challenge_id}")

        if response == challenge.key_authorization:
            challenge.status = ACMEChallengeStatus.VALID
            challenge.validated_at = datetime.now(timezone.utc)
            # Update order status
            for order in self._orders.values():
                if any(c.challenge_id == challenge_id for c in order.challenges):
                    order.status = ACMEOrderStatus.READY
            return True
        else:
            challenge.status = ACMEChallengeStatus.INVALID
            return False

    def finalize_order(self, order_id: str, csr: CertificateSigningRequest) -> X509Certificate:
        order = self._orders.get(order_id)
        if order is None:
            raise FizzPKIACMEOrderError(f"Unknown order: {order_id}")
        if order.status not in (ACMEOrderStatus.READY, ACMEOrderStatus.PENDING):
            raise FizzPKIACMEOrderError(f"Order not ready: {order.status.value}")

        if self._ca is None:
            raise FizzPKICANotInitializedError("ACME server has no CA")

        order.status = ACMEOrderStatus.PROCESSING
        cert = self._ca.issue_certificate(csr)
        order.status = ACMEOrderStatus.VALID
        order.certificate_serial = cert.serial_number
        return cert

    def get_directory(self) -> Dict[str, str]:
        base = "https://acme.fizzbuzz.local"
        return {
            "newNonce": f"{base}/acme/new-nonce",
            "newAccount": f"{base}/acme/new-acct",
            "newOrder": f"{base}/acme/new-order",
            "revokeCert": f"{base}/acme/revoke-cert",
            "keyChange": f"{base}/acme/key-change",
        }


# ============================================================
# Transparency Log
# ============================================================

class TransparencyLog:
    """Certificate Transparency log with Merkle hashing."""

    def __init__(self) -> None:
        self._entries: List[TransparencyLogEntry] = []

    def append(self, cert: X509Certificate) -> TransparencyLogEntry:
        index = len(self._entries)
        merkle_data = f"{cert.serial_number}:{cert.subject_cn}:{index}:{time.time()}"
        merkle_hash = hashlib.sha256(merkle_data.encode()).hexdigest()

        entry = TransparencyLogEntry(
            log_index=index,
            certificate_serial=cert.serial_number,
            issuer_cn=cert.issuer_cn,
            subject_cn=cert.subject_cn,
            logged_at=datetime.now(timezone.utc),
            merkle_hash=merkle_hash,
        )
        self._entries.append(entry)
        return entry

    def get_entry(self, index: int) -> TransparencyLogEntry:
        if 0 <= index < len(self._entries):
            return self._entries[index]
        raise FizzPKITransparencyError(f"Index {index} out of range")

    def get_log_size(self) -> int:
        return len(self._entries)


# ============================================================
# Renewal Tracker
# ============================================================

class RenewalTracker:
    """Monitors certificate expiration and flags renewals."""

    def __init__(self, renewal_window_days: int = 30) -> None:
        self._window_days = renewal_window_days
        self._pending: List[Dict[str, Any]] = []

    def scan(self, ca: CertificateAuthority) -> List[Dict[str, Any]]:
        self._pending.clear()
        now = datetime.utcnow()
        threshold = now + timedelta(days=self._window_days)
        for serial, cert in ca.certificate_store.items():
            if cert.status == CertificateStatus.VALID and cert.not_after and cert.not_after <= threshold:
                self._pending.append({
                    "serial": cert.serial_number,
                    "subject_cn": cert.subject_cn,
                    "not_after": cert.not_after,
                    "days_remaining": (cert.not_after - now).days,
                })
        return list(self._pending)

    def get_pending_count(self) -> int:
        return len(self._pending)


# ============================================================
# Dashboard
# ============================================================

class FizzPKIDashboard:
    """ASCII dashboard for PKI status."""

    def __init__(self, ca: CertificateAuthority, width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._ca = ca
        self._width = width

    def render(self) -> str:
        m = self._ca.get_metrics()
        lines = [
            "=" * self._width,
            "FizzPKI Certificate Authority Dashboard".center(self._width),
            "=" * self._width,
            f"  Version:           {FIZZPKI_VERSION}",
            f"  CA Initialized:    {m['initialized']}",
            f"  Certificates:      {m['total_certificates']}",
            f"  Issued:            {m['certificates_issued']}",
            f"  Revoked:           {m['certificates_revoked']}",
            f"  CRL Entries:       {m['crl_entries']}",
        ]
        chain = self._ca.get_chain()
        if chain:
            lines.append(f"\n  Certificate Chain")
            lines.append(f"  {'─' * (self._width - 4)}")
            for cert in chain:
                lines.append(f"  {cert.subject_cn} (CA={cert.basic_constraints_ca})")
        return "\n".join(lines)


# ============================================================
# Middleware
# ============================================================

class FizzPKIMiddleware(IMiddleware):
    """Middleware integration for FizzPKI."""

    def __init__(self, ca: Optional[CertificateAuthority] = None,
                 dashboard: Optional[FizzPKIDashboard] = None,
                 config: Optional[FizzPKIConfig] = None) -> None:
        self._ca = ca
        self._dashboard = dashboard
        self._config = config or FizzPKIConfig()

    def get_name(self) -> str:
        return "fizzpki"

    def get_priority(self) -> int:
        return MIDDLEWARE_PRIORITY

    def process(self, context: ProcessingContext, next_handler: Any) -> ProcessingContext:
        if self._ca:
            m = self._ca.get_metrics()
            context.metadata["fizzpki_version"] = FIZZPKI_VERSION
            context.metadata["fizzpki_initialized"] = m["initialized"]
            context.metadata["fizzpki_issued"] = m["certificates_issued"]
        if next_handler is not None:
            return next_handler(context)
        return context

    def render_dashboard(self) -> str:
        if self._dashboard:
            return self._dashboard.render()
        return "FizzPKI not initialized"

    def render_status(self) -> str:
        if self._ca:
            m = self._ca.get_metrics()
            return (f"FizzPKI {FIZZPKI_VERSION} | Certs: {m['total_certificates']} | "
                    f"Issued: {m['certificates_issued']} | Revoked: {m['certificates_revoked']}")
        return f"FizzPKI {FIZZPKI_VERSION} | Not initialized"

    def render_list(self) -> str:
        if not self._ca:
            return "No CA"
        lines = ["FizzPKI Certificates:"]
        for serial, cert in self._ca.certificate_store.items():
            lines.append(f"  {serial[:16]} {cert.subject_cn:<30} {cert.status.name}")
        return "\n".join(lines)

    def render_inventory(self) -> str:
        return self.render_list()

    def render_transparency(self) -> str:
        return "FizzPKI Transparency Log"


# ============================================================
# Factory
# ============================================================

def create_fizzpki_subsystem(
    cert_validity_days: int = DEFAULT_CERT_VALIDITY_DAYS,
    acme_enabled: bool = True,
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[CertificateAuthority, ACMEServer, FizzPKIDashboard, FizzPKIMiddleware]:
    config = FizzPKIConfig(cert_validity_days=cert_validity_days,
                           acme_enabled=acme_enabled, dashboard_width=dashboard_width)
    ca = CertificateAuthority(config)
    ca.initialize()

    acme = ACMEServer(config)
    acme.set_ca(ca)

    dashboard = FizzPKIDashboard(ca, dashboard_width)
    middleware = FizzPKIMiddleware(ca, dashboard, config)

    logger.info("FizzPKI initialized: CA ready, ACME=%s", acme_enabled)
    return ca, acme, dashboard, middleware
