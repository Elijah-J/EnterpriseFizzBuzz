# PLAN.md -- FizzSSH: SSH Protocol Server

## Overview

The Enterprise FizzBuzz Platform provides TCP/IP networking, DNS resolution,
TLS-capable reverse proxying, and a full container orchestration stack -- yet offers no
mechanism for secure, authenticated remote access to platform resources.  Operators
wishing to inspect FizzBuzz computation state, execute administrative commands, or
transfer configuration files must resort to insecure ad-hoc channels.

FizzSSH fills this gap by implementing the SSH-2 protocol (RFC 4253) as a simulated
in-process server.  It provides encrypted transport, multiple key exchange algorithms,
server host key authentication, three client authentication methods, multiplexed channels
with flow control, interactive shell sessions, remote command execution, SFTP file
operations, TCP/IP port forwarding, SCP transfers, session recording, rate limiting, and
configurable banner messages.

Architecture reference: OpenSSH, Dropbear, libssh, RFC 4251 (Architecture), RFC 4252
(Authentication), RFC 4253 (Transport), RFC 4254 (Connection), RFC 4256
(Keyboard-Interactive).

## Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `enterprise_fizzbuzz/infrastructure/fizzssh.py` | CREATE | Main module (~3,500 lines) |
| `enterprise_fizzbuzz/domain/exceptions/fizzssh.py` | CREATE | Exception hierarchy (~35 exception classes) |
| `enterprise_fizzbuzz/infrastructure/config/mixins/fizzssh.py` | CREATE | Configuration mixin properties |
| `enterprise_fizzbuzz/infrastructure/features/fizzssh_feature.py` | CREATE | Feature descriptor with CLI flags |
| `fizzssh.py` | CREATE | Backward-compatible re-export stub |
| `tests/test_fizzssh.py` | CREATE | Test suite (~250+ tests) |
| `enterprise_fizzbuzz/__main__.py` | MODIFY | Wire FizzSSH subsystem, add CLI flags |
| `enterprise_fizzbuzz/infrastructure/config/mixins/__init__.py` | MODIFY | Register mixin |
| `enterprise_fizzbuzz/infrastructure/features/__init__.py` | MODIFY | Register feature descriptor |
| `enterprise_fizzbuzz/domain/exceptions/__init__.py` | MODIFY | Register exceptions |

## Phase 1: Foundation (~400 lines)

### 1.1 Exception Hierarchy (`domain/exceptions/fizzssh.py`)

Base class `FizzSSHError(FizzBuzzError)` with error code prefix `EFP-SSH`.

Exception classes (~35):

- `FizzSSHError` -- base (EFP-SSH00)
- `SSHProtocolError` -- generic protocol violation (EFP-SSH01)
- `SSHTransportError` -- transport layer failure (EFP-SSH02)
- `SSHPacketError` -- malformed packet (EFP-SSH03)
- `SSHMACError` -- MAC verification failure (EFP-SSH04)
- `SSHEncryptionError` -- encryption/decryption failure (EFP-SSH05)
- `SSHKeyExchangeError` -- key exchange failure (EFP-SSH06)
- `SSHDHGroupError` -- DH group parameter error (EFP-SSH07)
- `SSHECDHError` -- ECDH exchange failure (EFP-SSH08)
- `SSHHostKeyError` -- host key management error (EFP-SSH09)
- `SSHHostKeyNotFoundError` -- requested host key type unavailable (EFP-SSH10)
- `SSHAuthenticationError` -- authentication failure (EFP-SSH11)
- `SSHPasswordAuthError` -- password auth rejected (EFP-SSH12)
- `SSHPublicKeyAuthError` -- public key auth rejected (EFP-SSH13)
- `SSHKeyboardInteractiveError` -- keyboard-interactive auth failure (EFP-SSH14)
- `SSHAuthorizedKeyError` -- authorized_keys parse/lookup error (EFP-SSH15)
- `SSHChannelError` -- channel lifecycle error (EFP-SSH16)
- `SSHChannelOpenError` -- channel open refused (EFP-SSH17)
- `SSHChannelEOFError` -- unexpected channel EOF (EFP-SSH18)
- `SSHChannelCloseError` -- channel close failure (EFP-SSH19)
- `SSHFlowControlError` -- window size violation (EFP-SSH20)
- `SSHSessionError` -- session channel error (EFP-SSH21)
- `SSHPTYError` -- PTY allocation failure (EFP-SSH22)
- `SSHExecError` -- remote command execution error (EFP-SSH23)
- `SSHSFTPError` -- SFTP subsystem error (EFP-SSH24)
- `SSHSFTPFileNotFoundError` -- SFTP target not found (EFP-SSH25)
- `SSHSFTPPermissionError` -- SFTP permission denied (EFP-SSH26)
- `SSHPortForwardError` -- port forwarding failure (EFP-SSH27)
- `SSHLocalForwardError` -- local tunnel failure (EFP-SSH28)
- `SSHRemoteForwardError` -- remote tunnel failure (EFP-SSH29)
- `SSHSCPError` -- SCP transfer error (EFP-SSH30)
- `SSHSessionRecordingError` -- audit recording failure (EFP-SSH31)
- `SSHRateLimitError` -- connection rate exceeded (EFP-SSH32)
- `SSHBannerError` -- banner delivery failure (EFP-SSH33)
- `SSHMaxSessionsError` -- session limit exceeded (EFP-SSH34)

### 1.2 Constants and Enums

