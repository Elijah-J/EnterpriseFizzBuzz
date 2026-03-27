# PLAN.md -- FizzMail: SMTP/IMAP Email Server

## Overview

FizzMail is a complete SMTP (RFC 5321) and IMAP (RFC 3501) email server for the Enterprise FizzBuzz Platform. It fills the platform's most conspicuous communication gap: twelve existing subsystems generate notifications, alerts, invoices, and reports that terminate at webhook endpoints or log entries. FizzMail gives them a universal delivery channel.

The implementation follows the established infrastructure module pattern: a single `fizzmail.py` module (~4,000 lines), wired via `__main__.py`, with a test file `tests/test_fizzmail.py` (~600 tests).

---

## 1. Architecture

### 1.1 File Layout

| File | Purpose |
|---|---|
| `enterprise_fizzbuzz/infrastructure/fizzmail.py` | Main module (~4,000 lines) |
| `tests/test_fizzmail.py` | ~600 tests |

### 1.2 Integration Points

- **FizzDNS**: MX record lookup for relay routing, TXT record lookup for SPF/DKIM/DMARC
- **FizzSearch**: Full-text indexing of message bodies/headers for IMAP SEARCH
- **FizzPager/FizzApproval/FizzBill**: Notification delivery consumers
- **FizzVault**: DKIM private key storage
- **FizzCap**: Capability-based mailbox access control
- **FizzOTel**: Tracing spans for SMTP/IMAP operations

### 1.3 Module Internal Architecture

Following `fizzweb.py` pattern:
1. Constants block (version, defaults, ports, limits)
2. Enums (SMTPState, IMAPState, AuthMechanism, MIMEType, etc.)
3. Dataclasses (config, envelope, message, mailbox metadata, queue entries)
4. Core classes (parsers, validators, storage, servers)
5. Dashboard class (ASCII rendering)
6. Middleware class (IMiddleware implementation)
7. Factory function `create_fizzmail_subsystem()`

---

## 2. SMTP Server Components

### 2.1 SMTPServer
Top-level SMTP server class. Connection acceptance, TLS negotiation, command dispatch.

### 2.2 SMTP State Machine
```
CONNECTED -> (EHLO/HELO) -> GREETED -> (STARTTLS) -> TLS_NEGOTIATED -> (AUTH) -> AUTHENTICATED
GREETED/AUTHENTICATED -> (MAIL FROM) -> MAIL_FROM -> (RCPT TO) -> RCPT_TO -> (DATA) -> DATA -> (.) -> GREETED
Any state -> (QUIT) -> CLOSED
Any state -> (RSET) -> GREETED
```

### 2.3 STARTTLS
Simulated TLS negotiation (consistent with FizzWeb pattern). After upgrade, session resets, requires re-EHLO.

### 2.4 Authentication
Three mechanisms: PLAIN (base64), LOGIN (challenge/response), CRAM-MD5 (HMAC challenge).

### 2.5 Envelope Parsing
MAIL FROM/RCPT TO with extension parameters (SIZE, BODY=8BITMIME). Empty reverse-path for bounces.

### 2.6 DATA Handling
Dot-stuffing, size limits, Received header injection.

### 2.7 RFC 5322 Header Parsing
Structured headers (addresses, dates) and unstructured headers. Folding/unfolding. Encoded-word (RFC 2047).

### 2.8 MIME
multipart/mixed, alternative, related. base64 and quoted-printable. Boundary generation. Charset handling.

### 2.9 Message Queue
Persistent queue with retry scheduling: exponential backoff, configurable max retries. States: PENDING, SENDING, SENT, DEFERRED, BOUNCED, FAILED.

### 2.10 Relay and Routing
Smart host routing. MX record lookup via FizzDNS. Local delivery for matching domain.

### 2.11 SPF Validation
DNS TXT record parsing. Mechanisms: ip4, ip6, a, mx, include, all. Qualifiers: +, -, ~, ?. Recursion limit.

### 2.12 DKIM
RSA-SHA256 signing. Header canonicalization (relaxed/simple). Body hash. Selector-based key lookup. Verification.

### 2.13 DMARC
Policy lookup. Identifier alignment (relaxed/strict). Aggregate report generation. Actions: none/quarantine/reject.

### 2.14 Greylisting
Sender/recipient/IP triplet tracking. Auto-whitelist after delay. Configurable TTL.

### 2.15 RBL/DNSBL
Reversed IP query via FizzDNS. Multiple zones. Aggregate result.

### 2.16 Bounce Handling
DSN generation per RFC 3464. multipart/report with delivery-status and original message.

---

## 3. IMAP Server Components

### 3.1 IMAPServer
Connection state machine: NOT_AUTHENTICATED -> AUTHENTICATED -> SELECTED -> LOGOUT.

### 3.2 Authentication
LOGIN and AUTHENTICATE PLAIN.

### 3.3 Mailbox Operations
LIST, LSUB, CREATE, DELETE, RENAME, SUBSCRIBE, UNSUBSCRIBE, STATUS.

