"""
Tests for enterprise_fizzbuzz.infrastructure.fizzssh

Comprehensive test suite for the FizzSSH SSH protocol server covering
host key management, authorized keys, key exchange, client authentication,
SFTP operations, port forwarding, session recording, rate limiting, SSH
server protocol flow, and middleware integration.
"""

from __future__ import annotations

import base64
import hashlib
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from enterprise_fizzbuzz.infrastructure.fizzssh import (
    FIZZSSH_VERSION,
    FIZZSSH_PROTOCOL_VERSION,
    MIDDLEWARE_PRIORITY,
    DEFAULT_PORT,
    DEFAULT_CREDENTIALS,
    SSHConnectionState,
    ChannelState,
    ChannelType,
    AuthMethod,
    SFTPOperation,
    HostKeyType,
    FizzSSHConfig,
    KeyPair,
    SSHSession,
    SSHChannel,
    PortForward,
    SFTPFileEntry,
    ServerMetrics,
    HostKeyManager,
    AuthorizedKeysStore,
    KeyExchange,
    ClientAuthenticator,
    SFTPSubsystem,
    PortForwarder,
    SessionRecorder,
    ConnectionRateLimiter,
    SSHServer,
    FizzSSHDashboard,
    FizzSSHMiddleware,
    create_fizzssh_subsystem,
)


@pytest.fixture
def config():
    return FizzSSHConfig()


@pytest.fixture
def subsystem():
    return create_fizzssh_subsystem()


def _auth_and_open_channel(server, client_addr="10.0.0.1"):
    """Helper: connect, auth, open channel."""
    return server.handle_connection(client_addr, [
        {"type": "auth", "method": "password", "username": "root", "credentials": {"password": "fizzbuzz"}},
        {"type": "channel_open", "channel_type": "session"},
    ])


class TestHostKeyManager:
    def test_default_keys(self):
        mgr = HostKeyManager()
        assert mgr.get_key("ssh-ed25519") is not None
        assert mgr.get_key("ssh-rsa") is not None

    def test_fingerprint(self):
        mgr = HostKeyManager()
        fp = mgr.get_fingerprint("ssh-ed25519")
        assert fp.startswith("SHA256:")

    def test_list_keys(self):
        mgr = HostKeyManager()
        keys = mgr.list_keys()
        assert len(keys) == 2

    def test_unknown_key(self):
        mgr = HostKeyManager()
        assert mgr.get_key("unknown-algo") is None


class TestAuthorizedKeysStore:
    def test_default_keys(self):
        store = AuthorizedKeysStore()
        for user in DEFAULT_CREDENTIALS:
            assert len(store.get_keys(user)) == 1

    def test_verify_key(self):
        store = AuthorizedKeysStore()
        keys = store.get_keys("root")
        assert store.verify_key("root", keys[0].public_key) is True

    def test_verify_wrong_key(self):
        store = AuthorizedKeysStore()
        assert store.verify_key("root", "wrong-key") is False

    def test_add_key(self):
        store = AuthorizedKeysStore()
        store.add_key("newuser", KeyPair(algorithm="ssh-ed25519", public_key="newkey"))
        assert len(store.get_keys("newuser")) == 1

    def test_remove_key(self):
        store = AuthorizedKeysStore()
        keys = store.get_keys("root")
        fp = keys[0].fingerprint
        assert store.remove_key("root", fp) is True
        assert len(store.get_keys("root")) == 0

    def test_list_all(self):
        store = AuthorizedKeysStore()
        all_keys = store.list_all()
        assert len(all_keys) == len(DEFAULT_CREDENTIALS)