```python
# SSH-2 protocol constants (RFC 4253 Section 12)
SSH_MSG_DISCONNECT = 1
SSH_MSG_IGNORE = 2
SSH_MSG_UNIMPLEMENTED = 3
SSH_MSG_DEBUG = 4
SSH_MSG_SERVICE_REQUEST = 5
SSH_MSG_SERVICE_ACCEPT = 6
SSH_MSG_KEXINIT = 20
SSH_MSG_NEWKEYS = 21
SSH_MSG_KEXDH_INIT = 30
SSH_MSG_KEXDH_REPLY = 31
SSH_MSG_USERAUTH_REQUEST = 50
SSH_MSG_USERAUTH_FAILURE = 51
SSH_MSG_USERAUTH_SUCCESS = 52
SSH_MSG_USERAUTH_BANNER = 53
SSH_MSG_USERAUTH_PK_OK = 60
SSH_MSG_USERAUTH_INFO_REQUEST = 60
SSH_MSG_USERAUTH_INFO_RESPONSE = 61
SSH_MSG_GLOBAL_REQUEST = 80
SSH_MSG_REQUEST_SUCCESS = 81
SSH_MSG_REQUEST_FAILURE = 82
SSH_MSG_CHANNEL_OPEN = 90
SSH_MSG_CHANNEL_OPEN_CONFIRMATION = 91
SSH_MSG_CHANNEL_OPEN_FAILURE = 92
SSH_MSG_CHANNEL_WINDOW_ADJUST = 93
SSH_MSG_CHANNEL_DATA = 94
SSH_MSG_CHANNEL_EXTENDED_DATA = 95
SSH_MSG_CHANNEL_EOF = 96
SSH_MSG_CHANNEL_CLOSE = 97
SSH_MSG_CHANNEL_REQUEST = 98
SSH_MSG_CHANNEL_SUCCESS = 99
SSH_MSG_CHANNEL_FAILURE = 100

# Disconnect reason codes (RFC 4253 Section 11.1)
SSH_DISCONNECT_HOST_NOT_ALLOWED_TO_CONNECT = 1
SSH_DISCONNECT_PROTOCOL_ERROR = 2
SSH_DISCONNECT_KEY_EXCHANGE_FAILED = 3
SSH_DISCONNECT_RESERVED = 4
SSH_DISCONNECT_MAC_ERROR = 5
SSH_DISCONNECT_COMPRESSION_ERROR = 6
SSH_DISCONNECT_SERVICE_NOT_AVAILABLE = 7
SSH_DISCONNECT_PROTOCOL_VERSION_NOT_SUPPORTED = 8
SSH_DISCONNECT_HOST_KEY_NOT_VERIFIABLE = 9
SSH_DISCONNECT_CONNECTION_LOST = 10
SSH_DISCONNECT_BY_APPLICATION = 11
SSH_DISCONNECT_TOO_MANY_CONNECTIONS = 12
SSH_DISCONNECT_AUTH_CANCELLED_BY_USER = 13
SSH_DISCONNECT_NO_MORE_AUTH_METHODS_AVAILABLE = 14
SSH_DISCONNECT_ILLEGAL_USER_NAME = 15
```

Enums:

- `SSHState` -- `INITIAL`, `VERSION_EXCHANGE`, `KEY_EXCHANGE`, `AUTHENTICATED`, `CONNECTED`, `DISCONNECTED`
- `KeyExchangeAlgorithm` -- `DIFFIE_HELLMAN_GROUP14_SHA256`, `DIFFIE_HELLMAN_GROUP16_SHA512`, `DIFFIE_HELLMAN_GROUP_EXCHANGE_SHA256`, `ECDH_SHA2_NISTP256`, `CURVE25519_SHA256`
- `HostKeyAlgorithm` -- `SSH_ED25519`, `SSH_RSA`, `RSA_SHA2_256`, `RSA_SHA2_512`
- `CipherAlgorithm` -- `AES128_CTR`, `AES192_CTR`, `AES256_CTR`, `AES128_GCM`, `AES256_GCM`, `CHACHA20_POLY1305`
- `MACAlgorithm` -- `HMAC_SHA2_256`, `HMAC_SHA2_512`, `HMAC_SHA2_256_ETM`, `HMAC_SHA2_512_ETM`
- `CompressionAlgorithm` -- `NONE`, `ZLIB`, `ZLIB_OPENSSH`
- `AuthMethod` -- `PASSWORD`, `PUBLIC_KEY`, `KEYBOARD_INTERACTIVE`
- `ChannelType` -- `SESSION`, `DIRECT_TCPIP`, `FORWARDED_TCPIP`
- `ChannelState` -- `OPENING`, `OPEN`, `EOF_SENT`, `EOF_RECEIVED`, `CLOSING`, `CLOSED`
- `SFTPOperation` -- `OPEN`, `CLOSE`, `READ`, `WRITE`, `STAT`, `FSTAT`, `LSTAT`, `OPENDIR`, `READDIR`, `REMOVE`, `MKDIR`, `RMDIR`, `RENAME`, `SYMLINK`, `READLINK`, `REALPATH`
- `TerminalMode` -- `VINTR`, `VQUIT`, `VERASE`, `VKILL`, `VEOF`, `VEOL`, `VEOL2`, `VSTART`, `VSTOP`, `VSUSP`, `ECHO`, `ECHOE`, `ECHOK`, `ECHOCTL`, `ISIG`, `ICANON`, `IXON`, `IXOFF`, `OPOST`, `CS7`, `CS8`, `TTY_OP_END`

### 1.3 Dataclasses