### 3.4 Message Access
SELECT/EXAMINE, FETCH (FLAGS, INTERNALDATE, RFC822*, ENVELOPE, BODY/BODYSTRUCTURE, BODY[section]<partial>, UID), STORE, COPY, MOVE.

### 3.5 SEARCH
Full criteria grammar: AND, OR, NOT, FROM, TO, SUBJECT, BODY, SINCE, BEFORE, SEEN, UNSEEN, FLAGGED, DELETED, LARGER, SMALLER. Body/text searches delegate to FizzSearch.

### 3.6 UID Commands
UID FETCH, UID STORE, UID COPY, UID SEARCH. Monotonically increasing per mailbox.

### 3.7 IDLE
Push notifications for new mail. DONE to exit.

### 3.8 NAMESPACE
Personal and shared folder separation.

### 3.9 EXPUNGE
Permanent deletion of \Deleted messages. Sequence number adjustment.

---

## 4. Storage

### 4.1 Maildir Format
In-memory simulation: new/, cur/, tmp/ per mailbox. File naming with flags. Atomic delivery (tmp -> new).

### 4.2 Message Indexing
FizzSearch integration for full-text search across headers and bodies.

### 4.3 Quota Enforcement
Per-mailbox storage limits. Reject delivery when exceeded.

---

## 5. Configuration

### 5.1 FizzMailConfig
~20 configurable properties: ports, domain, TLS, auth, DKIM, SPF, DMARC, greylisting, RBL, quota, retry, smart host.

### 5.2 CLI Flags
`--fizzmail`, `--fizzmail-smtp-port`, `--fizzmail-imap-port`, `--fizzmail-domain`, `--fizzmail-tls`, `--fizzmail-auth`, `--fizzmail-dkim-sign`, `--fizzmail-dkim-verify`, `--fizzmail-spf`, `--fizzmail-dmarc`, `--fizzmail-greylist`, `--fizzmail-rbl`, `--fizzmail-quota`, `--fizzmail-retry-max`, `--fizzmail-relay`, `--fizzmail-smart-host`, `--fizzmail-send`, `--fizzmail-list-mailboxes`, `--fizzmail-search`, `--fizzmail-idle`

---

## 6. Middleware & Wiring

### 6.1 FizzMailMiddleware
Implements IMiddleware. Priority ~120. Records metrics in context.metadata.

### 6.2 Dashboard
ASCII rendering of SMTP/IMAP state, queue status, delivery statistics.

### 6.3 Factory Function
`create_fizzmail_subsystem()` returns (SMTPServer, IMAPServer, FizzMailDashboard, FizzMailMiddleware).

### 6.4 __main__.py Wiring
Add CLI flags, construct subsystem when --fizzmail enabled, register middleware.

---

## 7. Implementation Sequence

### Phase 1: Foundation (~800 lines)
- Constants, enums, dataclasses
- RFC 5322 header parser
- MIME builder and parser

### Phase 2: SMTP Server (~1,200 lines)
- State machine and command parser
- STARTTLS, AUTH, envelope parsing, DATA
- Message queue with retry
- Relay router with MX lookup

### Phase 3: Email Security (~600 lines)
- SPF, DKIM, DMARC, greylisting, RBL, bounce handling

### Phase 4: IMAP Server (~1,000 lines)
- State machine, mailbox manager, Maildir storage
- FETCH, SEARCH, STORE, UID, COPY/MOVE, EXPUNGE, IDLE, NAMESPACE, quota

### Phase 5: Integration (~400 lines)
- Dashboard, middleware, factory, wiring

---

## 8. Test Plan (~600 tests)

- SMTP command parsing & state machine (~60)
- TLS (~15)
- Authentication (~30)
- Envelope parsing (~25)
- DATA phase (~20)
- RFC 5322 header parsing (~35)
- MIME (~45)
- Message queue (~25)
- SPF validation (~35)
- DKIM (~40)
- DMARC (~30)
- Greylisting (~20)
- RBL/DNSBL (~10)
- Bounce handling (~15)
- IMAP state machine (~30)
- IMAP FETCH (~40)
- IMAP SEARCH (~40)
- Maildir storage (~25)
- Quota enforcement (~15)
- Flag manipulation (~15)
- UID operations (~15)
- EXPUNGE (~10)
- Integration & middleware (~30)

---

## 9. Key Design Decisions

1. **Simulated I/O**: All network I/O simulated (consistent with FizzWeb, FizzDNS, FizzNet patterns)
2. **Maildir in-memory**: Dict-based storage simulating Maildir filesystem
3. **DNS via interface**: Duck-typed resolver for MX/TXT/A lookups; tests mock this
4. **FizzSearch via interface**: Duck-typed search engine for indexing/querying
5. **RSA simulation**: DKIM uses deterministic crypto (consistent with platform pattern)
6. **Middleware priority 120**: Between FizzWeb and other network subsystems