class TestKeyExchange:
    def test_curve25519(self):
        mgr = HostKeyManager()
        kex = KeyExchange(mgr)
        session = SSHSession(session_id="test123")
        key = kex.perform_kex(session, "curve25519-sha256")
        assert len(key) == 32
        assert session.kex_algorithm == "curve25519-sha256"

    def test_dh_group14(self):
        mgr = HostKeyManager()
        kex = KeyExchange(mgr)
        session = SSHSession(session_id="test456")
        key = kex.perform_kex(session, "diffie-hellman-group14-sha256")
        assert len(key) == 32

    def test_dh_group16(self):
        mgr = HostKeyManager()
        kex = KeyExchange(mgr)
        session = SSHSession(session_id="test789")
        key = kex.perform_kex(session, "diffie-hellman-group16-sha512")
        assert len(key) == 32

    def test_unsupported_algorithm(self):
        mgr = HostKeyManager()
        kex = KeyExchange(mgr)
        session = SSHSession(session_id="test")
        with pytest.raises(Exception):
            kex.perform_kex(session, "unsupported-algo")

    def test_different_sessions_different_keys(self):
        mgr = HostKeyManager()
        kex = KeyExchange(mgr)
        s1 = SSHSession(session_id="aaa")
        s2 = SSHSession(session_id="bbb")
        k1 = kex.perform_kex(s1)
        k2 = kex.perform_kex(s2)
        assert k1 != k2


class TestClientAuthenticator:
    def test_password_success(self, config):
        auth = ClientAuthenticator(config, AuthorizedKeysStore())
        session = SSHSession()
        assert auth.authenticate(session, AuthMethod.PASSWORD, "root", {"password": "fizzbuzz"})

    def test_password_failure(self, config):
        auth = ClientAuthenticator(config, AuthorizedKeysStore())
        session = SSHSession()
        assert not auth.authenticate(session, AuthMethod.PASSWORD, "root", {"password": "wrong"})

    def test_password_unknown_user(self, config):
        auth = ClientAuthenticator(config, AuthorizedKeysStore())
        session = SSHSession()
        assert not auth.authenticate(session, AuthMethod.PASSWORD, "nobody", {"password": "x"})

    def test_pubkey_success(self, config):
        store = AuthorizedKeysStore()
        auth = ClientAuthenticator(config, store)
        session = SSHSession()
        pubkey = store.get_keys("root")[0].public_key
        assert auth.authenticate(session, AuthMethod.PUBLIC_KEY, "root", {"public_key": pubkey})

    def test_pubkey_wrong_key(self, config):
        auth = ClientAuthenticator(config, AuthorizedKeysStore())
        session = SSHSession()
        assert not auth.authenticate(session, AuthMethod.PUBLIC_KEY, "root", {"public_key": "bad"})

    def test_keyboard_interactive(self, config):
        auth = ClientAuthenticator(config, AuthorizedKeysStore())
        session = SSHSession()
        assert auth.authenticate(session, AuthMethod.KEYBOARD_INTERACTIVE, "admin", {"responses": ["admin"]})

    def test_supported_methods(self, config):
        auth = ClientAuthenticator(config, AuthorizedKeysStore())
        methods = auth.get_supported_methods("root")
        assert AuthMethod.PASSWORD in methods
        assert AuthMethod.PUBLIC_KEY in methods


