"""Tests for enterprise_fizzbuzz.infrastructure.fizzauth2"""
from __future__ import annotations
import base64, hashlib, uuid
from unittest.mock import MagicMock
import pytest
from enterprise_fizzbuzz.infrastructure.fizzauth2 import (
    FIZZAUTH2_VERSION, MIDDLEWARE_PRIORITY, SUPPORTED_SCOPES,
    GrantType, TokenType, ClientType,
    FizzAuth2Config, OAuthClient, AuthorizationCode, TokenData, JWK,
    JWTEngine, ClientRegistry, AuthorizationServer,
    FizzAuth2Dashboard, FizzAuth2Middleware, create_fizzauth2_subsystem,
)

@pytest.fixture
def subsystem():
    return create_fizzauth2_subsystem()

@pytest.fixture
def server():
    s, _, _ = create_fizzauth2_subsystem()
    return s

def _pkce_pair():
    verifier = uuid.uuid4().hex
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


class TestJWTEngine:
    def test_issue_and_validate(self):
        jwt = JWTEngine(FizzAuth2Config())
        token = jwt.issue({"sub": "bob", "exp": 9999999999})
        claims = jwt.validate(token)
        assert claims is not None
        assert claims["sub"] == "bob"

    def test_expired_token(self):
        jwt = JWTEngine(FizzAuth2Config())
        token = jwt.issue({"sub": "bob", "exp": 1})
        assert jwt.validate(token) is None

    def test_invalid_signature(self):
        jwt = JWTEngine(FizzAuth2Config())
        token = jwt.issue({"sub": "bob", "exp": 9999999999})
        assert jwt.validate(token + "tampered") is None

    def test_get_jwks(self):
        jwt = JWTEngine(FizzAuth2Config())
        jwks = jwt.get_jwks()
        assert "keys" in jwks
        assert len(jwks["keys"]) == 1
        assert jwks["keys"][0]["alg"] == "RS256"


class TestClientRegistry:
    def test_default_clients(self):
        cr = ClientRegistry()
        assert cr.count == 3
        assert cr.get("fizzbuzz-web") is not None

    def test_authenticate_confidential(self):
        cr = ClientRegistry()
        client = cr.authenticate("fizzbuzz-web", "fizzbuzz-web-secret")
        assert client is not None

    def test_authenticate_wrong_secret(self):
        cr = ClientRegistry()
        assert cr.authenticate("fizzbuzz-web", "wrong") is None

    def test_authenticate_public(self):
        cr = ClientRegistry()
        client = cr.authenticate("fizzbuzz-cli", "")
        assert client is not None

    def test_register(self):
        cr = ClientRegistry()
        cr.register(OAuthClient(client_id="new", client_name="New"))
        assert cr.get("new") is not None