```python
@dataclass
class FizzSSHConfig:
    host: str = "127.0.0.1"
    port: int = 2222
    host_key_algorithms: List[HostKeyAlgorithm]
    kex_algorithms: List[KeyExchangeAlgorithm]
    ciphers: List[CipherAlgorithm]
    macs: List[MACAlgorithm]
    compression: List[CompressionAlgorithm]
    password_auth_enabled: bool = True
    pubkey_auth_enabled: bool = True
    keyboard_interactive_enabled: bool = False
    sftp_enabled: bool = True
    port_forwarding_enabled: bool = True
    session_recording_enabled: bool = False
    max_sessions: int = 256
    idle_timeout: float = 3600.0
    auth_max_attempts: int = 6
    banner_message: Optional[str] = None
    rate_limit_max_connections: int = 100
    rate_limit_window_seconds: float = 60.0

@dataclass
class SSHKeyPair:
    algorithm: HostKeyAlgorithm
    public_key: bytes
    private_key: bytes
    fingerprint_sha256: str
    fingerprint_md5: str
    comment: str = ""
    created_at: float

@dataclass
class SSHSession:
    session_id: str
    client_address: Tuple[str, int]
    server_address: Tuple[str, int]
    state: SSHState
    username: Optional[str]
    auth_method: Optional[AuthMethod]
    channels: Dict[int, 'SSHChannel']
    kex_algorithm: Optional[KeyExchangeAlgorithm]
    cipher_algorithm: Optional[CipherAlgorithm]
    mac_algorithm: Optional[MACAlgorithm]
    compression: Optional[CompressionAlgorithm]
    session_key: Optional[bytes]
    sequence_number_client: int = 0
    sequence_number_server: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0
    connected_at: float
    last_activity: float
    client_version: str = ""
    server_version: str = "SSH-2.0-FizzSSH_1.0"

@dataclass
class SSHChannel:
    channel_id: int
    remote_channel_id: int
    channel_type: ChannelType
    state: ChannelState
    initial_window_size: int = 2097152  # 2MB
    max_packet_size: int = 32768
    local_window_size: int = 2097152
    remote_window_size: int = 2097152
    data_buffer: bytes = b""
    pty_allocated: bool = False
    pty_term: str = ""
    pty_width: int = 80
    pty_height: int = 24
    pty_modes: Dict[TerminalMode, int]
    environment: Dict[str, str]
    exec_command: Optional[str] = None
    subsystem: Optional[str] = None
    exit_status: Optional[int] = None

@dataclass
class SSHPacket:
    packet_length: int
    padding_length: int
    payload: bytes
    padding: bytes
    mac: bytes
    sequence_number: int

@dataclass
class PortForwardBinding:
    bind_address: str
    bind_port: int
    destination_address: str
    destination_port: int
    direction: str  # "local" or "remote"
    active: bool = True
    bytes_forwarded: int = 0

@dataclass
class SFTPHandle:
    handle_id: str
    path: str
    is_directory: bool
    read_offset: int = 0
    write_offset: int = 0
    flags: int = 0
    opened_at: float

@dataclass
class SessionRecording:
    session_id: str
    username: str
    client_address: str
    connected_at: float
    disconnected_at: Optional[float]
    auth_method: str
    events: List[Dict[str, Any]]  # timestamp, event_type, data
    bytes_transmitted: int = 0
    commands_executed: List[str]
```

## Phase 2: Protocol Core (~1,000 lines)

### 2.1 SSHTransport

The transport layer implements the SSH-2 binary packet protocol (RFC 4253 Section 6).

Responsibilities:
- Version string exchange (`SSH-2.0-FizzSSH_1.0`)
- Binary packet framing: 4-byte packet_length, 1-byte padding_length, payload, padding, MAC
- Packet serialization/deserialization with proper SSH data type encoding (byte, uint32, string, mpint, name-list)
- Encryption envelope: encrypt payload+padding, compute MAC over sequence_number+unencrypted_packet
- Sequence number tracking (separate client-to-server and server-to-client counters, 32-bit wrapping)
- Re-keying after 1GB transferred or 1 hour elapsed
- `SSH_MSG_IGNORE` and `SSH_MSG_DISCONNECT` handling

Key methods:
- `encode_packet(msg_type: int, payload: bytes, session: SSHSession) -> bytes`
- `decode_packet(data: bytes, session: SSHSession) -> SSHPacket`
- `encode_string(s: str) -> bytes` -- uint32 length prefix + UTF-8 bytes
- `encode_mpint(n: int) -> bytes` -- SSH mpint encoding
- `decode_mpint(data: bytes, offset: int) -> Tuple[int, int]`
- `encode_name_list(names: List[str]) -> bytes`
- `compute_mac(key: bytes, sequence_number: int, packet: bytes, algorithm: MACAlgorithm) -> bytes`
- `verify_mac(key: bytes, sequence_number: int, packet: bytes, mac: bytes, algorithm: MACAlgorithm) -> bool`
- `encrypt_payload(key: bytes, iv: bytes, plaintext: bytes, algorithm: CipherAlgorithm) -> bytes`
- `decrypt_payload(key: bytes, iv: bytes, ciphertext: bytes, algorithm: CipherAlgorithm) -> bytes`
- `check_rekey_needed(session: SSHSession) -> bool`

### 2.2 KeyExchange

Implements SSH-2 key exchange (RFC 4253 Section 7, RFC 4419 for DH group exchange).