class TestSFTPSubsystem:
    def test_stat(self, config):
        sftp = SFTPSubsystem(config)
        stat = sftp.stat("/etc/fizzbuzz.conf")
        assert stat["name"] == "fizzbuzz.conf"
        assert stat["size"] > 0

    def test_stat_not_found(self, config):
        sftp = SFTPSubsystem(config)
        with pytest.raises(Exception):
            sftp.stat("/nonexistent")

    def test_opendir(self, config):
        sftp = SFTPSubsystem(config)
        entries = sftp.opendir("/")
        names = [e["name"] for e in entries]
        assert "home" in names or "etc" in names or "var" in names

    def test_read(self, config):
        sftp = SFTPSubsystem(config)
        data = sftp.read("/etc/fizzbuzz.conf")
        assert b"Enterprise FizzBuzz" in data

    def test_write_and_read(self, config):
        sftp = SFTPSubsystem(config)
        sftp.write("/tmp/test.txt", b"Hello FizzBuzz")
        data = sftp.read("/tmp/test.txt")
        assert data == b"Hello FizzBuzz"

    def test_mkdir(self, config):
        sftp = SFTPSubsystem(config)
        sftp.mkdir("/tmp/newdir")
        stat = sftp.stat("/tmp/newdir")
        assert stat["is_directory"]

    def test_rmdir(self, config):
        sftp = SFTPSubsystem(config)
        sftp.mkdir("/tmp/toremove")
        sftp.rmdir("/tmp/toremove")
        with pytest.raises(Exception):
            sftp.stat("/tmp/toremove")

    def test_remove(self, config):
        sftp = SFTPSubsystem(config)
        sftp.write("/tmp/removeme.txt", b"bye")
        sftp.remove("/tmp/removeme.txt")
        with pytest.raises(Exception):
            sftp.stat("/tmp/removeme.txt")

    def test_rename(self, config):
        sftp = SFTPSubsystem(config)
        sftp.write("/tmp/old.txt", b"data")
        sftp.rename("/tmp/old.txt", "/tmp/new.txt")
        assert sftp.read("/tmp/new.txt") == b"data"

    def test_operation_count(self, config):
        sftp = SFTPSubsystem(config)
        sftp.stat("/")
        sftp.opendir("/")
        assert sftp.operation_count == 2


class TestPortForwarder:
    def test_add_local(self, config):
        pf = PortForwarder(config)
        fid = pf.add_local_forward("s1", "127.0.0.1", 8080, "10.0.0.1", 80)
        assert pf.active_count == 1

    def test_add_remote(self, config):
        pf = PortForwarder(config)
        pf.add_remote_forward("s1", "0.0.0.0", 9090, "10.0.0.2", 443)
        assert pf.active_count == 1

    def test_remove(self, config):
        pf = PortForwarder(config)
        fid = pf.add_local_forward("s1", "127.0.0.1", 8080, "10.0.0.1", 80)
        assert pf.remove_forward(fid)
        assert pf.active_count == 0

    def test_disabled(self):
        config = FizzSSHConfig(enable_port_forwarding=False)
        pf = PortForwarder(config)
        with pytest.raises(Exception):
            pf.add_local_forward("s1", "127.0.0.1", 8080, "10.0.0.1", 80)

    def test_list_forwards(self, config):
        pf = PortForwarder(config)
        pf.add_local_forward("s1", "127.0.0.1", 8080, "a", 80)
        pf.add_local_forward("s2", "127.0.0.1", 9090, "b", 80)
        assert len(pf.list_forwards("s1")) == 1
        assert len(pf.list_forwards()) == 2


class TestSessionRecorder:
    def test_start_and_end(self, config):
        rec = SessionRecorder(config)
        session = SSHSession(session_id="rec1", authenticated_user="root", client_addr="1.2.3.4")
        rec.start_recording(session)
        rec.record_event("rec1", "test_event", {"key": "value"})
        rec.record_command("rec1", "whoami")
        recording = rec.end_recording("rec1")
        assert recording is not None
        assert len(recording.events) == 1
        assert len(recording.commands) == 1
        assert recording.ended_at is not None

    def test_recording_disabled(self):
        config = FizzSSHConfig(enable_session_recording=False)
        rec = SessionRecorder(config)
        session = SSHSession(session_id="x")
        rec.start_recording(session)
        assert rec.get_recording("x") is None

    def test_list_recordings(self, config):
        rec = SessionRecorder(config)
        for i in range(3):
            session = SSHSession(session_id=f"r{i}", authenticated_user="root")
            rec.start_recording(session)
        assert rec.recording_count == 3


