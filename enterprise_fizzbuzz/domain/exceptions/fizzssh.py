"""
Enterprise FizzBuzz Platform - FizzSSH Remote Shell Engine Errors (EFP-SSH00 .. EFP-SSH24)

Exception hierarchy for the FizzSSH secure shell engine.  Covers transport
layer negotiation, packet framing, encryption and MAC verification, key
exchange, host key management, multi-method authentication, channel
multiplexing, session and PTY allocation, remote command execution, SFTP
and SCP file transfer, port forwarding, rate limiting, and SSH
configuration management.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class FizzSSHError(FizzBuzzError):
    """Base exception for all FizzSSH secure shell engine errors.

    FizzSSH is the platform's SSH-2 protocol implementation that provides
    encrypted remote shell access, file transfer, and port forwarding
    capabilities.  It handles the full SSH-2 protocol stack from transport
    layer negotiation through channel multiplexing and subsystem dispatch.
    All SSH-specific failures inherit from this class to enable categorical
    error handling in the middleware pipeline.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzSSH error: {reason}",
            error_code="EFP-SSH00",
            context={"reason": reason},
        )


class FizzSSHTransportError(FizzSSHError):
    """Raised on transport layer errors.

    Covers failures in the SSH-2 transport layer including TCP connection
    establishment, protocol version exchange, algorithm negotiation, and
    transport-level disconnection events.
    """

    def __init__(self, host: str, reason: str) -> None:
        super().__init__(f"Transport error for host '{host}': {reason}")
        self.error_code = "EFP-SSH01"
        self.context = {"host": host, "reason": reason}


