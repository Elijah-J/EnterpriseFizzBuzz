"""
Enterprise FizzBuzz Platform - FizzMail Email Server Errors (EFP-MAIL00 .. EFP-MAIL35)

Exception hierarchy for the FizzMail SMTP/IMAP email server.
Covers SMTP command processing, TLS negotiation, authentication,
envelope parsing, MIME construction, message queuing, relay routing,
SPF/DKIM/DMARC validation, greylisting, RBL checking, bounce handling,
IMAP state management, mailbox operations, FETCH processing, SEARCH
evaluation, flag manipulation, quota enforcement, and UID consistency.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class FizzMailError(FizzBuzzError):
    """Base exception for all FizzMail email server errors.

    FizzMail is the platform's SMTP and IMAP email server that accepts
    inbound mail, validates sender authentication (SPF/DKIM/DMARC),
    queues outbound delivery, and provides IMAP mailbox access.  All
    mail-specific failures inherit from this class to enable categorical
    error handling in the middleware pipeline.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzMail error: {reason}",
            error_code="EFP-MAIL00",
            context={"reason": reason},
        )


class FizzMailSMTPError(FizzMailError):
    """Raised on SMTP protocol-level errors.

    Covers malformed commands, unexpected sequences, and violations of
    the SMTP state machine defined in RFC 5321.
    """

    def __init__(self, command: str, reason: str) -> None:
        super().__init__(f"SMTP error on {command}: {reason}")
        self.error_code = "EFP-MAIL01"
        self.context = {"command": command, "reason": reason}


class FizzMailIMAPError(FizzMailError):
    """Raised on IMAP protocol-level errors.

    Covers malformed commands, unexpected sequences, and violations of
    the IMAP state machine defined in RFC 3501.
    """

    def __init__(self, command: str, reason: str) -> None:
        super().__init__(f"IMAP error on {command}: {reason}")
        self.error_code = "EFP-MAIL02"
        self.context = {"command": command, "reason": reason}


class FizzMailTLSError(FizzMailError):
    """Raised when STARTTLS negotiation fails.

    Covers handshake failures, cipher suite mismatches, and certificate
    validation errors during the TLS upgrade sequence.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"TLS negotiation failed: {reason}")
        self.error_code = "EFP-MAIL03"
        self.context = {"reason": reason}


class FizzMailAuthError(FizzMailError):
    """Raised when SMTP or IMAP authentication fails.

    Covers invalid credentials, unsupported mechanisms, and
    authentication protocol violations.
    """

    def __init__(self, mechanism: str, reason: str) -> None:
        super().__init__(f"Authentication failed ({mechanism}): {reason}")
        self.error_code = "EFP-MAIL04"
        self.context = {"mechanism": mechanism, "reason": reason}


class FizzMailEnvelopeError(FizzMailError):
    """Raised when MAIL FROM or RCPT TO parsing fails.

    Covers malformed addresses, missing angle brackets, and invalid
    extension parameters in the SMTP envelope commands.
    """

    def __init__(self, command: str, reason: str) -> None:
        super().__init__(f"Envelope error in {command}: {reason}")
        self.error_code = "EFP-MAIL05"
        self.context = {"command": command, "reason": reason}


class FizzMailDataError(FizzMailError):
    """Raised during the DATA phase of SMTP message reception.

    Covers premature disconnection, dot-stuffing violations, and
    failures in the DATA command processing pipeline.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"DATA phase error: {reason}")
        self.error_code = "EFP-MAIL06"
        self.context = {"reason": reason}


class FizzMailSizeLimitError(FizzMailError):
    """Raised when a message exceeds the configured size limit.

    The SMTP server enforces a maximum message size to prevent resource
    exhaustion.  Messages exceeding this limit are rejected with a 552
    response code.
    """

    def __init__(self, size: int, limit: int) -> None:
        super().__init__(f"Message size {size} exceeds limit {limit}")
        self.error_code = "EFP-MAIL07"
        self.context = {"size": size, "limit": limit}