class TestAuthorizationServer:
    def test_auth_code_flow(self, server):
        v, c = _pkce_pair()
        result = server.authorize("fizzbuzz-web", "", {"openid", "fizzbuzz:read"}, code_challenge=c)
        assert "code" in result
        tokens = server.exchange_code(result["code"], "fizzbuzz-web", code_verifier=v)
        assert "access_token" in tokens
        assert "id_token" in tokens

    def test_auth_code_invalid_client(self, server):
        with pytest.raises(Exception):
            server.authorize("nonexistent", "", {"openid"})

    def test_auth_code_invalid_scope(self, server):
        _, c = _pkce_pair()
        with pytest.raises(Exception):
            server.authorize("fizzbuzz-web", "", {"invalid_scope"}, code_challenge=c)

    def test_auth_code_reuse(self, server):
        v, c = _pkce_pair()
        result = server.authorize("fizzbuzz-web", "", {"openid"}, code_challenge=c)
        server.exchange_code(result["code"], "fizzbuzz-web", code_verifier=v)
        with pytest.raises(Exception):
            server.exchange_code(result["code"], "fizzbuzz-web", code_verifier=v)

    def test_pkce_required(self, server):
        with pytest.raises(Exception):
            server.authorize("fizzbuzz-web", "", {"openid"})

    def test_pkce_wrong_verifier(self, server):
        _, c = _pkce_pair()
        result = server.authorize("fizzbuzz-web", "", {"openid"}, code_challenge=c)
        with pytest.raises(Exception):
            server.exchange_code(result["code"], "fizzbuzz-web", code_verifier="wrong")

    def test_client_credentials(self, server):
        tokens = server.client_credentials("fizzbuzz-service", "fizzbuzz-service-secret", {"fizzbuzz:read"})
        assert "access_token" in tokens

    def test_client_credentials_wrong_secret(self, server):
        with pytest.raises(Exception):
            server.client_credentials("fizzbuzz-service", "wrong", {"fizzbuzz:read"})

    def test_device_auth_flow(self, server):
        da = server.device_authorize("fizzbuzz-cli", {"openid"})
        assert "device_code" in da
        assert "user_code" in da
        # Before approval
        result = server.device_token(da["device_code"], "fizzbuzz-cli")
        assert result.get("error") == "authorization_pending"
        # Approve
        server.device_approve(da["user_code"])
        result = server.device_token(da["device_code"], "fizzbuzz-cli")
        assert "access_token" in result

    def test_refresh_token(self, server):
        v, c = _pkce_pair()
        result = server.authorize("fizzbuzz-web", "", {"openid", "offline_access", "fizzbuzz:read"}, code_challenge=c)
        tokens = server.exchange_code(result["code"], "fizzbuzz-web", code_verifier=v)
        assert "refresh_token" in tokens
        new_tokens = server.refresh(tokens["refresh_token"], "fizzbuzz-web")
        assert "access_token" in new_tokens

    def test_introspect_active(self, server):
        tokens = server.client_credentials("fizzbuzz-service", "fizzbuzz-service-secret", {"fizzbuzz:read"})
        result = server.introspect(tokens["access_token"])
        assert result["active"] is True

    def test_introspect_invalid(self, server):
        result = server.introspect("invalid.token.here")
        assert result["active"] is False

    def test_revoke(self, server):
        tokens = server.client_credentials("fizzbuzz-service", "fizzbuzz-service-secret", {"fizzbuzz:read"})
        assert server.revoke(tokens["access_token"]) is True
        result = server.introspect(tokens["access_token"])
        assert result["active"] is False

    def test_discovery(self, server):
        disc = server.get_discovery()
        assert disc["issuer"] == "https://auth.fizzbuzz.local"
        assert "authorization_endpoint" in disc
        assert "token_endpoint" in disc
        assert "jwks_uri" in disc

    def test_metrics(self, server):
        server.client_credentials("fizzbuzz-service", "fizzbuzz-service-secret", {"fizzbuzz:read"})
        m = server.get_metrics()
        assert m.tokens_issued >= 1

    def test_uptime(self, server):
        assert server.uptime > 0
        assert server.is_running


class TestFizzAuth2Middleware:
    def test_get_name(self, subsystem):
        _, _, mw = subsystem
        assert mw.get_name() == "fizzauth2"

    def test_get_priority(self, subsystem):
        _, _, mw = subsystem
        assert mw.get_priority() == MIDDLEWARE_PRIORITY

    def test_process(self, subsystem):
        _, _, mw = subsystem
        ctx = MagicMock(); ctx.metadata = {}
        mw.process(ctx, None)
        assert ctx.metadata["fizzauth2_version"] == FIZZAUTH2_VERSION

    def test_render_dashboard(self, subsystem):
        _, _, mw = subsystem
        assert "FizzAuth2" in mw.render_dashboard()

    def test_render_clients(self, subsystem):
        _, _, mw = subsystem
        output = mw.render_clients()
        assert "fizzbuzz-web" in output

    def test_render_jwks(self, subsystem):
        _, _, mw = subsystem
        output = mw.render_jwks()
        assert "RS256" in output

    def test_render_discovery(self, subsystem):
        _, _, mw = subsystem
        output = mw.render_discovery()
        assert "authorization_endpoint" in output

    def test_render_authorize(self, subsystem):
        _, _, mw = subsystem
        output = mw.render_authorize("fizzbuzz-web")
        assert "Access Token" in output


class TestCreateSubsystem:
    def test_returns_tuple(self):
        assert len(create_fizzauth2_subsystem()) == 3

    def test_started(self):
        s, _, _ = create_fizzauth2_subsystem()
        assert s.is_running

    def test_default_clients(self):
        s, _, _ = create_fizzauth2_subsystem()
        assert s._clients.count == 3


class TestConstants:
    def test_version(self):
        assert FIZZAUTH2_VERSION == "1.0.0"
    def test_priority(self):
        assert MIDDLEWARE_PRIORITY == 132
    def test_scopes(self):
        assert "openid" in SUPPORTED_SCOPES
