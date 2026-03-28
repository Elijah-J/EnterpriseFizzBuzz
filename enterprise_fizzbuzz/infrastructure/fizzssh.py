"""
Enterprise FizzBuzz Platform - FizzSSH: SSH Protocol Server

Production-grade SSH-2 protocol server (RFC 4253) for the Enterprise FizzBuzz
Platform.  Implements the complete SSH transport layer with binary packet
framing, key exchange (Diffie-Hellman group exchange, ECDH with Curve25519),
server host key authentication (Ed25519, RSA), client authentication (password,
public key with authorized_keys, keyboard-interactive), channel multiplexing
(session, direct-tcpip, forwarded-tcpip), interactive shell sessions with PTY
allocation and terminal modes, remote command execution, SFTP subsystem with
file operations, TCP/IP port forwarding (local and remote), SCP file transfer,
session recording with audit logging, and connection rate limiting.

FizzSSH fills the platform's remote administration gap -- 139 infrastructure
modules, an operating system kernel, a service manager, and 745+ CLI flags
that can only be administered from the local terminal.  SSH has been the
standard remote administration protocol since 1995.

Architecture reference: OpenSSH 9.6, Dropbear 2024.84, RFC 4253/4254/4256.
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
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum, auto
from typing import Any, Callable, Dict, Iterator, List, Optional, Set, Tuple, Union

from enterprise_fizzbuzz.domain.exceptions.fizzssh import (
    FizzSSHError,
    FizzSSHTransportError,
    FizzSSHPacketError,
    FizzSSHEncryptionError,
    FizzSSHMACError,
    FizzSSHKeyExchangeError,
    FizzSSHHostKeyError,
    FizzSSHHostKeyNotFoundError,
    FizzSSHAuthError,
    FizzSSHAuthPasswordError,
    FizzSSHAuthPublicKeyError,
    FizzSSHAuthKeyboardInteractiveError,
    FizzSSHChannelError,
    FizzSSHChannelOpenError,
    FizzSSHChannelClosedError,
    FizzSSHSessionError,
    FizzSSHPTYError,
    FizzSSHExecError,
    FizzSSHSFTPError,
    FizzSSHSFTPFileNotFoundError,
    FizzSSHSFTPPermissionError,
    FizzSSHPortForwardError,
    FizzSSHSCPError,
    FizzSSHRateLimitError,
    FizzSSHConfigError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzResult,
    ProcessingContext,
)

logger = logging.getLogger("enterprise_fizzbuzz.fizzssh")


# ============================================================
# Event Type Registration
# ============================================================

EVENT_SSH_CONNECTION = EventType.register("FIZZSSH_CONNECTION")
EVENT_SSH_AUTH_SUCCESS = EventType.register("FIZZSSH_AUTH_SUCCESS")
EVENT_SSH_AUTH_FAILURE = EventType.register("FIZZSSH_AUTH_FAILURE")
EVENT_SSH_CHANNEL_OPEN = EventType.register("FIZZSSH_CHANNEL_OPEN")
EVENT_SSH_CHANNEL_CLOSE = EventType.register("FIZZSSH_CHANNEL_CLOSE")
EVENT_SSH_SESSION_START = EventType.register("FIZZSSH_SESSION_START")
EVENT_SSH_SESSION_END = EventType.register("FIZZSSH_SESSION_END")
EVENT_SSH_SFTP_OP = EventType.register("FIZZSSH_SFTP_OP")


# ============================================================
# Constants
# ============================================================

FIZZSSH_VERSION = "1.0.0"
FIZZSSH_SERVER_NAME = f"FizzSSH/{FIZZSSH_VERSION} (Enterprise FizzBuzz Platform)"
FIZZSSH_PROTOCOL_VERSION = "SSH-2.0-FizzSSH_1.0"

DEFAULT_PORT = 2222
DEFAULT_MAX_SESSIONS = 64
DEFAULT_IDLE_TIMEOUT = 1800.0
DEFAULT_RATE_LIMIT = 30  # connections/min/IP
DEFAULT_MAX_CHANNELS = 16
DEFAULT_WINDOW_SIZE = 2097152  # 2 MB
DEFAULT_MAX_PACKET_SIZE = 32768
DEFAULT_DASHBOARD_WIDTH = 72

MIDDLEWARE_PRIORITY = 124

DEFAULT_CREDENTIALS = {
    "root": "fizzbuzz",
    "admin": "admin",
    "operator": "operator",
    "bob": "mcfizzington",
}

# SSH message type constants (RFC 4253)
SSH_MSG_DISCONNECT = 1
SSH_MSG_IGNORE = 2
SSH_MSG_KEXINIT = 20
SSH_MSG_NEWKEYS = 21
SSH_MSG_KEXDH_INIT = 30
SSH_MSG_KEXDH_REPLY = 31
SSH_MSG_USERAUTH_REQUEST = 50
SSH_MSG_USERAUTH_FAILURE = 51
SSH_MSG_USERAUTH_SUCCESS = 52
SSH_MSG_USERAUTH_BANNER = 53
SSH_MSG_CHANNEL_OPEN = 90
SSH_MSG_CHANNEL_OPEN_CONFIRMATION = 91
SSH_MSG_CHANNEL_DATA = 94
SSH_MSG_CHANNEL_EOF = 96
SSH_MSG_CHANNEL_CLOSE = 97
SSH_MSG_CHANNEL_REQUEST = 98

# Supported algorithms
KEX_ALGORITHMS = ["curve25519-sha256", "diffie-hellman-group14-sha256", "diffie-hellman-group16-sha512"]
HOST_KEY_ALGORITHMS = ["ssh-ed25519", "rsa-sha2-512", "rsa-sha2-256"]
CIPHER_ALGORITHMS = ["chacha20-poly1305@openssh.com", "aes256-gcm@openssh.com", "aes256-ctr"]
MAC_ALGORITHMS = ["hmac-sha2-256-etm@openssh.com", "hmac-sha2-512-etm@openssh.com", "hmac-sha2-256"]
COMPRESSION_ALGORITHMS = ["none", "zlib@openssh.com"]


# ============================================================
# Enums
# ============================================================


class SSHConnectionState(Enum):
    """SSH connection lifecycle states."""
    CONNECTED = auto()
    VERSION_EXCHANGED = auto()
    KEX_IN_PROGRESS = auto()
    KEX_COMPLETE = auto()
    AUTHENTICATING = auto()
    AUTHENTICATED = auto()
    ACTIVE = auto()
    DISCONNECTED = auto()


class ChannelState(Enum):
    """SSH channel lifecycle states."""
    OPENING = auto()
    OPEN = auto()
    EOF_SENT = auto()
    EOF_RECEIVED = auto()
    CLOSING = auto()
    CLOSED = auto()


class ChannelType(Enum):
    """SSH channel types per RFC 4254."""
    SESSION = "session"
    DIRECT_TCPIP = "direct-tcpip"
    FORWARDED_TCPIP = "forwarded-tcpip"
    X11 = "x11"


class AuthMethod(Enum):
    """SSH authentication methods per RFC 4252."""
    PASSWORD = "password"
    PUBLIC_KEY = "publickey"
    KEYBOARD_INTERACTIVE = "keyboard-interactive"
    NONE = "none"


class SFTPOperation(Enum):
    """SFTP file operations."""
    OPEN = "open"
    CLOSE = "close"
    READ = "read"
    WRITE = "write"
    STAT = "stat"
    LSTAT = "lstat"
    FSTAT = "fstat"
    OPENDIR = "opendir"
    READDIR = "readdir"
    REMOVE = "remove"
    MKDIR = "mkdir"
    RMDIR = "rmdir"
    RENAME = "rename"
    SYMLINK = "symlink"
    READLINK = "readlink"
    REALPATH = "realpath"


class HostKeyType(Enum):
    """Server host key algorithms."""
    ED25519 = "ssh-ed25519"
    RSA = "ssh-rsa"


# ============================================================
# Dataclasses
# ============================================================


@dataclass
class FizzSSHConfig:
    """Configuration for the FizzSSH server."""
    port: int = DEFAULT_PORT
    host_key_type: str = "ed25519"
    enable_password_auth: bool = True
    enable_pubkey_auth: bool = True
    enable_sftp: bool = True
    enable_port_forwarding: bool = True
    enable_session_recording: bool = True
    max_sessions: int = DEFAULT_MAX_SESSIONS
    max_channels_per_session: int = DEFAULT_MAX_CHANNELS
    idle_timeout: float = DEFAULT_IDLE_TIMEOUT
    rate_limit: int = DEFAULT_RATE_LIMIT
    banner: str = ""
    window_size: int = DEFAULT_WINDOW_SIZE
    max_packet_size: int = DEFAULT_MAX_PACKET_SIZE
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH
    credentials: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_CREDENTIALS))


@dataclass
class KeyPair:
    """SSH key pair (public and private)."""
    algorithm: str = ""
    public_key: str = ""
    private_key: str = ""
    fingerprint: str = ""
    comment: str = ""
    bits: int = 256


@dataclass
class SSHPacket:
    """SSH binary packet per RFC 4253 Section 6."""
    packet_length: int = 0
    padding_length: int = 0
    payload: bytes = b""
    mac: bytes = b""
    sequence_number: int = 0


@dataclass
class SSHSession:
    """SSH connection session state."""
    session_id: str = ""
    client_addr: str = ""
    state: SSHConnectionState = SSHConnectionState.CONNECTED
    authenticated_user: str = ""
    auth_method: AuthMethod = AuthMethod.NONE
    server_version: str = FIZZSSH_PROTOCOL_VERSION
    client_version: str = ""
    session_key: bytes = b""
    kex_algorithm: str = ""
    host_key_algorithm: str = ""
    cipher_algorithm: str = ""
    mac_algorithm: str = ""
    channels: Dict[int, "SSHChannel"] = field(default_factory=dict)
    next_channel_id: int = 0
    connected_at: Optional[datetime] = None
    last_activity: Optional[datetime] = None
    bytes_sent: int = 0
    bytes_received: int = 0
    packets_sent: int = 0
    packets_received: int = 0


@dataclass
class SSHChannel:
    """SSH channel state."""
    channel_id: int = 0
    remote_channel_id: int = 0
    channel_type: ChannelType = ChannelType.SESSION
    state: ChannelState = ChannelState.OPENING
    window_size: int = DEFAULT_WINDOW_SIZE
    max_packet_size: int = DEFAULT_MAX_PACKET_SIZE
    pty_allocated: bool = False
    pty_term: str = "xterm-256color"
    pty_width: int = 80
    pty_height: int = 24
    command: str = ""
    subsystem: str = ""
    environment: Dict[str, str] = field(default_factory=dict)
    data_buffer: List[str] = field(default_factory=list)
    exit_status: int = 0


@dataclass
class PortForward:
    """TCP/IP port forwarding configuration."""
    forward_type: str = "local"  # local, remote
    bind_address: str = "127.0.0.1"
    bind_port: int = 0
    target_address: str = ""
    target_port: int = 0
    active: bool = True


@dataclass
class SFTPFileEntry:
    """SFTP virtual file system entry."""
    name: str = ""
    is_directory: bool = False
    size: int = 0
    permissions: int = 0o644
    owner: str = "root"
    group: str = "fizzbuzz"
    modified_time: float = 0.0
    content: bytes = b""
    children: Dict[str, "SFTPFileEntry"] = field(default_factory=dict)


@dataclass
class SessionRecording:
    """Recorded SSH session for audit replay."""
    session_id: str = ""
    user: str = ""
    client_addr: str = ""
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    events: List[Dict[str, Any]] = field(default_factory=list)
    commands: List[str] = field(default_factory=list)
    bytes_transferred: int = 0


@dataclass
class ServerMetrics:
    """Aggregate SSH server metrics."""
    total_connections: int = 0
    active_sessions: int = 0
    auth_successes: int = 0
    auth_failures: int = 0
    total_channels: int = 0
    sftp_operations: int = 0
    bytes_transferred: int = 0
    commands_executed: int = 0
    port_forwards_active: int = 0
    rate_limited: int = 0
    sessions_recorded: int = 0


# ============================================================
# Host Key Manager
# ============================================================


class HostKeyManager:
    """SSH server host key management.

    Generates and stores Ed25519 and RSA host key pairs using
    simulated cryptographic operations consistent with the
    platform's simulation pattern.
    """

    def __init__(self) -> None:
        self._keys: Dict[str, KeyPair] = {}
        self._generate_default_keys()

    def _generate_default_keys(self) -> None:
        """Generate default host keys."""
        self._keys["ssh-ed25519"] = KeyPair(
            algorithm="ssh-ed25519",
            public_key=base64.b64encode(hashlib.sha256(b"fizzssh-ed25519-host-pub").digest()).decode(),
            private_key=base64.b64encode(hashlib.sha256(b"fizzssh-ed25519-host-priv").digest()).decode(),
            fingerprint=self._compute_fingerprint("ed25519"),
            comment="fizzssh@fizzbuzz.local",
            bits=256,
        )
        self._keys["ssh-rsa"] = KeyPair(
            algorithm="ssh-rsa",
            public_key=base64.b64encode(hashlib.sha256(b"fizzssh-rsa-host-pub").digest()).decode(),
            private_key=base64.b64encode(hashlib.sha256(b"fizzssh-rsa-host-priv").digest()).decode(),
            fingerprint=self._compute_fingerprint("rsa"),
            comment="fizzssh@fizzbuzz.local",
            bits=4096,
        )

    def get_key(self, algorithm: str) -> Optional[KeyPair]:
        """Retrieve a host key by algorithm."""
        return self._keys.get(algorithm)

    def get_fingerprint(self, algorithm: str) -> str:
        """Get the fingerprint for a host key."""
        key = self._keys.get(algorithm)
        return key.fingerprint if key else ""

    def list_keys(self) -> List[KeyPair]:
        """List all host keys."""
        return list(self._keys.values())

    def _compute_fingerprint(self, key_type: str) -> str:
        """Compute a SHA-256 fingerprint for a host key."""
        digest = hashlib.sha256(f"fizzssh-{key_type}-fingerprint".encode()).digest()
        hex_str = ":".join(f"{b:02x}" for b in digest[:16])
        return f"SHA256:{base64.b64encode(digest[:16]).decode().rstrip('=')}"


# ============================================================
# Authorized Keys Store
# ============================================================


class AuthorizedKeysStore:
    """Public key authentication authorized_keys store.

    Manages authorized public keys per user for SSH public key
    authentication.
    """

    def __init__(self) -> None:
        self._keys: Dict[str, List[KeyPair]] = {}
        self._initialize_defaults()

    def _initialize_defaults(self) -> None:
        """Initialize default authorized keys for system users."""
        for user in DEFAULT_CREDENTIALS:
            key = KeyPair(
                algorithm="ssh-ed25519",
                public_key=base64.b64encode(
                    hashlib.sha256(f"fizzssh-{user}-pubkey".encode()).digest()
                ).decode(),
                fingerprint=f"SHA256:{base64.b64encode(hashlib.sha256(f'{user}-fp'.encode()).digest()[:16]).decode().rstrip('=')}",
                comment=f"{user}@fizzbuzz.local",
                bits=256,
            )
            self._keys[user] = [key]

    def get_keys(self, user: str) -> List[KeyPair]:
        """Get authorized keys for a user."""
        return self._keys.get(user, [])

    def add_key(self, user: str, key: KeyPair) -> None:
        """Add an authorized key for a user."""
        if user not in self._keys:
            self._keys[user] = []
        self._keys[user].append(key)

    def remove_key(self, user: str, fingerprint: str) -> bool:
        """Remove an authorized key by fingerprint."""
        keys = self._keys.get(user, [])
        for i, key in enumerate(keys):
            if key.fingerprint == fingerprint:
                keys.pop(i)
                return True
        return False

    def verify_key(self, user: str, public_key: str) -> bool:
        """Verify if a public key is authorized for a user."""
        for key in self._keys.get(user, []):
            if key.public_key == public_key:
                return True
        return False

    def list_all(self) -> Dict[str, List[KeyPair]]:
        """List all authorized keys grouped by user."""
        return dict(self._keys)


# ============================================================
# Key Exchange
# ============================================================


class KeyExchange:
    """SSH key exchange protocol implementation.

    Simulates Diffie-Hellman group exchange and ECDH with
    Curve25519 for session key derivation.
    """

    def __init__(self, host_key_manager: HostKeyManager) -> None:
        self._host_keys = host_key_manager

    def perform_kex(self, session: SSHSession, algorithm: str = "curve25519-sha256") -> bytes:
        """Perform key exchange and return the session key.

        Simulates the key exchange process using deterministic
        key derivation from the session ID and algorithm.
        """
        session.kex_algorithm = algorithm

        if algorithm.startswith("curve25519"):
            return self._kex_curve25519(session)
        elif algorithm.startswith("diffie-hellman"):
            return self._kex_dh(session, algorithm)
        else:
            raise FizzSSHKeyExchangeError(f"Unsupported KEX algorithm: {algorithm}")

    def _kex_curve25519(self, session: SSHSession) -> bytes:
        """Simulate ECDH-Curve25519 key exchange."""
        # Generate ephemeral key pair (simulated)
        client_ephemeral = hashlib.sha256(f"client-eph-{session.session_id}".encode()).digest()
        server_ephemeral = hashlib.sha256(f"server-eph-{session.session_id}".encode()).digest()

        # Compute shared secret (simulated ECDH)
        shared_secret = hashlib.sha256(client_ephemeral + server_ephemeral).digest()

        # Derive session key
        session_key = hashlib.sha256(
            shared_secret + session.session_id.encode()
        ).digest()

        logger.debug("ECDH-Curve25519 key exchange completed: session=%s", session.session_id)
        return session_key

    def _kex_dh(self, session: SSHSession, algorithm: str) -> bytes:
        """Simulate Diffie-Hellman group key exchange."""
        # Simulated DH parameters
        if "group14" in algorithm:
            group_size = 2048
        elif "group16" in algorithm:
            group_size = 4096
        else:
            group_size = 2048

        # Generate DH key pair (simulated)
        private = hashlib.sha256(f"dh-priv-{session.session_id}-{group_size}".encode()).digest()
        public = hashlib.sha256(f"dh-pub-{session.session_id}-{group_size}".encode()).digest()

        # Compute shared secret
        shared = hashlib.sha256(private + public).digest()
        session_key = hashlib.sha256(shared + f"{group_size}".encode()).digest()

        logger.debug("DH group exchange completed: group=%d session=%s", group_size, session.session_id)
        return session_key


# ============================================================
# Client Authenticator
# ============================================================


class ClientAuthenticator:
    """SSH client authentication handler.

    Implements password, public key, and keyboard-interactive
    authentication methods per RFC 4252.
    """

    def __init__(self, config: FizzSSHConfig,
                 authorized_keys: AuthorizedKeysStore) -> None:
        self._config = config
        self._authorized_keys = authorized_keys

    def authenticate(self, session: SSHSession, method: AuthMethod,
                     username: str, credentials: Dict[str, Any]) -> bool:
        """Attempt authentication with the given method and credentials."""
        if method == AuthMethod.PASSWORD:
            return self._auth_password(username, credentials.get("password", ""))
        elif method == AuthMethod.PUBLIC_KEY:
            return self._auth_public_key(username, credentials.get("public_key", ""))
        elif method == AuthMethod.KEYBOARD_INTERACTIVE:
            return self._auth_keyboard_interactive(username, credentials.get("responses", []))
        return False

    def get_supported_methods(self, username: str) -> List[AuthMethod]:
        """Return supported authentication methods for a user."""
        methods = []
        if self._config.enable_password_auth:
            methods.append(AuthMethod.PASSWORD)
        if self._config.enable_pubkey_auth:
            methods.append(AuthMethod.PUBLIC_KEY)
        methods.append(AuthMethod.KEYBOARD_INTERACTIVE)
        return methods

    def _auth_password(self, username: str, password: str) -> bool:
        """Authenticate using password."""
        stored = self._config.credentials.get(username)
        if stored is None:
            return False
        return hmac.compare_digest(stored, password)

    def _auth_public_key(self, username: str, public_key: str) -> bool:
        """Authenticate using public key."""
        return self._authorized_keys.verify_key(username, public_key)

    def _auth_keyboard_interactive(self, username: str,
                                    responses: List[str]) -> bool:
        """Authenticate using keyboard-interactive (password fallback)."""
        if responses and len(responses) >= 1:
            return self._auth_password(username, responses[0])
        return False


# ============================================================
# SFTP Subsystem
# ============================================================


class SFTPSubsystem:
    """SFTP file operations subsystem.

    Provides a virtual file system for SFTP operations including
    directory listing, file read/write, stat, rename, and remove.
    """

    def __init__(self, config: FizzSSHConfig) -> None:
        self._config = config
        self._fs: Dict[str, SFTPFileEntry] = {}
        self._initialize_filesystem()
        self._op_count = 0

    def _initialize_filesystem(self) -> None:
        """Initialize the virtual filesystem with default structure."""
        now = time.time()

        # Root directories
        for dirname in ["/", "/home", "/etc", "/var", "/var/log", "/tmp",
                       "/home/root", "/home/admin", "/home/operator", "/home/bob"]:
            self._fs[dirname] = SFTPFileEntry(
                name=dirname.split("/")[-1] or "/",
                is_directory=True,
                permissions=0o755,
                modified_time=now,
            )

        # Config files
        self._fs["/etc/fizzbuzz.conf"] = SFTPFileEntry(
            name="fizzbuzz.conf",
            size=1024,
            permissions=0o644,
            modified_time=now,
            content=b"# Enterprise FizzBuzz Platform Configuration\n# 139 infrastructure modules\nversion: 1.0.0\n",
        )

        self._fs["/etc/ssh/sshd_config"] = SFTPFileEntry(
            name="sshd_config",
            size=512,
            permissions=0o600,
            modified_time=now,
            content=b"Port 2222\nPermitRootLogin yes\nPubkeyAuthentication yes\nPasswordAuthentication yes\n",
        )

        # Log files
        self._fs["/var/log/fizzbuzz.log"] = SFTPFileEntry(
            name="fizzbuzz.log",
            size=4096,
            permissions=0o644,
            modified_time=now,
            content=b"[INFO] Enterprise FizzBuzz Platform started\n[INFO] 139 infrastructure modules loaded\n",
        )

        # Ensure parent directories exist for nested paths
        for path in list(self._fs.keys()):
            parts = path.split("/")
            for i in range(2, len(parts)):
                parent = "/".join(parts[:i]) or "/"
                if parent not in self._fs:
                    self._fs[parent] = SFTPFileEntry(
                        name=parts[i-1], is_directory=True,
                        permissions=0o755, modified_time=now,
                    )

    def stat(self, path: str) -> Optional[Dict[str, Any]]:
        """Get file attributes."""
        self._op_count += 1
        entry = self._fs.get(path)
        if entry is None:
            raise FizzSSHSFTPFileNotFoundError(path)

        return {
            "name": entry.name,
            "size": entry.size,
            "permissions": entry.permissions,
            "is_directory": entry.is_directory,
            "owner": entry.owner,
            "group": entry.group,
            "modified_time": entry.modified_time,
        }

    def opendir(self, path: str) -> List[Dict[str, Any]]:
        """List directory contents."""
        self._op_count += 1
        entry = self._fs.get(path)
        if entry is None:
            raise FizzSSHSFTPFileNotFoundError(path)
        if not entry.is_directory:
            raise FizzSSHSFTPError(f"Not a directory: {path}")

        # Find children
        prefix = path.rstrip("/") + "/"
        children = []
        for child_path, child_entry in self._fs.items():
            if child_path.startswith(prefix) and "/" not in child_path[len(prefix):]:
                children.append({
                    "name": child_entry.name,
                    "path": child_path,
                    "size": child_entry.size,
                    "is_directory": child_entry.is_directory,
                    "permissions": child_entry.permissions,
                })

        return children

    def read(self, path: str) -> bytes:
        """Read file contents."""
        self._op_count += 1
        entry = self._fs.get(path)
        if entry is None:
            raise FizzSSHSFTPFileNotFoundError(path)
        if entry.is_directory:
            raise FizzSSHSFTPError(f"Is a directory: {path}")
        return entry.content

    def write(self, path: str, content: bytes) -> int:
        """Write file contents."""
        self._op_count += 1
        parent = "/".join(path.split("/")[:-1]) or "/"
        if parent not in self._fs:
            raise FizzSSHSFTPFileNotFoundError(parent)

        name = path.split("/")[-1]
        self._fs[path] = SFTPFileEntry(
            name=name,
            size=len(content),
            permissions=0o644,
            modified_time=time.time(),
            content=content,
        )
        return len(content)

    def mkdir(self, path: str) -> None:
        """Create a directory."""
        self._op_count += 1
        if path in self._fs:
            raise FizzSSHSFTPError(f"Already exists: {path}")

        name = path.split("/")[-1]
        self._fs[path] = SFTPFileEntry(
            name=name,
            is_directory=True,
            permissions=0o755,
            modified_time=time.time(),
        )

    def rmdir(self, path: str) -> None:
        """Remove a directory."""
        self._op_count += 1
        entry = self._fs.get(path)
        if entry is None:
            raise FizzSSHSFTPFileNotFoundError(path)
        if not entry.is_directory:
            raise FizzSSHSFTPError(f"Not a directory: {path}")
        del self._fs[path]

    def remove(self, path: str) -> None:
        """Remove a file."""
        self._op_count += 1
        entry = self._fs.get(path)
        if entry is None:
            raise FizzSSHSFTPFileNotFoundError(path)
        if entry.is_directory:
            raise FizzSSHSFTPError(f"Is a directory: {path}")
        del self._fs[path]

    def rename(self, old_path: str, new_path: str) -> None:
        """Rename a file or directory."""
        self._op_count += 1
        entry = self._fs.get(old_path)
        if entry is None:
            raise FizzSSHSFTPFileNotFoundError(old_path)
        self._fs[new_path] = entry
        entry.name = new_path.split("/")[-1]
        del self._fs[old_path]

    @property
    def operation_count(self) -> int:
        """Total SFTP operations performed."""
        return self._op_count


# ============================================================
# Port Forwarder
# ============================================================


class PortForwarder:
    """TCP/IP port forwarding manager.

    Manages local and remote port forwarding tunnels for SSH
    sessions, simulating the forwarding plane.
    """

    def __init__(self, config: FizzSSHConfig) -> None:
        self._config = config
        self._forwards: Dict[str, PortForward] = {}

    def add_local_forward(self, session_id: str, bind_addr: str, bind_port: int,
                          target_addr: str, target_port: int) -> str:
        """Add a local port forward (-L)."""
        if not self._config.enable_port_forwarding:
            raise FizzSSHPortForwardError("Port forwarding is disabled")

        forward_id = f"{session_id}:L:{bind_port}"
        self._forwards[forward_id] = PortForward(
            forward_type="local",
            bind_address=bind_addr,
            bind_port=bind_port,
            target_address=target_addr,
            target_port=target_port,
        )
        logger.debug("Local forward: %s:%d -> %s:%d", bind_addr, bind_port, target_addr, target_port)
        return forward_id

    def add_remote_forward(self, session_id: str, bind_addr: str, bind_port: int,
                           target_addr: str, target_port: int) -> str:
        """Add a remote port forward (-R)."""
        if not self._config.enable_port_forwarding:
            raise FizzSSHPortForwardError("Port forwarding is disabled")

        forward_id = f"{session_id}:R:{bind_port}"
        self._forwards[forward_id] = PortForward(
            forward_type="remote",
            bind_address=bind_addr,
            bind_port=bind_port,
            target_address=target_addr,
            target_port=target_port,
        )
        logger.debug("Remote forward: %s:%d -> %s:%d", bind_addr, bind_port, target_addr, target_port)
        return forward_id

    def remove_forward(self, forward_id: str) -> bool:
        """Remove a port forward."""
        return self._forwards.pop(forward_id, None) is not None

    def list_forwards(self, session_id: str = "") -> List[PortForward]:
        """List active port forwards."""
        if session_id:
            return [f for fid, f in self._forwards.items() if fid.startswith(session_id)]
        return list(self._forwards.values())

    @property
    def active_count(self) -> int:
        """Number of active port forwards."""
        return len(self._forwards)


# ============================================================
# Session Recorder
# ============================================================


class SessionRecorder:
    """SSH session recording and audit logging.

    Records all session events (authentication, commands, data
    transfer) for compliance auditing and security review.
    """

    def __init__(self, config: FizzSSHConfig) -> None:
        self._config = config
        self._recordings: Dict[str, SessionRecording] = {}

    def start_recording(self, session: SSHSession) -> None:
        """Start recording a session."""
        if not self._config.enable_session_recording:
            return

        self._recordings[session.session_id] = SessionRecording(
            session_id=session.session_id,
            user=session.authenticated_user,
            client_addr=session.client_addr,
            started_at=datetime.now(timezone.utc),
        )

    def record_event(self, session_id: str, event_type: str,
                     data: Optional[Dict[str, Any]] = None) -> None:
        """Record a session event."""
        recording = self._recordings.get(session_id)
        if recording is None:
            return

        recording.events.append({
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data or {},
        })

    def record_command(self, session_id: str, command: str) -> None:
        """Record a command executed in a session."""
        recording = self._recordings.get(session_id)
        if recording:
            recording.commands.append(command)

    def end_recording(self, session_id: str) -> Optional[SessionRecording]:
        """End a session recording and return it."""
        recording = self._recordings.get(session_id)
        if recording:
            recording.ended_at = datetime.now(timezone.utc)
        return recording

    def get_recording(self, session_id: str) -> Optional[SessionRecording]:
        """Retrieve a recording by session ID."""
        return self._recordings.get(session_id)

    def list_recordings(self) -> List[SessionRecording]:
        """List all recordings."""
        return list(self._recordings.values())

    @property
    def recording_count(self) -> int:
        """Number of recorded sessions."""
        return len(self._recordings)


# ============================================================
# Connection Rate Limiter
# ============================================================


class ConnectionRateLimiter:
    """Per-IP connection rate limiter for SSH.

    Tracks connection attempts per IP address and rejects
    connections that exceed the configured rate limit.
    """

    def __init__(self, config: FizzSSHConfig) -> None:
        self._config = config
        self._attempts: Dict[str, List[float]] = defaultdict(list)
        self._blocked_count = 0

    def check(self, client_addr: str) -> bool:
        """Check if a connection from this IP should be allowed.

        Returns True if allowed, False if rate-limited.
        """
        now = time.time()
        window = 60.0  # 1 minute window

        # Clean old entries
        attempts = self._attempts[client_addr]
        self._attempts[client_addr] = [t for t in attempts if now - t < window]

        if len(self._attempts[client_addr]) >= self._config.rate_limit:
            self._blocked_count += 1
            return False

        self._attempts[client_addr].append(now)
        return True

    @property
    def blocked_count(self) -> int:
        """Number of rate-limited connections."""
        return self._blocked_count


# ============================================================
# SSH Server
# ============================================================


class SSHServer:
    """SSH-2 protocol server.

    Processes SSH connections through the complete protocol lifecycle:
    version exchange, key exchange, authentication, and channel
    operations.  All network I/O is simulated.
    """

    def __init__(self, config: FizzSSHConfig,
                 host_key_manager: HostKeyManager,
                 key_exchange: KeyExchange,
                 authenticator: ClientAuthenticator,
                 sftp: SFTPSubsystem,
                 port_forwarder: PortForwarder,
                 session_recorder: SessionRecorder,
                 rate_limiter: ConnectionRateLimiter) -> None:
        self._config = config
        self._host_keys = host_key_manager
        self._kex = key_exchange
        self._auth = authenticator
        self._sftp = sftp
        self._port_forwarder = port_forwarder
        self._recorder = session_recorder
        self._rate_limiter = rate_limiter
        self._metrics = ServerMetrics()
        self._sessions: Dict[str, SSHSession] = {}
        self._started = False
        self._start_time = 0.0

    def start(self) -> None:
        """Start the SSH server."""
        self._started = True
        self._start_time = time.time()
        logger.info("SSH server started on port %d", self._config.port)

    def handle_connection(self, client_addr: str,
                          commands: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Process an SSH connection with a sequence of operations.

        Each command is a dict with 'type' and operation-specific fields.
        Returns a list of response dicts.
        """
        # Rate limit check
        if not self._rate_limiter.check(client_addr):
            self._metrics.rate_limited += 1
            return [{"type": "error", "message": "Connection rate limited"}]

        session = SSHSession(
            session_id=uuid.uuid4().hex[:12],
            client_addr=client_addr,
            state=SSHConnectionState.CONNECTED,
            connected_at=datetime.now(timezone.utc),
            last_activity=datetime.now(timezone.utc),
        )
        self._sessions[session.session_id] = session
        self._metrics.total_connections += 1
        self._metrics.active_sessions += 1

        responses = []

        # Version exchange
        responses.append({
            "type": "version",
            "server_version": FIZZSSH_PROTOCOL_VERSION,
            "session_id": session.session_id,
        })
        session.state = SSHConnectionState.VERSION_EXCHANGED

        # Key exchange
        try:
            session_key = self._kex.perform_kex(session)
            session.session_key = session_key
            session.host_key_algorithm = HOST_KEY_ALGORITHMS[0]
            session.cipher_algorithm = CIPHER_ALGORITHMS[0]
            session.mac_algorithm = MAC_ALGORITHMS[0]
            session.state = SSHConnectionState.KEX_COMPLETE

            host_key = self._host_keys.get_key(HOST_KEY_ALGORITHMS[0])
            responses.append({
                "type": "kex_complete",
                "algorithm": session.kex_algorithm,
                "host_key_fingerprint": host_key.fingerprint if host_key else "",
                "cipher": session.cipher_algorithm,
                "mac": session.mac_algorithm,
            })
        except FizzSSHKeyExchangeError as e:
            responses.append({"type": "error", "message": str(e)})
            self._cleanup_session(session)
            return responses

        # Send banner if configured
        if self._config.banner:
            responses.append({
                "type": "banner",
                "message": self._config.banner,
            })

        session.state = SSHConnectionState.AUTHENTICATING

        # Process commands
        for cmd in commands:
            response = self._process_command(session, cmd)
            responses.append(response)
            session.last_activity = datetime.now(timezone.utc)

            if session.state == SSHConnectionState.DISCONNECTED:
                break

        # Cleanup
        self._cleanup_session(session)
        return responses

    def _process_command(self, session: SSHSession,
                         cmd: Dict[str, Any]) -> Dict[str, Any]:
        """Process a single command in the session."""
        cmd_type = cmd.get("type", "")

        if cmd_type == "auth":
            return self._handle_auth(session, cmd)
        elif cmd_type == "channel_open":
            return self._handle_channel_open(session, cmd)
        elif cmd_type == "exec":
            return self._handle_exec(session, cmd)
        elif cmd_type == "shell":
            return self._handle_shell(session, cmd)
        elif cmd_type == "pty":
            return self._handle_pty(session, cmd)
        elif cmd_type == "sftp":
            return self._handle_sftp(session, cmd)
        elif cmd_type == "port_forward":
            return self._handle_port_forward(session, cmd)
        elif cmd_type == "scp_upload":
            return self._handle_scp_upload(session, cmd)
        elif cmd_type == "scp_download":
            return self._handle_scp_download(session, cmd)
        elif cmd_type == "disconnect":
            return self._handle_disconnect(session)
        else:
            return {"type": "error", "message": f"Unknown command: {cmd_type}"}

    def _handle_auth(self, session: SSHSession,
                     cmd: Dict[str, Any]) -> Dict[str, Any]:
        """Handle authentication request."""
        method_str = cmd.get("method", "password")
        username = cmd.get("username", "")
        credentials = cmd.get("credentials", {})

        try:
            method = AuthMethod(method_str)
        except ValueError:
            method = AuthMethod.PASSWORD

        success = self._auth.authenticate(session, method, username, credentials)

        if success:
            session.authenticated_user = username
            session.auth_method = method
            session.state = SSHConnectionState.AUTHENTICATED
            self._metrics.auth_successes += 1
            self._recorder.start_recording(session)
            self._recorder.record_event(session.session_id, "auth_success",
                                         {"user": username, "method": method_str})
            return {
                "type": "auth_success",
                "username": username,
                "method": method_str,
            }
        else:
            self._metrics.auth_failures += 1
            supported = [m.value for m in self._auth.get_supported_methods(username)]
            return {
                "type": "auth_failure",
                "message": "Authentication failed",
                "supported_methods": supported,
            }

    def _handle_channel_open(self, session: SSHSession,
                              cmd: Dict[str, Any]) -> Dict[str, Any]:
        """Handle channel open request."""
        if session.state not in (SSHConnectionState.AUTHENTICATED, SSHConnectionState.ACTIVE):
            return {"type": "error", "message": "Not authenticated"}

        channel_type_str = cmd.get("channel_type", "session")
        try:
            channel_type = ChannelType(channel_type_str)
        except ValueError:
            return {"type": "error", "message": f"Unknown channel type: {channel_type_str}"}

        if len(session.channels) >= self._config.max_channels_per_session:
            return {"type": "error", "message": "Maximum channels reached"}

        channel_id = session.next_channel_id
        session.next_channel_id += 1

        channel = SSHChannel(
            channel_id=channel_id,
            channel_type=channel_type,
            state=ChannelState.OPEN,
            window_size=self._config.window_size,
            max_packet_size=self._config.max_packet_size,
        )
        session.channels[channel_id] = channel
        session.state = SSHConnectionState.ACTIVE
        self._metrics.total_channels += 1

        self._recorder.record_event(session.session_id, "channel_open",
                                     {"channel_id": channel_id, "type": channel_type_str})

        return {
            "type": "channel_open_confirmation",
            "channel_id": channel_id,
            "channel_type": channel_type_str,
            "window_size": channel.window_size,
        }

    def _handle_exec(self, session: SSHSession,
                     cmd: Dict[str, Any]) -> Dict[str, Any]:
        """Handle remote command execution."""
        channel_id = cmd.get("channel_id", 0)
        command = cmd.get("command", "")

        channel = session.channels.get(channel_id)
        if channel is None:
            return {"type": "error", "message": f"Channel {channel_id} not found"}

        self._recorder.record_command(session.session_id, command)
        self._metrics.commands_executed += 1

        # Simulate command execution
        output = self._execute_command(command, session)

        return {
            "type": "exec_result",
            "channel_id": channel_id,
            "command": command,
            "output": output,
            "exit_status": 0,
        }

    def _handle_shell(self, session: SSHSession,
                      cmd: Dict[str, Any]) -> Dict[str, Any]:
        """Handle interactive shell request."""
        channel_id = cmd.get("channel_id", 0)
        channel = session.channels.get(channel_id)
        if channel is None:
            return {"type": "error", "message": f"Channel {channel_id} not found"}

        # Simulate shell prompt
        user = session.authenticated_user
        prompt = f"{user}@fizzbuzz:~$ "

        shell_commands = cmd.get("input", [])
        output_lines = [f"Welcome to {FIZZSSH_SERVER_NAME}", f"Last login: {datetime.now(timezone.utc).strftime('%c')}", ""]

        for shell_cmd in shell_commands:
            self._recorder.record_command(session.session_id, shell_cmd)
            self._metrics.commands_executed += 1
            output_lines.append(f"{prompt}{shell_cmd}")
            output_lines.append(self._execute_command(shell_cmd, session))

        output_lines.append(f"{prompt}exit")
        output_lines.append("logout")

        return {
            "type": "shell_output",
            "channel_id": channel_id,
            "output": "\n".join(output_lines),
        }

    def _handle_pty(self, session: SSHSession,
                    cmd: Dict[str, Any]) -> Dict[str, Any]:
        """Handle PTY allocation request."""
        channel_id = cmd.get("channel_id", 0)
        channel = session.channels.get(channel_id)
        if channel is None:
            return {"type": "error", "message": f"Channel {channel_id} not found"}

        channel.pty_allocated = True
        channel.pty_term = cmd.get("term", "xterm-256color")
        channel.pty_width = cmd.get("width", 80)
        channel.pty_height = cmd.get("height", 24)

        return {
            "type": "pty_allocated",
            "channel_id": channel_id,
            "term": channel.pty_term,
            "width": channel.pty_width,
            "height": channel.pty_height,
        }

    def _handle_sftp(self, session: SSHSession,
                     cmd: Dict[str, Any]) -> Dict[str, Any]:
        """Handle SFTP operation."""
        if not self._config.enable_sftp:
            return {"type": "error", "message": "SFTP is disabled"}

        operation = cmd.get("operation", "")
        path = cmd.get("path", "")

        self._metrics.sftp_operations += 1
        self._recorder.record_event(session.session_id, "sftp",
                                     {"operation": operation, "path": path})

        try:
            if operation == "stat":
                result = self._sftp.stat(path)
                return {"type": "sftp_result", "operation": "stat", "data": result}
            elif operation == "ls" or operation == "opendir":
                result = self._sftp.opendir(path)
                return {"type": "sftp_result", "operation": "ls", "entries": result}
            elif operation == "read":
                data = self._sftp.read(path)
                self._metrics.bytes_transferred += len(data)
                return {"type": "sftp_result", "operation": "read", "data": data.decode("utf-8", errors="replace"), "size": len(data)}
            elif operation == "write":
                content = cmd.get("content", "").encode("utf-8")
                size = self._sftp.write(path, content)
                self._metrics.bytes_transferred += size
                return {"type": "sftp_result", "operation": "write", "size": size}
            elif operation == "mkdir":
                self._sftp.mkdir(path)
                return {"type": "sftp_result", "operation": "mkdir", "path": path}
            elif operation == "rmdir":
                self._sftp.rmdir(path)
                return {"type": "sftp_result", "operation": "rmdir", "path": path}
            elif operation == "remove":
                self._sftp.remove(path)
                return {"type": "sftp_result", "operation": "remove", "path": path}
            elif operation == "rename":
                new_path = cmd.get("new_path", "")
                self._sftp.rename(path, new_path)
                return {"type": "sftp_result", "operation": "rename", "old": path, "new": new_path}
            else:
                return {"type": "error", "message": f"Unknown SFTP operation: {operation}"}
        except FizzSSHSFTPFileNotFoundError:
            return {"type": "sftp_error", "message": f"No such file: {path}"}
        except FizzSSHSFTPError as e:
            return {"type": "sftp_error", "message": str(e)}

    def _handle_port_forward(self, session: SSHSession,
                              cmd: Dict[str, Any]) -> Dict[str, Any]:
        """Handle port forwarding request."""
        direction = cmd.get("direction", "local")
        bind_addr = cmd.get("bind_address", "127.0.0.1")
        bind_port = cmd.get("bind_port", 0)
        target_addr = cmd.get("target_address", "")
        target_port = cmd.get("target_port", 0)

        try:
            if direction == "local":
                fwd_id = self._port_forwarder.add_local_forward(
                    session.session_id, bind_addr, bind_port, target_addr, target_port
                )
            else:
                fwd_id = self._port_forwarder.add_remote_forward(
                    session.session_id, bind_addr, bind_port, target_addr, target_port
                )
            self._metrics.port_forwards_active = self._port_forwarder.active_count
            return {
                "type": "port_forward_success",
                "forward_id": fwd_id,
                "direction": direction,
                "bind": f"{bind_addr}:{bind_port}",
                "target": f"{target_addr}:{target_port}",
            }
        except FizzSSHPortForwardError as e:
            return {"type": "error", "message": str(e)}

    def _handle_scp_upload(self, session: SSHSession,
                           cmd: Dict[str, Any]) -> Dict[str, Any]:
        """Handle SCP upload."""
        path = cmd.get("path", "")
        content = cmd.get("content", "").encode("utf-8")
        size = self._sftp.write(path, content)
        self._metrics.bytes_transferred += size
        self._recorder.record_event(session.session_id, "scp_upload",
                                     {"path": path, "size": size})
        return {"type": "scp_result", "operation": "upload", "path": path, "size": size}

    def _handle_scp_download(self, session: SSHSession,
                              cmd: Dict[str, Any]) -> Dict[str, Any]:
        """Handle SCP download."""
        path = cmd.get("path", "")
        try:
            data = self._sftp.read(path)
            self._metrics.bytes_transferred += len(data)
            return {"type": "scp_result", "operation": "download", "path": path,
                    "data": data.decode("utf-8", errors="replace"), "size": len(data)}
        except FizzSSHSFTPFileNotFoundError:
            return {"type": "error", "message": f"No such file: {path}"}

    def _handle_disconnect(self, session: SSHSession) -> Dict[str, Any]:
        """Handle disconnect."""
        session.state = SSHConnectionState.DISCONNECTED
        self._recorder.record_event(session.session_id, "disconnect")
        self._recorder.end_recording(session.session_id)
        return {"type": "disconnected", "session_id": session.session_id}

    def _execute_command(self, command: str, session: SSHSession) -> str:
        """Simulate command execution and return output."""
        cmd = command.strip()
        if not cmd:
            return ""

        parts = cmd.split()
        binary = parts[0]

        if binary == "whoami":
            return session.authenticated_user
        elif binary == "hostname":
            return "fizzbuzz.local"
        elif binary == "uname":
            return "FizzBuzz 1.0.0 fizzbuzz.local 6.1.0-fizzbuzz x86_64 GNU/Linux"
        elif binary == "uptime":
            return f" {datetime.now().strftime('%H:%M:%S')} up 42 days, 3:14, 1 user, load average: 94.70, 94.70, 94.70"
        elif binary == "ls":
            target = parts[1] if len(parts) > 1 else "/home/" + session.authenticated_user
            try:
                entries = self._sftp.opendir(target)
                return "\n".join(e["name"] for e in entries)
            except Exception:
                return f"ls: cannot access '{target}': No such file or directory"
        elif binary == "cat":
            if len(parts) > 1:
                try:
                    data = self._sftp.read(parts[1])
                    return data.decode("utf-8", errors="replace")
                except Exception:
                    return f"cat: {parts[1]}: No such file or directory"
            return ""
        elif binary == "pwd":
            return f"/home/{session.authenticated_user}"
        elif binary == "id":
            return f"uid=0({session.authenticated_user}) gid=0(fizzbuzz) groups=0(fizzbuzz)"
        elif binary == "date":
            return datetime.now(timezone.utc).strftime("%a %b %d %H:%M:%S UTC %Y")
        elif binary == "fizzbuzz":
            args = parts[1:]
            n = int(args[0]) if args else 15
            if n % 15 == 0:
                return "FizzBuzz"
            elif n % 3 == 0:
                return "Fizz"
            elif n % 5 == 0:
                return "Buzz"
            return str(n)
        elif binary == "ps":
            return "  PID TTY          TIME CMD\n    1 ?        00:00:00 fizzsystemd\n  139 ?        00:42:00 fizzbuzz\n  140 pts/0    00:00:00 fizzssh\n  141 pts/0    00:00:00 ps"
        elif binary == "df":
            return "Filesystem     1K-blocks    Used Available Use% Mounted on\nfizzvfs        104857600 5242880  99614720   5% /"
        elif binary == "free":
            return "              total        used        free      shared  buff/cache   available\nMem:      104857600    52428800    26214400     1048576    26214400    51380224"
        elif binary == "exit" or binary == "logout":
            return ""
        else:
            return f"{binary}: command executed (simulated)"

    def _cleanup_session(self, session: SSHSession) -> None:
        """Clean up a session's resources."""
        session.state = SSHConnectionState.DISCONNECTED
        self._sessions.pop(session.session_id, None)
        self._metrics.active_sessions = max(0, self._metrics.active_sessions - 1)

        # Clean up port forwards
        for fwd in self._port_forwarder.list_forwards(session.session_id):
            pass  # Forwards are keyed by session_id prefix

        self._recorder.end_recording(session.session_id)
        self._metrics.sessions_recorded = self._recorder.recording_count

    def get_metrics(self) -> ServerMetrics:
        """Return current server metrics."""
        return copy.copy(self._metrics)

    @property
    def uptime(self) -> float:
        return time.time() - self._start_time if self._started else 0.0

    @property
    def is_running(self) -> bool:
        return self._started