**Diffie-Hellman Group Exchange:**
1. Client sends `SSH_MSG_KEX_DH_GEX_REQUEST` with min/preferred/max group sizes
2. Server selects a safe prime group and sends `SSH_MSG_KEX_DH_GEX_GROUP` (p, g)
3. Client generates random x, computes e = g^x mod p, sends `SSH_MSG_KEXDH_INIT`
4. Server generates random y, computes f = g^y mod p, K = e^y mod p
5. Server computes exchange hash H = HASH(V_C || V_S || I_C || I_S || K_S || min || n || max || p || g || e || f || K)
6. Server signs H with host key, sends `SSH_MSG_KEXDH_REPLY` (K_S, f, sig)
7. Both derive session keys from K and H

**ECDH-Curve25519:**
1. Both sides generate ephemeral Curve25519 key pairs
2. Client sends public key Q_C in `SSH_MSG_KEX_ECDH_INIT`
3. Server sends public key Q_S and signed exchange hash in `SSH_MSG_KEX_ECDH_REPLY`
4. Shared secret K = ECDH(Q_C, Q_S) using Curve25519 scalar multiplication
5. Session keys derived via HASH(K || H || session_id || letter) for each direction

Key derivation produces six keys: initial IV client-to-server, initial IV server-to-client,
encryption key C2S, encryption key S2C, MAC key C2S, MAC key S2C.

Key methods:
- `negotiate_algorithms(client_kexinit: bytes, server_kexinit: bytes) -> NegotiatedAlgorithms`
- `perform_dh_group_exchange(session: SSHSession) -> bytes`
- `perform_ecdh_curve25519(session: SSHSession) -> bytes`
- `derive_session_keys(shared_secret: int, exchange_hash: bytes, session_id: bytes) -> SessionKeys`
- `generate_dh_parameters(group_size: int) -> Tuple[int, int]`
- `curve25519_scalar_mult(private: bytes, public: bytes) -> bytes` (simulated)

### 2.3 HostKeyManager

Manages server host keys for multiple algorithms.

Responsibilities:
- Generate Ed25519 and RSA key pairs (simulated using hashlib-based deterministic generation)
- Store and retrieve host keys by algorithm
- Sign exchange hashes during key exchange
- Verify signatures (for client-side simulation)
- Compute key fingerprints (SHA-256 and MD5)
- Serialize keys in SSH wire format (ssh-ed25519, ssh-rsa)

Key methods:
- `generate_host_key(algorithm: HostKeyAlgorithm) -> SSHKeyPair`
- `get_host_key(algorithm: HostKeyAlgorithm) -> SSHKeyPair`
- `sign(private_key: bytes, data: bytes, algorithm: HostKeyAlgorithm) -> bytes`
- `verify(public_key: bytes, data: bytes, signature: bytes, algorithm: HostKeyAlgorithm) -> bool`
- `fingerprint(public_key: bytes) -> str` -- base64-encoded SHA-256
- `serialize_public_key(key: SSHKeyPair) -> bytes` -- SSH wire format

### 2.4 ClientAuthenticator

Implements the three authentication methods defined by RFC 4252.

**Password Authentication:**
- Client sends `SSH_MSG_USERAUTH_REQUEST` with method "password" and cleartext password
- Server verifies against stored credential database (salted + hashed with SHA-512)
- Supports password change requests

**Public Key Authentication:**
- Client sends `SSH_MSG_USERAUTH_REQUEST` with method "publickey", algorithm name, and public key blob
- Server checks if public key is in authorized_keys for the user
- If query-only (has_signature=false), server responds with `SSH_MSG_USERAUTH_PK_OK`
- If has_signature=true, server verifies the signature over the session ID + request fields
- Supports Ed25519 and RSA key types

**Keyboard-Interactive (RFC 4256):**
- Server sends `SSH_MSG_USERAUTH_INFO_REQUEST` with prompts
- Client responds with `SSH_MSG_USERAUTH_INFO_RESPONSE`
- Supports multi-round challenge-response (e.g., TOTP simulation)

Key methods:
- `authenticate(session: SSHSession, request: bytes) -> AuthResult`
- `verify_password(username: str, password: str) -> bool`
- `verify_public_key(username: str, key_blob: bytes, signature: Optional[bytes], signed_data: bytes) -> bool`
- `keyboard_interactive_challenge(username: str, round_num: int) -> List[str]`
- `keyboard_interactive_respond(username: str, responses: List[str]) -> bool`

### 2.5 AuthorizedKeysStore

Parses and manages OpenSSH-format authorized_keys files.

Format: `algorithm base64-key comment`

Supports:
- Multiple keys per user
- Key options parsing (command=, from=, no-pty, etc.)
- Wildcard hostname matching in `from=` restrictions
- Key revocation

Key methods:
- `load_authorized_keys(username: str, data: str) -> List[AuthorizedKey]`
- `is_authorized(username: str, algorithm: str, key_blob: bytes) -> bool`
- `add_key(username: str, key: AuthorizedKey) -> None`
- `remove_key(username: str, fingerprint: str) -> None`
- `get_key_options(username: str, fingerprint: str) -> Dict[str, Any]`

## Phase 3: Channels and Services (~1,000 lines)

### 3.1 ChannelMultiplexer

Manages the lifecycle of multiplexed channels over a single SSH connection (RFC 4254).

Responsibilities:
- Channel open/confirm/reject with reason codes
- Channel ID allocation (local and remote)
- Flow control via sliding window (`SSH_MSG_CHANNEL_WINDOW_ADJUST`)
- Data routing to appropriate channel handlers
- Channel EOF and close sequencing (half-close semantics)
- Extended data (stderr) handling