class FizzSSHPacketError(FizzSSHError):
    """Raised on packet framing errors.

    Covers malformed packet headers, invalid packet lengths, padding
    violations, and sequence number mismatches in the SSH-2 binary
    packet protocol.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Packet framing error: {reason}")
        self.error_code = "EFP-SSH02"
        self.context = {"reason": reason}


class FizzSSHEncryptionError(FizzSSHError):
    """Raised on encryption or decryption failures.

    Covers failures in symmetric cipher operations including AES, ChaCha20,
    and 3DES during packet encryption and decryption, as well as cipher
    initialization and key derivation errors.
    """

    def __init__(self, cipher: str, reason: str) -> None:
        super().__init__(f"Encryption error with cipher '{cipher}': {reason}")
        self.error_code = "EFP-SSH03"
        self.context = {"cipher": cipher, "reason": reason}


class FizzSSHMACError(FizzSSHError):
    """Raised on MAC verification failures.

    Covers message authentication code computation and verification
    failures, indicating potential data corruption or tampering in
    transit.  A MAC failure terminates the connection immediately
    as required by RFC 4253.
    """

    def __init__(self, algorithm: str, reason: str) -> None:
        super().__init__(f"MAC verification failed for algorithm '{algorithm}': {reason}")
        self.error_code = "EFP-SSH04"
        self.context = {"algorithm": algorithm, "reason": reason}


class FizzSSHKeyExchangeError(FizzSSHError):
    """Raised on key exchange failures.

    Covers failures in Diffie-Hellman group exchange, elliptic-curve
    Diffie-Hellman, and other key exchange methods during initial
    handshake and periodic re-keying operations.
    """

    def __init__(self, method: str, reason: str) -> None:
        super().__init__(f"Key exchange failed for method '{method}': {reason}")
        self.error_code = "EFP-SSH05"
        self.context = {"method": method, "reason": reason}


class FizzSSHHostKeyError(FizzSSHError):
    """Raised on host key verification errors.

    Covers host key type mismatches, signature verification failures,
    and host key changes that may indicate a man-in-the-middle attack.
    The connection is terminated when host key verification fails.
    """

    def __init__(self, host: str, reason: str) -> None:
        super().__init__(f"Host key error for '{host}': {reason}")
        self.error_code = "EFP-SSH06"
        self.context = {"host": host, "reason": reason}


class FizzSSHHostKeyNotFoundError(FizzSSHError):
    """Raised when a host key is not found in the known hosts database.

    The SSH client maintains a known hosts database mapping hostnames
    and IP addresses to their expected public keys.  This exception is
    raised when connecting to a host with no prior key on record,
    requiring explicit user or policy approval before proceeding.
    """

    def __init__(self, host: str, key_type: str) -> None:
        super().__init__(f"No {key_type} host key found for '{host}'")
        self.error_code = "EFP-SSH07"
        self.context = {"host": host, "key_type": key_type}


class FizzSSHAuthError(FizzSSHError):
    """Raised on authentication failures.

    Covers general authentication errors including method negotiation
    failures, authentication banner processing errors, and exhaustion
    of all available authentication methods.
    """

    def __init__(self, user: str, reason: str) -> None:
        super().__init__(f"Authentication failed for user '{user}': {reason}")
        self.error_code = "EFP-SSH08"
        self.context = {"user": user, "reason": reason}


class FizzSSHAuthPasswordError(FizzSSHError):
    """Raised when password authentication fails.

    Covers incorrect password, expired password, and password change
    required scenarios in the SSH-2 password authentication method
    as defined in RFC 4252.
    """

    def __init__(self, user: str) -> None:
        super().__init__(f"Password authentication failed for user '{user}'")
        self.error_code = "EFP-SSH09"
        self.context = {"user": user}


class FizzSSHAuthPublicKeyError(FizzSSHError):
    """Raised when public key authentication fails.

    Covers key format errors, signature computation failures, and
    server rejection of the offered public key during the SSH-2
    public key authentication method.
    """

    def __init__(self, user: str, key_type: str) -> None:
        super().__init__(f"Public key authentication failed for user '{user}' with key type '{key_type}'")
        self.error_code = "EFP-SSH10"
        self.context = {"user": user, "key_type": key_type}


class FizzSSHAuthKeyboardInteractiveError(FizzSSHError):
    """Raised when keyboard-interactive authentication fails.

    Covers failures in the challenge-response exchange of the SSH-2
    keyboard-interactive authentication method as defined in RFC 4256,
    including prompt processing errors and response validation failures.
    """

    def __init__(self, user: str, reason: str) -> None:
        super().__init__(f"Keyboard-interactive authentication failed for user '{user}': {reason}")
        self.error_code = "EFP-SSH11"
        self.context = {"user": user, "reason": reason}


class FizzSSHChannelError(FizzSSHError):
    """Raised on channel errors.

    Covers failures in the SSH-2 channel layer including window size
    management, data transfer errors, and channel-level flow control
    violations across all channel types.
    """

    def __init__(self, channel_id: int, reason: str) -> None:
        super().__init__(f"Channel {channel_id} error: {reason}")
        self.error_code = "EFP-SSH12"
        self.context = {"channel_id": channel_id, "reason": reason}


class FizzSSHChannelOpenError(FizzSSHError):
    """Raised when a channel open request fails.

    Covers server-side refusal of channel open requests due to resource
    constraints, administrative policy, or invalid channel type.  The
    SSH-2 reason code from the server is preserved in the context.
    """

    def __init__(self, channel_type: str, reason: str) -> None:
        super().__init__(f"Failed to open {channel_type} channel: {reason}")
        self.error_code = "EFP-SSH13"
        self.context = {"channel_type": channel_type, "reason": reason}


class FizzSSHChannelClosedError(FizzSSHError):
    """Raised when an operation is attempted on a closed channel.

    Once a channel has received or sent a close message, no further
    data or requests may be sent on that channel.  This exception is
    raised when application code attempts to use a channel that has
    already been closed.
    """

    def __init__(self, channel_id: int) -> None:
        super().__init__(f"Operation attempted on closed channel {channel_id}")
        self.error_code = "EFP-SSH14"
        self.context = {"channel_id": channel_id}


class FizzSSHSessionError(FizzSSHError):
    """Raised on session errors.

    Covers failures in SSH-2 session management including session
    channel establishment, environment variable propagation, and
    session lifecycle state machine violations.
    """

    def __init__(self, session_id: str, reason: str) -> None:
        super().__init__(f"Session '{session_id}' error: {reason}")
        self.error_code = "EFP-SSH15"
        self.context = {"session_id": session_id, "reason": reason}


class FizzSSHPTYError(FizzSSHError):
    """Raised on PTY allocation errors.

    Covers failures in pseudo-terminal allocation including unsupported
    terminal types, invalid terminal dimensions, and server-side PTY
    resource exhaustion.
    """

    def __init__(self, term: str, reason: str) -> None:
        super().__init__(f"PTY allocation failed for terminal '{term}': {reason}")
        self.error_code = "EFP-SSH16"
        self.context = {"term": term, "reason": reason}


class FizzSSHExecError(FizzSSHError):
    """Raised on remote command execution errors.

    Covers failures in dispatching commands to the remote shell,
    including command string encoding errors, shell invocation
    failures, and non-zero exit status propagation.
    """

    def __init__(self, command: str, exit_code: int, reason: str) -> None:
        super().__init__(f"Remote command failed with exit code {exit_code}: {command}")
        self.error_code = "EFP-SSH17"
        self.context = {"command": command, "exit_code": exit_code, "reason": reason}


class FizzSSHSFTPError(FizzSSHError):
    """Raised on SFTP subsystem errors.

    Covers failures in the SFTP subsystem including session
    initialization, protocol version negotiation, and general
    file operation errors not covered by more specific exceptions.
    """

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"SFTP error for '{path}': {reason}")
        self.error_code = "EFP-SSH18"
        self.context = {"path": path, "reason": reason}


class FizzSSHSFTPFileNotFoundError(FizzSSHError):
    """Raised when an SFTP operation targets a nonexistent file.

    The SFTP server returns SSH_FX_NO_SUCH_FILE when the requested
    path does not exist on the remote filesystem.  This maps to the
    SFTP status code 2 as defined in the SFTP protocol specification.
    """

    def __init__(self, path: str) -> None:
        super().__init__(f"SFTP file not found: '{path}'")
        self.error_code = "EFP-SSH19"
        self.context = {"path": path}


class FizzSSHSFTPPermissionError(FizzSSHError):
    """Raised when an SFTP operation is denied due to insufficient permissions.

    The SFTP server returns SSH_FX_PERMISSION_DENIED when the
    authenticated user lacks the required filesystem permissions
    to perform the requested operation on the target path.
    """

    def __init__(self, path: str, operation: str) -> None:
        super().__init__(f"SFTP permission denied for '{operation}' on '{path}'")
        self.error_code = "EFP-SSH20"
        self.context = {"path": path, "operation": operation}


class FizzSSHPortForwardError(FizzSSHError):
    """Raised on port forwarding errors.

    Covers failures in local and remote port forwarding setup,
    including bind address conflicts, connection refusal on the
    forwarded port, and dynamic SOCKS proxy establishment errors.
    """

    def __init__(self, bind_address: str, port: int, reason: str) -> None:
        super().__init__(f"Port forward error for {bind_address}:{port}: {reason}")
        self.error_code = "EFP-SSH21"
        self.context = {"bind_address": bind_address, "port": port, "reason": reason}


class FizzSSHSCPError(FizzSSHError):
    """Raised on SCP transfer errors.

    Covers failures in the SCP file transfer protocol including
    source file access errors, transfer interruptions, checksum
    mismatches, and remote sink-side write failures.
    """

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"SCP transfer error for '{path}': {reason}")
        self.error_code = "EFP-SSH22"
        self.context = {"path": path, "reason": reason}


class FizzSSHRateLimitError(FizzSSHError):
    """Raised when the SSH connection rate limit is exceeded.

    The SSH engine enforces per-host and global connection rate limits
    to prevent resource exhaustion and brute-force attacks.  This
    exception is raised when a new connection attempt exceeds the
    configured rate threshold.
    """

    def __init__(self, host: str, limit: int, window_seconds: int) -> None:
        super().__init__(f"Rate limit exceeded for host '{host}': {limit} connections per {window_seconds}s")
        self.error_code = "EFP-SSH23"
        self.context = {"host": host, "limit": limit, "window_seconds": window_seconds}


class FizzSSHConfigError(FizzSSHError):
    """Raised on SSH configuration errors.

    Covers invalid SSH client or server configuration parameters,
    missing required configuration directives, and conflicts between
    configuration options such as incompatible cipher and MAC
    algorithm selections.
    """

    def __init__(self, parameter: str, reason: str) -> None:
        super().__init__(f"SSH configuration error for '{parameter}': {reason}")
        self.error_code = "EFP-SSH24"
        self.context = {"parameter": parameter, "reason": reason}