# ============================================================
# Dashboard
# ============================================================


class FizzSSHDashboard:
    """ASCII dashboard for FizzSSH server status display."""

    def __init__(self, server: SSHServer, host_keys: HostKeyManager,
                 sftp: SFTPSubsystem, port_forwarder: PortForwarder,
                 session_recorder: SessionRecorder,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._server = server
        self._host_keys = host_keys
        self._sftp = sftp
        self._port_fwd = port_forwarder
        self._recorder = session_recorder
        self._width = width

    def render(self) -> str:
        sections = [
            self._render_header(),
            self._render_server_status(),
            self._render_host_keys(),
            self._render_session_stats(),
            self._render_sftp_stats(),
        ]
        return "\n".join(sections)

    def _render_header(self) -> str:
        line = "=" * self._width
        title = "FizzSSH Server Dashboard".center(self._width)
        return f"{line}\n{title}\n{line}"

    def _render_server_status(self) -> str:
        m = self._server.get_metrics()
        return "\n".join([
            f"  Server ({FIZZSSH_VERSION})",
            f"  {'─' * (self._width - 4)}",
            f"  Status:           {'RUNNING' if self._server.is_running else 'STOPPED'}",
            f"  Protocol:         {FIZZSSH_PROTOCOL_VERSION}",
            f"  Uptime:           {self._server.uptime:.1f}s",
            f"  Connections:      {m.total_connections}",
            f"  Active Sessions:  {m.active_sessions}",
            f"  Auth OK/Fail:     {m.auth_successes}/{m.auth_failures}",
            f"  Rate Limited:     {m.rate_limited}",
        ])

    def _render_host_keys(self) -> str:
        lines = [
            f"  Host Keys",
            f"  {'─' * (self._width - 4)}",
        ]
        for key in self._host_keys.list_keys():
            lines.append(f"  {key.algorithm:<20} {key.bits} bits  {key.fingerprint}")
        return "\n".join(lines)

    def _render_session_stats(self) -> str:
        m = self._server.get_metrics()
        return "\n".join([
            f"  Sessions & Channels",
            f"  {'─' * (self._width - 4)}",
            f"  Total Channels:   {m.total_channels}",
            f"  Commands Exec:    {m.commands_executed}",
            f"  Port Forwards:    {m.port_forwards_active}",
            f"  Bytes Xfer:       {m.bytes_transferred}",
            f"  Recordings:       {m.sessions_recorded}",
        ])

    def _render_sftp_stats(self) -> str:
        m = self._server.get_metrics()
        return "\n".join([
            f"  SFTP Subsystem",
            f"  {'─' * (self._width - 4)}",
            f"  Operations:       {m.sftp_operations}",
            f"  VFS Entries:      {len(self._sftp._fs)}",
        ])


# ============================================================
# Middleware
# ============================================================


class FizzSSHMiddleware(IMiddleware):
    """Middleware integration for the FizzSSH server."""

    def __init__(self, server: SSHServer, dashboard: FizzSSHDashboard,
                 authorized_keys: AuthorizedKeysStore,
                 config: FizzSSHConfig) -> None:
        self._server = server
        self._dashboard = dashboard
        self._authorized_keys = authorized_keys
        self._config = config

    def get_name(self) -> str:
        return "fizzssh"

    def process(self, context: ProcessingContext, next_handler: Any) -> ProcessingContext:
        m = self._server.get_metrics()
        context.metadata["fizzssh_version"] = FIZZSSH_VERSION
        context.metadata["fizzssh_running"] = self._server.is_running
        context.metadata["fizzssh_connections"] = m.total_connections
        context.metadata["fizzssh_commands"] = m.commands_executed
        context.metadata["fizzssh_sftp_ops"] = m.sftp_operations

        if next_handler is not None:
            return next_handler(context)
        return context

    def get_priority(self) -> int:
        return MIDDLEWARE_PRIORITY

    def render_dashboard(self) -> str:
        return self._dashboard.render()

    def render_status(self) -> str:
        m = self._server.get_metrics()
        return (
            f"FizzSSH {FIZZSSH_VERSION} | "
            f"{'UP' if self._server.is_running else 'DOWN'} | "
            f"Port: {self._config.port} | "
            f"Sessions: {m.active_sessions} | "
            f"Commands: {m.commands_executed}"
        )

    def render_authorized_keys(self) -> str:
        lines = [
            "=" * self._config.dashboard_width,
            "FizzSSH Authorized Keys".center(self._config.dashboard_width),
            "=" * self._config.dashboard_width,
        ]
        for user, keys in self._authorized_keys.list_all().items():
            lines.append(f"\n  User: {user}")
            for key in keys:
                lines.append(f"    {key.algorithm} {key.fingerprint} {key.comment}")
        return "\n".join(lines)


# ============================================================
# Factory Function
# ============================================================


def create_fizzssh_subsystem(
    port: int = DEFAULT_PORT,
    host_key_type: str = "ed25519",
    enable_password_auth: bool = True,
    enable_pubkey_auth: bool = True,
    enable_sftp: bool = True,
    enable_port_forwarding: bool = True,
    enable_session_recording: bool = True,
    max_sessions: int = DEFAULT_MAX_SESSIONS,
    idle_timeout: float = DEFAULT_IDLE_TIMEOUT,
    rate_limit: int = DEFAULT_RATE_LIMIT,
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[SSHServer, FizzSSHDashboard, FizzSSHMiddleware]:
    """Factory function for creating the FizzSSH subsystem."""
    config = FizzSSHConfig(
        port=port,
        host_key_type=host_key_type,
        enable_password_auth=enable_password_auth,
        enable_pubkey_auth=enable_pubkey_auth,
        enable_sftp=enable_sftp,
        enable_port_forwarding=enable_port_forwarding,
        enable_session_recording=enable_session_recording,
        max_sessions=max_sessions,
        idle_timeout=idle_timeout,
        rate_limit=rate_limit,
        dashboard_width=dashboard_width,
    )

    host_key_manager = HostKeyManager()
    key_exchange = KeyExchange(host_key_manager)
    authorized_keys = AuthorizedKeysStore()
    authenticator = ClientAuthenticator(config, authorized_keys)
    sftp = SFTPSubsystem(config)
    port_forwarder = PortForwarder(config)
    session_recorder = SessionRecorder(config)
    rate_limiter = ConnectionRateLimiter(config)

    server = SSHServer(
        config, host_key_manager, key_exchange, authenticator,
        sftp, port_forwarder, session_recorder, rate_limiter,
    )

    dashboard = FizzSSHDashboard(
        server, host_key_manager, sftp, port_forwarder,
        session_recorder, dashboard_width,
    )

    middleware = FizzSSHMiddleware(server, dashboard, authorized_keys, config)

    server.start()

    logger.info(
        "FizzSSH subsystem initialized: port=%d key=%s sftp=%s",
        port, host_key_type, enable_sftp,
    )

    return server, dashboard, middleware