class FizzMailHeaderParseError(FizzMailError):
    """Raised when RFC 5322 header parsing fails.

    Covers malformed header field names, invalid structured header
    syntax (addresses, dates), and encoding errors in header values.
    """

    def __init__(self, header: str, reason: str) -> None:
        super().__init__(f"Header parse error in '{header}': {reason}")
        self.error_code = "EFP-MAIL08"
        self.context = {"header": header, "reason": reason}


class FizzMailMIMEError(FizzMailError):
    """Raised on MIME construction or parsing failures.

    Covers invalid content types, malformed multipart boundaries,
    and encoding/decoding errors in MIME message bodies.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"MIME error: {reason}")
        self.error_code = "EFP-MAIL09"
        self.context = {"reason": reason}


class FizzMailMIMEBoundaryError(FizzMailError):
    """Raised when a MIME boundary conflict is detected.

    The randomly generated boundary string must not appear in the
    message content.  This exception signals that the boundary
    generation algorithm produced a collision.
    """

    def __init__(self, boundary: str) -> None:
        super().__init__(f"MIME boundary collision: {boundary}")
        self.error_code = "EFP-MAIL10"
        self.context = {"boundary": boundary}


class FizzMailEncodingError(FizzMailError):
    """Raised on base64 or quoted-printable encoding/decoding failures.

    Covers invalid base64 padding, illegal quoted-printable sequences,
    and charset conversion errors.
    """

    def __init__(self, encoding: str, reason: str) -> None:
        super().__init__(f"Encoding error ({encoding}): {reason}")
        self.error_code = "EFP-MAIL11"
        self.context = {"encoding": encoding, "reason": reason}


class FizzMailQueueError(FizzMailError):
    """Raised on message queue operation failures.

    Covers queue insertion failures, status transition violations,
    and queue capacity exhaustion.
    """

    def __init__(self, message_id: str, reason: str) -> None:
        super().__init__(f"Queue error for message {message_id}: {reason}")
        self.error_code = "EFP-MAIL12"
        self.context = {"message_id": message_id, "reason": reason}


class FizzMailRetryExhaustedError(FizzMailError):
    """Raised when a message exhausts its maximum delivery retry count.

    After the configured number of delivery attempts with exponential
    backoff, the message is declared permanently undeliverable and a
    DSN bounce is generated.
    """

    def __init__(self, message_id: str, attempts: int) -> None:
        super().__init__(f"Retry exhausted for {message_id} after {attempts} attempts")
        self.error_code = "EFP-MAIL13"
        self.context = {"message_id": message_id, "attempts": attempts}


class FizzMailRelayError(FizzMailError):
    """Raised when outbound relay delivery fails.

    Covers connection failures to the target MTA, SMTP error responses
    from the remote server, and smart host routing failures.
    """

    def __init__(self, recipient: str, reason: str) -> None:
        super().__init__(f"Relay failed for {recipient}: {reason}")
        self.error_code = "EFP-MAIL14"
        self.context = {"recipient": recipient, "reason": reason}


class FizzMailMXLookupError(FizzMailError):
    """Raised when MX record resolution fails for a recipient domain.

    The relay router queries FizzDNS for MX records to determine the
    target MTA.  This exception covers DNS resolution failures and
    domains with no MX records.
    """

    def __init__(self, domain: str, reason: str) -> None:
        super().__init__(f"MX lookup failed for {domain}: {reason}")
        self.error_code = "EFP-MAIL15"
        self.context = {"domain": domain, "reason": reason}


class FizzMailSPFError(FizzMailError):
    """Raised on SPF validation errors.

    Covers DNS lookup failures for SPF records, syntax errors in SPF
    policy strings, and mechanism evaluation failures.
    """

    def __init__(self, domain: str, reason: str) -> None:
        super().__init__(f"SPF error for {domain}: {reason}")
        self.error_code = "EFP-MAIL16"
        self.context = {"domain": domain, "reason": reason}


class FizzMailSPFPermError(FizzMailError):
    """Raised on permanent SPF evaluation errors.

    Permanent errors indicate that the SPF record is syntactically
    invalid and cannot be evaluated regardless of retry attempts.
    """

    def __init__(self, domain: str, reason: str) -> None:
        super().__init__(f"SPF permanent error for {domain}: {reason}")
        self.error_code = "EFP-MAIL17"
        self.context = {"domain": domain, "reason": reason}


class FizzMailSPFTempError(FizzMailError):
    """Raised on temporary SPF evaluation errors.

    Temporary errors indicate transient DNS failures that may resolve
    on retry.  The message should be deferred rather than rejected.
    """

    def __init__(self, domain: str, reason: str) -> None:
        super().__init__(f"SPF temporary error for {domain}: {reason}")
        self.error_code = "EFP-MAIL18"
        self.context = {"domain": domain, "reason": reason}


class FizzMailDKIMError(FizzMailError):
    """Raised on DKIM signing or verification failures.

    Covers key generation errors, canonicalization failures, and
    signature computation errors.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"DKIM error: {reason}")
        self.error_code = "EFP-MAIL19"
        self.context = {"reason": reason}