Key methods:
- `open_channel(session: SSHSession, channel_type: ChannelType, initial_window: int, max_packet: int) -> SSHChannel`
- `confirm_channel(session: SSHSession, channel: SSHChannel) -> bytes`
- `reject_channel(session: SSHSession, channel_id: int, reason_code: int, description: str) -> bytes`
- `send_data(session: SSHSession, channel: SSHChannel, data: bytes) -> bytes`
- `send_extended_data(session: SSHSession, channel: SSHChannel, data_type: int, data: bytes) -> bytes`
- `adjust_window(session: SSHSession, channel: SSHChannel, bytes_to_add: int) -> bytes`
- `close_channel(session: SSHSession, channel: SSHChannel) -> bytes`
- `handle_channel_data(session: SSHSession, channel: SSHChannel, data: bytes) -> None`

### 3.2 SessionChannel

Handles interactive shell sessions with PTY allocation.

Responsibilities:
- PTY allocation with terminal type (xterm, vt100, etc.), dimensions, and terminal modes
- Shell request processing
- Environment variable passing
- Terminal window resize (`SSH_MSG_CHANNEL_REQUEST` "window-change")
- Signal forwarding (INT, QUIT, TERM, KILL, etc.)
- Exit status reporting

Key methods:
- `allocate_pty(channel: SSHChannel, term: str, width: int, height: int, modes: Dict[TerminalMode, int]) -> None`
- `start_shell(session: SSHSession, channel: SSHChannel) -> None`
- `set_environment(channel: SSHChannel, name: str, value: str) -> None`
- `resize_window(channel: SSHChannel, width: int, height: int) -> None`
- `send_signal(channel: SSHChannel, signal_name: str) -> None`
- `process_input(session: SSHSession, channel: SSHChannel, data: bytes) -> bytes`

### 3.3 ExecChannel

Handles single remote command execution.

- Parses command string
- Simulates execution against FizzBuzz platform commands
- Returns stdout, stderr, exit status
- Built-in commands: `fizzbuzz <n>`, `status`, `uptime`, `whoami`, `help`, `config show`, `metrics`

Key methods:
- `execute(session: SSHSession, channel: SSHChannel, command: str) -> ExecResult`
- `parse_command(command: str) -> Tuple[str, List[str]]`

### 3.4 SFTPSubsystem

Implements the SFTP protocol (RFC 4254 subsystem "sftp") for file operations.

The SFTP subsystem operates over an SSH channel and provides a virtual filesystem
rooted at the FizzBuzz platform's data directory.

Packet types:
- SSH_FXP_INIT / SSH_FXP_VERSION (version negotiation, version 3)
- SSH_FXP_OPEN / SSH_FXP_CLOSE / SSH_FXP_READ / SSH_FXP_WRITE
- SSH_FXP_STAT / SSH_FXP_FSTAT / SSH_FXP_LSTAT
- SSH_FXP_OPENDIR / SSH_FXP_READDIR
- SSH_FXP_REMOVE / SSH_FXP_MKDIR / SSH_FXP_RMDIR
- SSH_FXP_RENAME / SSH_FXP_SYMLINK / SSH_FXP_READLINK / SSH_FXP_REALPATH
- SSH_FXP_STATUS / SSH_FXP_HANDLE / SSH_FXP_DATA / SSH_FXP_NAME / SSH_FXP_ATTRS

Status codes: SSH_FX_OK, SSH_FX_EOF, SSH_FX_NO_SUCH_FILE, SSH_FX_PERMISSION_DENIED,
SSH_FX_FAILURE, SSH_FX_BAD_MESSAGE, SSH_FX_OP_UNSUPPORTED.

Virtual filesystem provides:
- `/config/` -- platform configuration files
- `/logs/` -- computation logs
- `/data/` -- FizzBuzz output data
- `/keys/` -- authorized keys (read-only)

Key methods:
- `handle_sftp_packet(session: SSHSession, channel: SSHChannel, packet: bytes) -> bytes`
- `sftp_open(path: str, flags: int, attrs: Dict) -> SFTPHandle`
- `sftp_close(handle: SFTPHandle) -> None`
- `sftp_read(handle: SFTPHandle, offset: int, length: int) -> bytes`
- `sftp_write(handle: SFTPHandle, offset: int, data: bytes) -> int`
- `sftp_stat(path: str) -> SFTPAttrs`
- `sftp_opendir(path: str) -> SFTPHandle`
- `sftp_readdir(handle: SFTPHandle) -> List[SFTPEntry]`
- `sftp_remove(path: str) -> None`
- `sftp_mkdir(path: str, attrs: Dict) -> None`
- `sftp_rmdir(path: str) -> None`
- `sftp_rename(old_path: str, new_path: str) -> None`
- `sftp_realpath(path: str) -> str`

### 3.5 PortForwarder

Implements TCP/IP port forwarding (tunneling) per RFC 4254 Sections 7.1 and 7.2.

**Local forwarding** (client connects to local port, traffic tunnels to remote host):
- Client sends `SSH_MSG_GLOBAL_REQUEST` "tcpip-forward" with bind address and port
- Server confirms, opens `forwarded-tcpip` channels for inbound connections

**Remote forwarding** (remote port on server forwards to client-side destination):
- Client sends `SSH_MSG_CHANNEL_OPEN` "direct-tcpip" with destination address and port
- Server opens channel, data flows bidirectionally