class TestConnectionRateLimiter:
    def test_allow(self, config):
        rl = ConnectionRateLimiter(config)
        assert rl.check("1.2.3.4") is True

    def test_rate_limit(self):
        config = FizzSSHConfig(rate_limit=2)
        rl = ConnectionRateLimiter(config)
        rl.check("1.2.3.4")
        rl.check("1.2.3.4")
        assert rl.check("1.2.3.4") is False
        assert rl.blocked_count == 1

    def test_different_ips(self):
        config = FizzSSHConfig(rate_limit=1)
        rl = ConnectionRateLimiter(config)
        assert rl.check("1.1.1.1") is True
        assert rl.check("2.2.2.2") is True


class TestSSHServer:
    def test_version_exchange(self, subsystem):
        server, _, _ = subsystem
        responses = server.handle_connection("10.0.0.1", [])
        assert responses[0]["type"] == "version"
        assert "SSH-2.0" in responses[0]["server_version"]

    def test_kex_complete(self, subsystem):
        server, _, _ = subsystem
        responses = server.handle_connection("10.0.0.1", [])
        kex = [r for r in responses if r["type"] == "kex_complete"]
        assert len(kex) == 1
        assert "curve25519" in kex[0]["algorithm"]

    def test_auth_password_success(self, subsystem):
        server, _, _ = subsystem
        responses = server.handle_connection("10.0.0.1", [
            {"type": "auth", "method": "password", "username": "root", "credentials": {"password": "fizzbuzz"}},
        ])
        auth_resp = [r for r in responses if r["type"] == "auth_success"]
        assert len(auth_resp) == 1
        assert auth_resp[0]["username"] == "root"

    def test_auth_password_failure(self, subsystem):
        server, _, _ = subsystem
        responses = server.handle_connection("10.0.0.1", [
            {"type": "auth", "method": "password", "username": "root", "credentials": {"password": "wrong"}},
        ])
        auth_resp = [r for r in responses if r["type"] == "auth_failure"]
        assert len(auth_resp) == 1

    def test_channel_open(self, subsystem):
        server, _, _ = subsystem
        responses = _auth_and_open_channel(server)
        chan_resp = [r for r in responses if r["type"] == "channel_open_confirmation"]
        assert len(chan_resp) == 1

    def test_exec_command(self, subsystem):
        server, _, _ = subsystem
        responses = server.handle_connection("10.0.0.1", [
            {"type": "auth", "method": "password", "username": "bob", "credentials": {"password": "mcfizzington"}},
            {"type": "channel_open", "channel_type": "session"},
            {"type": "exec", "channel_id": 0, "command": "fizzbuzz 15"},
        ])
        exec_resp = [r for r in responses if r["type"] == "exec_result"]
        assert len(exec_resp) == 1
        assert exec_resp[0]["output"] == "FizzBuzz"

    def test_exec_whoami(self, subsystem):
        server, _, _ = subsystem
        responses = server.handle_connection("10.0.0.1", [
            {"type": "auth", "method": "password", "username": "operator", "credentials": {"password": "operator"}},
            {"type": "channel_open", "channel_type": "session"},
            {"type": "exec", "channel_id": 0, "command": "whoami"},
        ])
        exec_resp = [r for r in responses if r["type"] == "exec_result"]
        assert exec_resp[0]["output"] == "operator"

    def test_pty_allocation(self, subsystem):
        server, _, _ = subsystem
        responses = server.handle_connection("10.0.0.1", [
            {"type": "auth", "method": "password", "username": "root", "credentials": {"password": "fizzbuzz"}},
            {"type": "channel_open", "channel_type": "session"},
            {"type": "pty", "channel_id": 0, "term": "vt100", "width": 132, "height": 43},
        ])
        pty_resp = [r for r in responses if r["type"] == "pty_allocated"]
        assert len(pty_resp) == 1
        assert pty_resp[0]["term"] == "vt100"

    def test_shell_session(self, subsystem):
        server, _, _ = subsystem
        responses = server.handle_connection("10.0.0.1", [
            {"type": "auth", "method": "password", "username": "root", "credentials": {"password": "fizzbuzz"}},
            {"type": "channel_open", "channel_type": "session"},
            {"type": "shell", "channel_id": 0, "input": ["hostname", "date"]},
        ])
        shell_resp = [r for r in responses if r["type"] == "shell_output"]
        assert len(shell_resp) == 1
        assert "fizzbuzz.local" in shell_resp[0]["output"]

    def test_sftp_ls(self, subsystem):
        server, _, _ = subsystem
        responses = server.handle_connection("10.0.0.1", [
            {"type": "auth", "method": "password", "username": "root", "credentials": {"password": "fizzbuzz"}},
            {"type": "sftp", "operation": "ls", "path": "/"},
        ])
        sftp_resp = [r for r in responses if r["type"] == "sftp_result"]
        assert len(sftp_resp) == 1

    def test_sftp_read(self, subsystem):
        server, _, _ = subsystem
        responses = server.handle_connection("10.0.0.1", [
            {"type": "auth", "method": "password", "username": "root", "credentials": {"password": "fizzbuzz"}},
            {"type": "sftp", "operation": "read", "path": "/etc/fizzbuzz.conf"},
        ])
        sftp_resp = [r for r in responses if r["type"] == "sftp_result"]
        assert "Enterprise FizzBuzz" in sftp_resp[0]["data"]

    def test_sftp_write_and_read(self, subsystem):
        server, _, _ = subsystem
        responses = server.handle_connection("10.0.0.1", [
            {"type": "auth", "method": "password", "username": "root", "credentials": {"password": "fizzbuzz"}},
            {"type": "sftp", "operation": "write", "path": "/tmp/test.txt", "content": "Hello SSH"},
            {"type": "sftp", "operation": "read", "path": "/tmp/test.txt"},
        ])
        sftp_resps = [r for r in responses if r["type"] == "sftp_result"]
        assert sftp_resps[1]["data"] == "Hello SSH"

    def test_sftp_not_found(self, subsystem):
        server, _, _ = subsystem
        responses = server.handle_connection("10.0.0.1", [
            {"type": "auth", "method": "password", "username": "root", "credentials": {"password": "fizzbuzz"}},
            {"type": "sftp", "operation": "read", "path": "/nonexistent"},
        ])
        err_resp = [r for r in responses if r["type"] == "sftp_error"]
        assert len(err_resp) == 1

    def test_port_forward(self, subsystem):
        server, _, _ = subsystem
        responses = server.handle_connection("10.0.0.1", [
            {"type": "auth", "method": "password", "username": "root", "credentials": {"password": "fizzbuzz"}},
            {"type": "port_forward", "direction": "local", "bind_address": "127.0.0.1",
             "bind_port": 3000, "target_address": "10.0.0.2", "target_port": 5432},
        ])
        fwd_resp = [r for r in responses if r["type"] == "port_forward_success"]
        assert len(fwd_resp) == 1

    def test_scp_upload(self, subsystem):
        server, _, _ = subsystem
        responses = server.handle_connection("10.0.0.1", [
            {"type": "auth", "method": "password", "username": "root", "credentials": {"password": "fizzbuzz"}},
            {"type": "scp_upload", "path": "/tmp/scp_test.txt", "content": "SCP data"},
        ])
        scp_resp = [r for r in responses if r["type"] == "scp_result"]
        assert len(scp_resp) == 1
        assert scp_resp[0]["operation"] == "upload"

    def test_scp_download(self, subsystem):
        server, _, _ = subsystem
        responses = server.handle_connection("10.0.0.1", [
            {"type": "auth", "method": "password", "username": "root", "credentials": {"password": "fizzbuzz"}},
            {"type": "scp_download", "path": "/etc/fizzbuzz.conf"},
        ])
        scp_resp = [r for r in responses if r["type"] == "scp_result"]
        assert len(scp_resp) == 1
        assert "Enterprise FizzBuzz" in scp_resp[0]["data"]

    def test_disconnect(self, subsystem):
        server, _, _ = subsystem
        responses = server.handle_connection("10.0.0.1", [
            {"type": "auth", "method": "password", "username": "root", "credentials": {"password": "fizzbuzz"}},
            {"type": "disconnect"},
        ])
        disc_resp = [r for r in responses if r["type"] == "disconnected"]
        assert len(disc_resp) == 1

    def test_rate_limiting(self):
        server, _, _ = create_fizzssh_subsystem(rate_limit=1)
        server.handle_connection("bad.ip", [])
        responses = server.handle_connection("bad.ip", [])
        err_resp = [r for r in responses if r["type"] == "error"]
        assert len(err_resp) == 1
        assert "rate limited" in err_resp[0]["message"].lower()

    def test_metrics(self, subsystem):
        server, _, _ = subsystem
        server.handle_connection("10.0.0.1", [
            {"type": "auth", "method": "password", "username": "root", "credentials": {"password": "fizzbuzz"}},
            {"type": "channel_open", "channel_type": "session"},
            {"type": "exec", "channel_id": 0, "command": "whoami"},
        ])
        m = server.get_metrics()
        assert m.total_connections >= 1
        assert m.auth_successes >= 1
        assert m.commands_executed >= 1

    def test_uptime(self, subsystem):
        server, _, _ = subsystem
        assert server.uptime > 0
        assert server.is_running