class FizzMailDKIMSignatureError(FizzMailError):
    """Raised when a DKIM signature fails verification.

    The signature in the DKIM-Signature header does not match the
    computed hash of the canonicalized headers and body.
    """

    def __init__(self, domain: str, selector: str, reason: str) -> None:
        super().__init__(f"DKIM signature invalid for {selector}._domainkey.{domain}: {reason}")
        self.error_code = "EFP-MAIL20"
        self.context = {"domain": domain, "selector": selector, "reason": reason}


class FizzMailDKIMKeyError(FizzMailError):
    """Raised when DKIM public key lookup fails.

    The selector-based DNS query for the DKIM public key returned no
    result or an unparseable TXT record.
    """

    def __init__(self, domain: str, selector: str) -> None:
        super().__init__(f"DKIM key not found: {selector}._domainkey.{domain}")
        self.error_code = "EFP-MAIL21"
        self.context = {"domain": domain, "selector": selector}


class FizzMailDMARCError(FizzMailError):
    """Raised on DMARC evaluation failures.

    Covers DNS lookup failures for DMARC records, policy parsing
    errors, and alignment evaluation failures.
    """

    def __init__(self, domain: str, reason: str) -> None:
        super().__init__(f"DMARC error for {domain}: {reason}")
        self.error_code = "EFP-MAIL22"
        self.context = {"domain": domain, "reason": reason}