Both directions support:
- Multiple concurrent forwarding bindings
- Binding to specific addresses or wildcard (0.0.0.0)
- Bytes-forwarded accounting per binding

Key methods:
- `request_local_forward(session: SSHSession, bind_addr: str, bind_port: int) -> PortForwardBinding`
- `cancel_local_forward(session: SSHSession, bind_addr: str, bind_port: int) -> None`
- `open_direct_tcpip(session: SSHSession, dest_addr: str, dest_port: int, orig_addr: str, orig_port: int) -> SSHChannel`
- `forward_data(binding: PortForwardBinding, data: bytes) -> bytes`
- `list_active_forwards(session: SSHSession) -> List[PortForwardBinding]`

### 3.6 SCPHandler

Implements the SCP (Secure Copy Protocol) for simple file transfers.

SCP protocol (legacy, operates over exec channel):
- `scp -t <path>` (sink mode -- receive files)
- `scp -f <path>` (source mode -- send files)

Protocol messages:
- `C<mode> <size> <filename>` -- file header
- `D<mode> 0 <dirname>` -- directory entry
- `E` -- end of directory
- `T<mtime> 0 <atime> 0` -- timestamps (optional)
- `\x00` -- OK, `\x01` -- warning, `\x02` -- error

Key methods:
- `handle_scp(session: SSHSession, channel: SSHChannel, command: str) -> None`
- `scp_send_file(channel: SSHChannel, path: str, data: bytes, mode: int) -> None`
- `scp_receive_file(channel: SSHChannel) -> Tuple[str, bytes, int]`
- `scp_send_directory(channel: SSHChannel, path: str, entries: List) -> None`

## Phase 4: Integration (~600 lines)

### 4.1 SessionRecorder

Records all session activity for compliance audit trails.

Each recording captures:
- Session metadata (user, client address, auth method, timestamps)
- All channel data events with millisecond timestamps
- Commands executed
- Files transferred (names and sizes, not contents)
- Window resize events
- Total bytes transmitted

Supports replay by emitting events in chronological order with timing information.

Key methods:
- `start_recording(session: SSHSession) -> SessionRecording`
- `record_event(recording: SessionRecording, event_type: str, data: Any) -> None`
- `stop_recording(recording: SessionRecording) -> None`
- `get_recording(session_id: str) -> SessionRecording`
- `replay(recording: SessionRecording) -> Iterator[Tuple[float, str, Any]]`
- `export_recording(recording: SessionRecording, format: str) -> str` (JSON or text)

### 4.2 ConnectionRateLimiter

Sliding-window rate limiter for incoming SSH connections.

- Tracks connection attempts per source address within configurable window
- Rejects connections exceeding threshold with `SSH_DISCONNECT_TOO_MANY_CONNECTIONS`
- Separate limits for authentication failures per address
- Exponential backoff for repeated failures

Key methods:
- `check_rate_limit(client_address: str) -> bool`
- `record_connection(client_address: str) -> None`
- `record_auth_failure(client_address: str) -> None`
- `get_stats() -> Dict[str, Any]`
- `reset(client_address: Optional[str] = None) -> None`

### 4.3 BannerManager

Manages pre-authentication and post-authentication banner messages.

- Pre-auth banner sent via `SSH_MSG_USERAUTH_BANNER` before auth completes
- Post-auth MOTD delivered after successful authentication
- Dynamic banners with template variables: `{hostname}`, `{version}`, `{time}`, `{sessions}`
- Banner rotation (multiple banners, selected round-robin or randomly)

Default banner:
```
  =====================================================================
  =  Enterprise FizzBuzz Platform - FizzSSH Secure Access             =
  =  Authorized access only. All sessions are recorded.               =
  =====================================================================
```

Key methods:
- `get_pre_auth_banner() -> str`
- `get_post_auth_motd(session: SSHSession) -> str`
- `set_banner(banner: str) -> None`
- `add_banner_rotation(banners: List[str]) -> None`

### 4.4 FizzSSHDashboard

Provides real-time visibility into the SSH server's operational state.

Dashboard data:
- Active sessions (count, per-user, per-address)
- Authentication statistics (success/failure rates, methods used)
- Channel statistics (open channels by type, data throughput)
- Port forwarding status (active bindings, bytes forwarded)
- Rate limiter status (blocked addresses, current rates)
- Key exchange statistics (algorithms negotiated, re-key counts)
- SFTP operations (files transferred, bytes moved)
- Session recordings (count, total size)

Key methods:
- `get_dashboard_data() -> Dict[str, Any]`
- `get_active_sessions() -> List[Dict[str, Any]]`
- `get_auth_statistics() -> Dict[str, Any]`
- `get_transfer_statistics() -> Dict[str, Any]`

### 4.5 FizzSSHMiddleware

Integrates FizzSSH into the Enterprise FizzBuzz middleware pipeline.

When enabled, appends SSH server status information to FizzBuzz output and makes
the platform accessible via SSH for remote computation requests.

Key methods:
- `process(value: int, current_result: str) -> str`
- `get_status() -> Dict[str, Any]`

### 4.6 Factory Function

