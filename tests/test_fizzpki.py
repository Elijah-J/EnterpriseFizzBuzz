"""
Enterprise FizzBuzz Platform - FizzPKI Test Suite

Comprehensive tests for the Public Key Infrastructure and Certificate
Authority subsystem. A production FizzBuzz platform requires cryptographic
identity verification to ensure that when a number claims to be divisible
by 3, that claim is backed by a signed certificate from a trusted authority.
Without PKI, any integer could impersonate a Fizz.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta

import pytest

from enterprise_fizzbuzz.domain.models import ProcessingContext
from enterprise_fizzbuzz.infrastructure.fizzpki import (
    FIZZPKI_VERSION,
    MIDDLEWARE_PRIORITY,
    KeyAlgorithm,
    CertificateStatus,
    RevocationReason,
    ACMEOrderStatus,
    ACMEChallengeType,
    ACMEChallengeStatus,
    OCSPResponseStatus,
    FizzPKIConfig,
    KeyPair,
    X509Certificate,
    CertificateSigningRequest,
    CRLDocument,
    CRLEntry,
    OCSPRequest,
    OCSPResponse,
    ACMEAccount,
    ACMEOrder,
    ACMEChallenge,
    TransparencyLogEntry,
    KeyGenerator,
    X509CertificateBuilder,
    CSRProcessor,
    CertificateAuthority,
    CRLGenerator,
    OCSPResponder,
    ACMEServer,
    TransparencyLog,
    RenewalTracker,
    FizzPKIDashboard,
    FizzPKIMiddleware,
    create_fizzpki_subsystem,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config():
    """Default FizzPKI configuration for testing."""
    return FizzPKIConfig()


@pytest.fixture
def key_generator():
    return KeyGenerator()


@pytest.fixture
def rsa_key_pair(key_generator):
    return key_generator.generate(KeyAlgorithm.RSA_2048)


@pytest.fixture
def ecdsa_key_pair(key_generator):
    return key_generator.generate(KeyAlgorithm.ECDSA_P256)


@pytest.fixture
def builder():
    return X509CertificateBuilder()


@pytest.fixture
def csr_processor():
    return CSRProcessor()


@pytest.fixture
def root_cert_and_key(config, rsa_key_pair, builder):
    cert = builder.build_root_ca(config, rsa_key_pair)
    return cert, rsa_key_pair


@pytest.fixture
def ca(config):
    ca = CertificateAuthority(config)
    ca.initialize()
    return ca


@pytest.fixture
def crl_generator():
    return CRLGenerator()


@pytest.fixture
def ocsp_responder():
    return OCSPResponder()


@pytest.fixture
def acme_server(config):
    return ACMEServer(config)


@pytest.fixture
def transparency_log():
    return TransparencyLog()


# ---------------------------------------------------------------------------
# TestConstants
# ---------------------------------------------------------------------------


class TestConstants:
    """Verify module-level constants are correctly defined."""

    def test_version_string(self):
        assert FIZZPKI_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 134


# ---------------------------------------------------------------------------
# TestKeyGenerator
# ---------------------------------------------------------------------------


class TestKeyGenerator:
    """Key generation for all supported algorithms."""

    def test_generate_rsa_2048(self, key_generator):
        kp = key_generator.generate(KeyAlgorithm.RSA_2048)
        assert isinstance(kp, KeyPair)
        assert kp.algorithm == KeyAlgorithm.RSA_2048
        assert isinstance(kp.public_key_pem, bytes)
        assert isinstance(kp.private_key_pem, bytes)
        assert b"PUBLIC KEY" in kp.public_key_pem
        assert b"PRIVATE KEY" in kp.private_key_pem

    def test_generate_rsa_4096(self, key_generator):
        kp = key_generator.generate(KeyAlgorithm.RSA_4096)
        assert kp.algorithm == KeyAlgorithm.RSA_4096
        assert len(kp.public_key_pem) > 0
        assert len(kp.private_key_pem) > 0

    def test_generate_ecdsa_p256(self, key_generator):
        kp = key_generator.generate(KeyAlgorithm.ECDSA_P256)
        assert kp.algorithm == KeyAlgorithm.ECDSA_P256
        assert isinstance(kp.fingerprint, str)
        assert len(kp.fingerprint) > 0

    def test_generate_ecdsa_p384(self, key_generator):
        kp = key_generator.generate(KeyAlgorithm.ECDSA_P384)
        assert kp.algorithm == KeyAlgorithm.ECDSA_P384

    def test_unique_fingerprints(self, key_generator):
        kp1 = key_generator.generate(KeyAlgorithm.RSA_2048)
        kp2 = key_generator.generate(KeyAlgorithm.RSA_2048)
        assert kp1.fingerprint != kp2.fingerprint

    def test_unique_key_material(self, key_generator):
        kp1 = key_generator.generate(KeyAlgorithm.ECDSA_P256)
        kp2 = key_generator.generate(KeyAlgorithm.ECDSA_P256)
        assert kp1.private_key_pem != kp2.private_key_pem


# ---------------------------------------------------------------------------
# TestX509CertificateBuilder
# ---------------------------------------------------------------------------


class TestX509CertificateBuilder:
    """Certificate construction for root, intermediate, and end-entity."""

    def test_build_root_ca(self, builder, config, rsa_key_pair):
        cert = builder.build_root_ca(config, rsa_key_pair)
        assert isinstance(cert, X509Certificate)
        assert cert.basic_constraints_ca is True
        assert cert.status == CertificateStatus.VALID
        assert cert.issuer_cn == cert.subject_cn  # self-signed
        assert isinstance(cert.certificate_pem, bytes)
        assert len(cert.serial_number) > 0

    def test_build_intermediate_ca(self, builder, config, root_cert_and_key):
        root_cert, root_key = root_cert_and_key
        inter_key = KeyGenerator().generate(KeyAlgorithm.RSA_2048)
        inter_cert = builder.build_intermediate_ca(config, inter_key, root_cert, root_key)
        assert inter_cert.basic_constraints_ca is True
        assert inter_cert.issuer_cn == root_cert.subject_cn
        assert inter_cert.subject_cn != root_cert.subject_cn

    def test_build_end_entity(self, builder, config, root_cert_and_key, csr_processor, rsa_key_pair):
        root_cert, root_key = root_cert_and_key
        csr = csr_processor.create_csr("fizzbuzz.example.com", ["fizzbuzz.example.com"], rsa_key_pair)
        cert = builder.build_end_entity(csr, root_cert, root_key, validity_days=365)
        assert cert.basic_constraints_ca is False
        assert cert.subject_cn == "fizzbuzz.example.com"
        assert cert.issuer_cn == root_cert.subject_cn
        assert cert.not_before <= datetime.utcnow()
        assert cert.not_after > datetime.utcnow()

    def test_certificate_validity_window(self, builder, config, root_cert_and_key, csr_processor, rsa_key_pair):
        root_cert, root_key = root_cert_and_key
        csr = csr_processor.create_csr("test.example.com", ["test.example.com"], rsa_key_pair)
        cert = builder.build_end_entity(csr, root_cert, root_key, validity_days=30)
        delta = cert.not_after - cert.not_before
        assert 29 <= delta.days <= 31


# ---------------------------------------------------------------------------
# TestCSRProcessor
# ---------------------------------------------------------------------------


class TestCSRProcessor:
    """Certificate Signing Request creation and validation."""

    def test_create_csr(self, csr_processor, rsa_key_pair):
        csr = csr_processor.create_csr(
            "fizzbuzz.enterprise.local",
            ["fizzbuzz.enterprise.local", "*.fizzbuzz.enterprise.local"],
            rsa_key_pair,
        )
        assert isinstance(csr, CertificateSigningRequest)
        assert csr.subject_cn == "fizzbuzz.enterprise.local"
        assert "*.fizzbuzz.enterprise.local" in csr.subject_alt_names
        assert isinstance(csr.csr_pem, bytes)
        assert len(csr.csr_pem) > 0

    def test_validate_csr_accepts_valid(self, csr_processor, rsa_key_pair):
        csr = csr_processor.create_csr("valid.example.com", ["valid.example.com"], rsa_key_pair)
        assert csr_processor.validate_csr(csr) is True

    def test_csr_subject_alt_names_preserved(self, csr_processor, ecdsa_key_pair):
        sans = ["a.example.com", "b.example.com", "c.example.com"]
        csr = csr_processor.create_csr("a.example.com", sans, ecdsa_key_pair)
        assert set(sans).issubset(set(csr.subject_alt_names))


# ---------------------------------------------------------------------------
# TestCertificateAuthority
# ---------------------------------------------------------------------------


class TestCertificateAuthority:
    """Full CA lifecycle: initialize, issue, revoke, query."""

    def test_initialize(self, config):
        ca = CertificateAuthority(config)
        assert ca.is_initialized() is False
        ca.initialize()
        assert ca.is_initialized() is True

    def test_issue_certificate(self, ca, csr_processor, rsa_key_pair):
        csr = csr_processor.create_csr("service.fizz.local", ["service.fizz.local"], rsa_key_pair)
        cert = ca.issue_certificate(csr, validity_days=365)
        assert isinstance(cert, X509Certificate)
        assert cert.subject_cn == "service.fizz.local"
        assert cert.status == CertificateStatus.VALID

    def test_get_certificate_by_serial(self, ca, csr_processor, rsa_key_pair):
        csr = csr_processor.create_csr("lookup.fizz.local", ["lookup.fizz.local"], rsa_key_pair)
        issued = ca.issue_certificate(csr, validity_days=90)
        retrieved = ca.get_certificate(issued.serial_number)
        assert retrieved.serial_number == issued.serial_number
        assert retrieved.subject_cn == "lookup.fizz.local"

    def test_revoke_certificate(self, ca, csr_processor, rsa_key_pair):
        csr = csr_processor.create_csr("revokeme.fizz.local", ["revokeme.fizz.local"], rsa_key_pair)
        cert = ca.issue_certificate(csr, validity_days=365)
        ca.revoke_certificate(cert.serial_number, RevocationReason.KEY_COMPROMISE)
        revoked = ca.get_certificate(cert.serial_number)
        assert revoked.status == CertificateStatus.REVOKED

    def test_get_chain_includes_root(self, ca):
        chain = ca.get_chain()
        assert isinstance(chain, list)
        assert len(chain) >= 1
        root = chain[-1]
        assert root.basic_constraints_ca is True

    def test_get_metrics(self, ca, csr_processor, rsa_key_pair):
        csr = csr_processor.create_csr("metrics.fizz.local", ["metrics.fizz.local"], rsa_key_pair)
        ca.issue_certificate(csr, validity_days=30)
        metrics = ca.get_metrics()
        assert metrics["certificates_issued"] >= 1

    def test_multiple_certificates_unique_serials(self, ca, csr_processor, rsa_key_pair):
        serials = set()
        for i in range(5):
            csr = csr_processor.create_csr(f"node{i}.fizz.local", [f"node{i}.fizz.local"], rsa_key_pair)
            cert = ca.issue_certificate(csr, validity_days=365)
            serials.add(cert.serial_number)
        assert len(serials) == 5


# ---------------------------------------------------------------------------
# TestCRLGenerator
# ---------------------------------------------------------------------------


class TestCRLGenerator:
    """Certificate Revocation List generation and queries."""

    def test_generate_crl(self, crl_generator, ca, csr_processor, rsa_key_pair):
        csr = csr_processor.create_csr("crl-test.fizz.local", ["crl-test.fizz.local"], rsa_key_pair)
        cert = ca.issue_certificate(csr, validity_days=365)
        ca.revoke_certificate(cert.serial_number, RevocationReason.KEY_COMPROMISE)
        crl = crl_generator.generate(ca)
        assert isinstance(crl, CRLDocument)
        assert len(crl.entries) >= 1
        revoked_serials = [e.serial_number for e in crl.entries]
        assert cert.serial_number in revoked_serials

    def test_is_revoked_true(self, crl_generator, ca, csr_processor, rsa_key_pair):
        csr = csr_processor.create_csr("revoked.fizz.local", ["revoked.fizz.local"], rsa_key_pair)
        cert = ca.issue_certificate(csr, validity_days=365)
        ca.revoke_certificate(cert.serial_number, RevocationReason.CESSATION_OF_OPERATION)
        crl = crl_generator.generate(ca)
        assert crl_generator.is_revoked(cert.serial_number, crl) is True

    def test_is_revoked_false(self, crl_generator, ca, csr_processor, rsa_key_pair):
        csr = csr_processor.create_csr("active.fizz.local", ["active.fizz.local"], rsa_key_pair)
        cert = ca.issue_certificate(csr, validity_days=365)
        crl = crl_generator.generate(ca)
        assert crl_generator.is_revoked(cert.serial_number, crl) is False

    def test_crl_metadata(self, crl_generator, ca):
        crl = crl_generator.generate(ca)
        assert crl.this_update is not None
        assert crl.next_update is not None
        assert crl.next_update > crl.this_update
        assert isinstance(crl.crl_number, int)


# ---------------------------------------------------------------------------
# TestOCSPResponder
# ---------------------------------------------------------------------------


class TestOCSPResponder:
    """Online Certificate Status Protocol responder."""

    def test_good_status(self, ocsp_responder, ca, csr_processor, rsa_key_pair):
        csr = csr_processor.create_csr("ocsp-good.fizz.local", ["ocsp-good.fizz.local"], rsa_key_pair)
        cert = ca.issue_certificate(csr, validity_days=365)
        req = OCSPRequest(serial_number=cert.serial_number, issuer_cn=cert.issuer_cn)
        resp = ocsp_responder.handle_request(req, ca)
        assert isinstance(resp, OCSPResponse)
        assert resp.status == OCSPResponseStatus.GOOD
        assert resp.serial_number == cert.serial_number

    def test_revoked_status(self, ocsp_responder, ca, csr_processor, rsa_key_pair):
        csr = csr_processor.create_csr("ocsp-rev.fizz.local", ["ocsp-rev.fizz.local"], rsa_key_pair)
        cert = ca.issue_certificate(csr, validity_days=365)
        ca.revoke_certificate(cert.serial_number, RevocationReason.KEY_COMPROMISE)
        req = OCSPRequest(serial_number=cert.serial_number, issuer_cn=cert.issuer_cn)
        resp = ocsp_responder.handle_request(req, ca)
        assert resp.status == OCSPResponseStatus.REVOKED

    def test_unknown_serial(self, ocsp_responder, ca):
        req = OCSPRequest(serial_number="nonexistent-serial-999", issuer_cn="unknown")
        resp = ocsp_responder.handle_request(req, ca)
        assert resp.status == OCSPResponseStatus.UNKNOWN

    def test_query_count_increments(self, ocsp_responder, ca, csr_processor, rsa_key_pair):
        initial = ocsp_responder.get_query_count()
        csr = csr_processor.create_csr("count.fizz.local", ["count.fizz.local"], rsa_key_pair)
        cert = ca.issue_certificate(csr, validity_days=365)
        req = OCSPRequest(serial_number=cert.serial_number, issuer_cn=cert.issuer_cn)
        ocsp_responder.handle_request(req, ca)
        ocsp_responder.handle_request(req, ca)
        assert ocsp_responder.get_query_count() == initial + 2


# ---------------------------------------------------------------------------
# TestACMEServer
# ---------------------------------------------------------------------------


class TestACMEServer:
    """ACME protocol server for automated certificate lifecycle."""

    def test_create_account(self, acme_server):
        acct = acme_server.create_account("admin@fizzbuzz.enterprise")
        assert isinstance(acct, ACMEAccount)
        assert acct.contact_email == "admin@fizzbuzz.enterprise"
        assert len(acct.account_id) > 0

    def test_create_order(self, acme_server):
        acct = acme_server.create_account("order@fizzbuzz.enterprise")
        order = acme_server.create_order(acct.account_id, ["fizzbuzz.example.com"])
        assert isinstance(order, ACMEOrder)
        assert order.status == ACMEOrderStatus.PENDING
        assert "fizzbuzz.example.com" in order.identifiers

    def test_get_challenge(self, acme_server):
        acct = acme_server.create_account("challenge@fizzbuzz.enterprise")
        order = acme_server.create_order(acct.account_id, ["challenge.example.com"])
        challenge = acme_server.get_challenge(order.order_id)
        assert isinstance(challenge, ACMEChallenge)
        assert len(challenge.token) > 0
        assert challenge.status == ACMEChallengeStatus.PENDING

    def test_validate_challenge(self, acme_server):
        acct = acme_server.create_account("validate@fizzbuzz.enterprise")
        order = acme_server.create_order(acct.account_id, ["validate.example.com"])
        challenge = acme_server.get_challenge(order.order_id)
        result = acme_server.validate_challenge(challenge.challenge_id, challenge.key_authorization)
        assert result is True

    def test_finalize_order(self, acme_server, csr_processor):
        acct = acme_server.create_account("finalize@fizzbuzz.enterprise")
        order = acme_server.create_order(acct.account_id, ["finalize.example.com"])
        challenge = acme_server.get_challenge(order.order_id)
        acme_server.validate_challenge(challenge.challenge_id, challenge.key_authorization)
        kg = KeyGenerator()
        kp = kg.generate(KeyAlgorithm.RSA_2048)
        csr = csr_processor.create_csr("finalize.example.com", ["finalize.example.com"], kp)
        cert = acme_server.finalize_order(order.order_id, csr)
        assert isinstance(cert, X509Certificate)
        assert cert.subject_cn == "finalize.example.com"
        assert cert.status == CertificateStatus.VALID

    def test_get_directory(self, acme_server):
        directory = acme_server.get_directory()
        assert isinstance(directory, dict)
        assert "newAccount" in directory
        assert "newOrder" in directory


# ---------------------------------------------------------------------------
# TestTransparencyLog
# ---------------------------------------------------------------------------


class TestTransparencyLog:
    """Certificate Transparency log for audit trail."""

    def test_append_and_retrieve(self, transparency_log, ca, csr_processor, rsa_key_pair):
        csr = csr_processor.create_csr("ct.fizz.local", ["ct.fizz.local"], rsa_key_pair)
        cert = ca.issue_certificate(csr, validity_days=365)
        entry = transparency_log.append(cert)
        assert isinstance(entry, TransparencyLogEntry)
        assert entry.certificate_serial == cert.serial_number
        assert isinstance(entry.merkle_hash, str)
        assert len(entry.merkle_hash) > 0
        retrieved = transparency_log.get_entry(entry.log_index)
        assert retrieved.certificate_serial == cert.serial_number

    def test_log_size_grows(self, transparency_log, ca, csr_processor, rsa_key_pair):
        initial = transparency_log.get_log_size()
        for i in range(3):
            csr = csr_processor.create_csr(f"ct{i}.fizz.local", [f"ct{i}.fizz.local"], rsa_key_pair)
            cert = ca.issue_certificate(csr, validity_days=365)
            transparency_log.append(cert)
        assert transparency_log.get_log_size() == initial + 3

    def test_unique_merkle_hashes(self, transparency_log, ca, csr_processor, rsa_key_pair):
        hashes = set()
        for i in range(3):
            csr = csr_processor.create_csr(f"hash{i}.fizz.local", [f"hash{i}.fizz.local"], rsa_key_pair)
            cert = ca.issue_certificate(csr, validity_days=365)
            entry = transparency_log.append(cert)
            hashes.add(entry.merkle_hash)
        assert len(hashes) == 3


# ---------------------------------------------------------------------------
# TestRenewalTracker
# ---------------------------------------------------------------------------


class TestRenewalTracker:
    """Renewal scanning for certificates approaching expiration."""

    def test_scan_finds_expiring_certs(self, ca, csr_processor, rsa_key_pair):
        csr = csr_processor.create_csr("shortlived.fizz.local", ["shortlived.fizz.local"], rsa_key_pair)
        ca.issue_certificate(csr, validity_days=1)
        tracker = RenewalTracker(renewal_window_days=30)
        pending = tracker.scan(ca)
        assert isinstance(pending, list)
        assert len(pending) >= 1

    def test_get_pending_count(self, ca, csr_processor, rsa_key_pair):
        csr = csr_processor.create_csr("expiring.fizz.local", ["expiring.fizz.local"], rsa_key_pair)
        ca.issue_certificate(csr, validity_days=1)
        tracker = RenewalTracker(renewal_window_days=30)
        tracker.scan(ca)
        assert tracker.get_pending_count() >= 1


# ---------------------------------------------------------------------------
# TestFizzPKIDashboard
# ---------------------------------------------------------------------------


class TestFizzPKIDashboard:
    """Dashboard rendering for PKI operational overview."""

    def test_render_returns_string(self, ca):
        dashboard = FizzPKIDashboard(ca)
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_contains_status_info(self, ca, csr_processor, rsa_key_pair):
        csr = csr_processor.create_csr("dash.fizz.local", ["dash.fizz.local"], rsa_key_pair)
        ca.issue_certificate(csr, validity_days=365)
        dashboard = FizzPKIDashboard(ca)
        output = dashboard.render()
        assert "certificate" in output.lower() or "cert" in output.lower()


# ---------------------------------------------------------------------------
# TestFizzPKIMiddleware
# ---------------------------------------------------------------------------


class TestFizzPKIMiddleware:
    """Middleware integration into the FizzBuzz processing pipeline."""

    def test_get_name(self):
        mw = FizzPKIMiddleware()
        assert mw.get_name() == "fizzpki"

    def test_get_priority(self):
        mw = FizzPKIMiddleware()
        assert mw.get_priority() == 134

    def test_process_calls_next_handler(self):
        mw = FizzPKIMiddleware()
        called = []

        def next_handler(ctx):
            called.append(True)
            return ctx

        ctx = ProcessingContext(number=15, session_id="test-session")
        mw.process(ctx, next_handler)
        assert len(called) == 1


# ---------------------------------------------------------------------------
# TestCreateSubsystem
# ---------------------------------------------------------------------------


class TestCreateSubsystem:
    """Factory function wiring all PKI components together."""

    def test_returns_tuple_of_four(self):
        result = create_fizzpki_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 4

    def test_component_types(self):
        ca, acme, dashboard, middleware = create_fizzpki_subsystem()
        assert isinstance(ca, CertificateAuthority)
        assert isinstance(acme, ACMEServer)
        assert isinstance(dashboard, FizzPKIDashboard)
        assert isinstance(middleware, FizzPKIMiddleware)

    def test_ca_is_initialized(self):
        ca, _, _, _ = create_fizzpki_subsystem()
        assert ca.is_initialized() is True
