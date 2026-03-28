# PLAN.md -- FizzPKI: Public Key Infrastructure & Certificate Authority

## Overview
Root/Intermediate CA hierarchy, X.509 certificate issuance (RSA/ECDSA), CSR processing, ACME server (RFC 8555) with http-01/dns-01 challenges, CRL generation, OCSP responder, certificate transparency log, automatic renewal tracking, and certificate inventory.

## TDD Order: Tests first, then implementation.

## Phases
1. Exceptions (EFP-PKI00..18), constants, enums, dataclasses
2. KeyGenerator, X509CertificateBuilder, CSRProcessor, CertificateAuthority
3. CRLGenerator, OCSPResponder, ACMEServer, TransparencyLog
4. RenewalTracker, Dashboard, Middleware, Factory

## Files
- enterprise_fizzbuzz/domain/exceptions/fizzpki.py
- enterprise_fizzbuzz/infrastructure/fizzpki.py (~1,000 lines)
- enterprise_fizzbuzz/infrastructure/config/mixins/fizzpki.py
- enterprise_fizzbuzz/infrastructure/features/fizzpki_feature.py
- fizzpki.py (stub)
- tests/test_fizzpki.py (~45 tests, written FIRST)

## CLI Flags (10)
--fizzpki, --fizzpki-issue, --fizzpki-revoke, --fizzpki-list, --fizzpki-crl, --fizzpki-ocsp, --fizzpki-acme, --fizzpki-renew, --fizzpki-inventory, --fizzpki-transparency