```python
def create_fizzssh_subsystem(config: FizzSSHConfig) -> Dict[str, Any]:
    """Factory function to wire all FizzSSH components."""
    host_key_manager = HostKeyManager()
    # Generate default host keys
    host_key_manager.generate_host_key(HostKeyAlgorithm.SSH_ED25519)
    host_key_manager.generate_host_key(HostKeyAlgorithm.SSH_RSA)

    transport = SSHTransport(config)
    key_exchange = KeyExchange(config, host_key_manager)
    authorized_keys = AuthorizedKeysStore()
    authenticator = ClientAuthenticator(config, authorized_keys)
    multiplexer = ChannelMultiplexer(config)
    session_channel = SessionChannel()
    exec_channel = ExecChannel()
    sftp = SFTPSubsystem(config)
    port_forwarder = PortForwarder(config)
    scp_handler = SCPHandler()
    recorder = SessionRecorder(config)
    rate_limiter = ConnectionRateLimiter(config)
    banner = BannerManager(config)
    dashboard = FizzSSHDashboard(...)
    middleware = FizzSSHMiddleware(...)

    return {
        "transport": transport,
        "key_exchange": key_exchange,
        "host_key_manager": host_key_manager,
        "authenticator": authenticator,
        "authorized_keys": authorized_keys,
        "multiplexer": multiplexer,
        "session_channel": session_channel,
        "exec_channel": exec_channel,
        "sftp": sftp,
        "port_forwarder": port_forwarder,
        "scp_handler": scp_handler,
        "recorder": recorder,
        "rate_limiter": rate_limiter,
        "banner": banner,
        "dashboard": dashboard,
        "middleware": middleware,
    }
```

## CLI Flags

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--fizzssh` | store_true | False | Enable FizzSSH secure shell server |
| `--fizzssh-port` | int | 2222 | SSH server listen port |
| `--fizzssh-host-key` | str | None | Path to host key file (PEM format) |
| `--fizzssh-authorized-keys` | str | None | Path to authorized_keys file |
| `--fizzssh-password-auth` | store_true | True | Enable password authentication |
| `--fizzssh-pubkey-auth` | store_true | True | Enable public key authentication |
| `--fizzssh-sftp` | store_true | True | Enable SFTP subsystem |
| `--fizzssh-port-forwarding` | store_true | True | Enable TCP/IP port forwarding |
| `--fizzssh-session-recording` | store_true | False | Enable session recording for audit compliance |
| `--fizzssh-banner` | str | None | Custom pre-authentication banner message |
| `--fizzssh-max-sessions` | int | 256 | Maximum concurrent SSH sessions |
| `--fizzssh-idle-timeout` | float | 3600.0 | Session idle timeout in seconds |
| `--fizzssh-rate-limit` | int | 100 | Maximum connections per minute per source address |

## Configuration Mixin Properties

```python
class FizzsshConfigMixin:
    fizzssh_enabled: bool
    fizzssh_port: int
    fizzssh_host_key_path: Optional[str]
    fizzssh_authorized_keys_path: Optional[str]
    fizzssh_password_auth: bool
    fizzssh_pubkey_auth: bool
    fizzssh_sftp_enabled: bool
    fizzssh_port_forwarding: bool
    fizzssh_session_recording: bool
    fizzssh_banner: Optional[str]
    fizzssh_max_sessions: int
    fizzssh_idle_timeout: float
    fizzssh_rate_limit: int
```

## Feature Descriptor

```python
class FizzSSHFeature(FeatureDescriptor):
    name = "fizzssh"
    description = "SSH-2 protocol server with encrypted transport, key exchange, client authentication, channel multiplexing, SFTP, and port forwarding"
    middleware_priority = 138
    cli_flags = [...]  # 13 flags as listed above