class TestFizzSSHMiddleware:
    def test_get_name(self, subsystem):
        _, _, mw = subsystem
        assert mw.get_name() == "fizzssh"

    def test_get_priority(self, subsystem):
        _, _, mw = subsystem
        assert mw.get_priority() == MIDDLEWARE_PRIORITY

    def test_process(self, subsystem):
        _, _, mw = subsystem
        ctx = MagicMock()
        ctx.metadata = {}
        mw.process(ctx, None)
        assert ctx.metadata["fizzssh_version"] == FIZZSSH_VERSION

    def test_render_dashboard(self, subsystem):
        _, _, mw = subsystem
        output = mw.render_dashboard()
        assert "FizzSSH" in output
        assert "RUNNING" in output

    def test_render_status(self, subsystem):
        _, _, mw = subsystem
        output = mw.render_status()
        assert "FizzSSH" in output
        assert "UP" in output

    def test_render_authorized_keys(self, subsystem):
        _, _, mw = subsystem
        output = mw.render_authorized_keys()
        assert "root" in output
        assert "ssh-ed25519" in output


class TestCreateSubsystem:
    def test_returns_tuple(self):
        result = create_fizzssh_subsystem()
        assert len(result) == 3

    def test_server_started(self):
        server, _, _ = create_fizzssh_subsystem()
        assert server.is_running

    def test_custom_port(self):
        server, _, _ = create_fizzssh_subsystem(port=2223)
        assert server._config.port == 2223

    def test_all_auth_methods(self):
        server, _, _ = create_fizzssh_subsystem()
        # Password auth
        r1 = server.handle_connection("10.0.0.1", [
            {"type": "auth", "method": "password", "username": "admin", "credentials": {"password": "admin"}},
        ])
        assert any(r["type"] == "auth_success" for r in r1)


class TestConstants:
    def test_version(self):
        assert FIZZSSH_VERSION == "1.0.0"

    def test_protocol(self):
        assert "SSH-2.0" in FIZZSSH_PROTOCOL_VERSION

    def test_priority(self):
        assert MIDDLEWARE_PRIORITY == 124

    def test_default_port(self):
        assert DEFAULT_PORT == 2222

    def test_default_credentials(self):
        assert "root" in DEFAULT_CREDENTIALS
        assert "bob" in DEFAULT_CREDENTIALS