class FizzMailGreylistError(FizzMailError):
    """Raised on greylisting subsystem failures.

    Covers triplet storage errors and auto-whitelist computation
    failures.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Greylisting error: {reason}")
        self.error_code = "EFP-MAIL23"
        self.context = {"reason": reason}


class FizzMailRBLError(FizzMailError):
    """Raised on DNSBL/RBL query failures.

    Covers DNS resolution errors when querying real-time blocklists
    and result interpretation failures.
    """

    def __init__(self, zone: str, ip: str, reason: str) -> None:
        super().__init__(f"RBL query failed for {ip} against {zone}: {reason}")
        self.error_code = "EFP-MAIL24"
        self.context = {"zone": zone, "ip": ip, "reason": reason}


class FizzMailBounceError(FizzMailError):
    """Raised when DSN bounce generation fails.

    Covers failures in constructing the multipart/report DSN message
    per RFC 3464.
    """

    def __init__(self, message_id: str, reason: str) -> None:
        super().__init__(f"Bounce generation failed for {message_id}: {reason}")
        self.error_code = "EFP-MAIL25"
        self.context = {"message_id": message_id, "reason": reason}


class FizzMailIMAPStateError(FizzMailError):
    """Raised on invalid IMAP state transitions.

    The IMAP protocol defines strict state transitions (not_authenticated,
    authenticated, selected, logout).  Commands issued in an invalid
    state trigger this exception.
    """

    def __init__(self, current_state: str, command: str) -> None:
        super().__init__(f"Invalid IMAP command {command} in state {current_state}")
        self.error_code = "EFP-MAIL26"
        self.context = {"current_state": current_state, "command": command}


class FizzMailMailboxError(FizzMailError):
    """Raised on mailbox operation failures.

    Covers creation, deletion, renaming, and subscription errors
    for IMAP mailboxes.
    """

    def __init__(self, mailbox: str, reason: str) -> None:
        super().__init__(f"Mailbox error for '{mailbox}': {reason}")
        self.error_code = "EFP-MAIL27"
        self.context = {"mailbox": mailbox, "reason": reason}


class FizzMailMailboxNotFoundError(FizzMailError):
    """Raised when a referenced mailbox does not exist.

    The IMAP SELECT, EXAMINE, STATUS, and COPY commands require the
    target mailbox to exist.
    """

    def __init__(self, mailbox: str) -> None:
        super().__init__(f"Mailbox not found: '{mailbox}'")
        self.error_code = "EFP-MAIL28"
        self.context = {"mailbox": mailbox}


class FizzMailMailboxExistsError(FizzMailError):
    """Raised when attempting to create a mailbox that already exists.

    The IMAP CREATE command requires the target mailbox name to be
    unique within the namespace.
    """

    def __init__(self, mailbox: str) -> None:
        super().__init__(f"Mailbox already exists: '{mailbox}'")
        self.error_code = "EFP-MAIL29"
        self.context = {"mailbox": mailbox}


class FizzMailFetchError(FizzMailError):
    """Raised when IMAP FETCH processing fails.

    Covers invalid data item specifiers, partial range errors, and
    BODYSTRUCTURE construction failures.
    """

    def __init__(self, data_item: str, reason: str) -> None:
        super().__init__(f"FETCH error for {data_item}: {reason}")
        self.error_code = "EFP-MAIL30"
        self.context = {"data_item": data_item, "reason": reason}


class FizzMailSearchError(FizzMailError):
    """Raised when IMAP SEARCH evaluation fails.

    Covers invalid search criteria, date parsing failures, and
    FizzSearch integration errors.
    """

    def __init__(self, criteria: str, reason: str) -> None:
        super().__init__(f"SEARCH error for '{criteria}': {reason}")
        self.error_code = "EFP-MAIL31"
        self.context = {"criteria": criteria, "reason": reason}


class FizzMailFlagError(FizzMailError):
    """Raised on IMAP flag manipulation failures.

    Covers invalid flag names, read-only mailbox violations, and
    permanent flag constraint violations.
    """

    def __init__(self, flag: str, reason: str) -> None:
        super().__init__(f"Flag error for '{flag}': {reason}")
        self.error_code = "EFP-MAIL32"
        self.context = {"flag": flag, "reason": reason}


class FizzMailQuotaError(FizzMailError):
    """Raised when a mailbox quota is exceeded.

    The storage quota system enforces per-mailbox size limits.
    Delivery attempts that would exceed the quota are rejected
    with SMTP 552 or IMAP NO responses.
    """

    def __init__(self, mailbox: str, usage: int, quota: int) -> None:
        super().__init__(f"Quota exceeded for '{mailbox}': {usage}/{quota} bytes")
        self.error_code = "EFP-MAIL33"
        self.context = {"mailbox": mailbox, "usage": usage, "quota": quota}


class FizzMailUIDError(FizzMailError):
    """Raised on UID consistency violations.

    UIDs must be strictly monotonically increasing within a mailbox.
    This exception covers UID generation failures and UIDVALIDITY
    mismatches.
    """

    def __init__(self, mailbox: str, reason: str) -> None:
        super().__init__(f"UID error in '{mailbox}': {reason}")
        self.error_code = "EFP-MAIL34"
        self.context = {"mailbox": mailbox, "reason": reason}


class FizzMailConfigError(FizzMailError):
    """Raised on FizzMail configuration errors.

    Covers invalid port numbers, missing required parameters, and
    conflicting configuration options.
    """

    def __init__(self, parameter: str, reason: str) -> None:
        super().__init__(f"Configuration error for '{parameter}': {reason}")
        self.error_code = "EFP-MAIL35"
        self.context = {"parameter": parameter, "reason": reason}