```

## Test Plan (~250+ tests)

### Transport Tests (~40)
- Packet encoding/decoding round-trip
- SSH data type encoding (string, mpint, name-list, uint32, byte)
- Packet framing with correct padding (multiple of 8, minimum 4)
- MAC computation and verification for each MAC algorithm
- Encryption/decryption for each cipher algorithm
- Sequence number wrapping at 2^32
- Re-key threshold detection (bytes and time)
- Version string parsing and validation
- Malformed packet rejection
- Oversized packet rejection (>35000 bytes)

### Key Exchange Tests (~35)
- Algorithm negotiation (matching first common algorithm)
- Algorithm negotiation failure (no common algorithm)
- DH group14 key exchange simulation
- DH group16 key exchange simulation
- DH group exchange with custom group sizes
- ECDH-Curve25519 key exchange simulation
- Session key derivation produces six distinct keys
- Exchange hash computation matches expected value
- Host key signature verification during KEX
- Re-keying produces new session keys

### Host Key Tests (~25)
- Ed25519 key generation produces valid key pair
- RSA key generation produces valid key pair
- Key fingerprint computation (SHA-256 and MD5)
- Public key serialization in SSH wire format
- Sign and verify round-trip for Ed25519
- Sign and verify round-trip for RSA
- Key retrieval by algorithm type
- Multiple host keys stored simultaneously
- Invalid algorithm rejection
- Key persistence across sessions

### Authentication Tests (~40)
- Password auth success with valid credentials
- Password auth failure with wrong password
- Password auth failure with unknown user
- Password auth disabled when config says so
- Public key auth success with authorized key
- Public key auth query (no signature) returns PK_OK
- Public key auth failure with unauthorized key
- Public key auth failure with invalid signature
- Public key auth disabled when config says so
- Keyboard-interactive single-round success
- Keyboard-interactive multi-round challenge
- Keyboard-interactive failure
- Auth attempt counting and lockout after max_attempts
- Multiple auth method fallback
- Banner sent before auth
- Service request for ssh-userauth accepted
- Service request for unknown service rejected

### Authorized Keys Tests (~20)
- Parse single authorized key line
- Parse multiple keys
- Parse keys with comments
- Parse keys with options (command=, from=, no-pty)
- Wildcard hostname matching in from= option
- Key lookup by fingerprint
- Add and remove keys
- Empty authorized_keys handling
- Malformed line handling (skip, don't crash)
- Duplicate key detection

### Channel Tests (~35)
- Open session channel
- Open direct-tcpip channel
- Channel confirmation with correct IDs
- Channel rejection with reason code
- Multiple channels on same session
- Channel ID allocation (sequential)
- Window size tracking on send
- Window adjust increases remote window
- Data rejected when window exhausted
- Extended data (stderr) routing
- Channel EOF sequencing (half-close)
- Channel close sequencing
- Data buffering before channel open confirmation
- Max packet size enforcement

### Session Channel Tests (~20)
- PTY allocation with terminal type and dimensions
- Terminal mode setting (individual modes)
- Shell request processing
- Environment variable setting
- Window resize event handling
- Signal forwarding (INT, TERM, KILL)
- Exit status reporting
- Input processing produces output
- Session without PTY (no terminal)

### Exec Channel Tests (~15)
- Execute `fizzbuzz <n>` returns correct output
- Execute `status` returns server status
- Execute `whoami` returns authenticated username
- Execute `help` returns command list
- Execute unknown command returns error with exit status 127
- Command with arguments parsed correctly
- Exit status propagation
- Stderr output for errors

### SFTP Tests (~30)
- Version negotiation (client sends INIT, server responds VERSION)
- Open file for reading
- Open file for writing
- Read file contents
- Write file contents
- Close file handle
- Stat file returns correct attributes
- Opendir and readdir enumerate directory contents
- Mkdir creates new directory
- Rmdir removes empty directory
- Remove deletes file
- Rename moves file
- Realpath resolves to absolute path
- Permission denied for unauthorized paths
- File not found error
- Handle lifecycle (open, use, close)
- Multiple concurrent handles
- Invalid handle rejection
- Virtual filesystem root enforcement (no path traversal)

### Port Forwarding Tests (~15)
- Local forward binding creation
- Local forward cancellation
- Remote forward (direct-tcpip) channel open
- Data forwarding through tunnel
- Bytes-forwarded accounting
- Multiple concurrent forwards
- Port forwarding disabled when config says so
- Wildcard bind address
- Duplicate binding rejection

### SCP Tests (~10)
- Send single file
- Receive single file
- File mode preservation
- Directory transfer
- Timestamp preservation
- Error propagation (file not found)
- Large file transfer (chunked)

### Session Recording Tests (~15)
- Recording starts on session open
- Events captured with timestamps
- Command execution events recorded
- Channel data events recorded
- Recording stops on session close
- Recording retrieval by session ID
- Replay produces events in order with timing
- Export to JSON format
- Export to text format
- Recording disabled when config says so

### Rate Limiting Tests (~10)
- Connections within limit accepted
- Connections exceeding limit rejected
- Sliding window expiry allows new connections
- Auth failure tracking
- Exponential backoff applied
- Per-address isolation
- Stats reporting
- Rate limiter reset

### Banner Tests (~8)
- Default banner content
- Custom banner override
- Template variable substitution ({hostname}, {version}, {time})
- Banner rotation (round-robin)
- Pre-auth banner delivery timing
- Post-auth MOTD delivery
- Empty banner suppression

### Dashboard Tests (~8)
- Active session count
- Auth statistics aggregation
- Channel statistics
- Transfer statistics
- Rate limiter status
- Dashboard data structure completeness

### Integration Tests (~10)
- Factory function creates all components
- Middleware processes FizzBuzz value with SSH status
- Full connection lifecycle: version exchange, KEX, auth, channel, data, close
- Session timeout disconnection
- Graceful disconnect sequencing
- Config mixin properties read correctly

### Edge Cases (~5)
- Zero-length payload packet
- Maximum channel count per session
- Concurrent sessions at max limit
- Re-key during data transfer
- Disconnect during key exchange

## Implementation Order

1. Create `enterprise_fizzbuzz/domain/exceptions/fizzssh.py` -- exception hierarchy
2. Create `enterprise_fizzbuzz/infrastructure/fizzssh.py` -- Phase 1 (constants, enums, dataclasses), then Phase 2, then Phase 3, then Phase 4
3. Create `enterprise_fizzbuzz/infrastructure/config/mixins/fizzssh.py` -- config mixin
4. Create `enterprise_fizzbuzz/infrastructure/features/fizzssh_feature.py` -- feature descriptor
5. Create `fizzssh.py` -- backward-compat stub
6. Create `tests/test_fizzssh.py` -- full test suite
7. Modify `enterprise_fizzbuzz/__main__.py` -- wire subsystem and CLI flags
8. Modify `enterprise_fizzbuzz/infrastructure/config/mixins/__init__.py` -- register mixin
9. Modify `enterprise_fizzbuzz/infrastructure/features/__init__.py` -- register feature
10. Modify `enterprise_fizzbuzz/domain/exceptions/__init__.py` -- register exceptions

## Estimated Scope

| Artifact | Lines |
|----------|-------|
| `fizzssh.py` (infrastructure) | ~3,500 |
| `fizzssh.py` (exceptions) | ~400 |
| `fizzssh.py` (config mixin) | ~120 |
| `fizzssh_feature.py` | ~80 |
| `fizzssh.py` (compat stub) | ~3 |
| `test_fizzssh.py` | ~3,000 |
| Wiring modifications | ~50 |
| **Total** | **~7,150** |
