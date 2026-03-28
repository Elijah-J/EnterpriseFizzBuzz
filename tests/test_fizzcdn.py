"""Tests for enterprise_fizzbuzz.infrastructure.fizzcdn"""
from __future__ import annotations
from unittest.mock import MagicMock
import pytest
from enterprise_fizzbuzz.infrastructure.fizzcdn import (
    FIZZCDN_VERSION, MIDDLEWARE_PRIORITY, CacheStatus, PoPStatus,
    FizzCDNConfig, CacheEntry, PoP, CDNRequest, CDNResponse, CDNMetrics,
    GeographicRouter, CacheController, OriginPuller, CDNEngine,
    FizzCDNDashboard, FizzCDNMiddleware, create_fizzcdn_subsystem,
)

@pytest.fixture
def subsystem():
    return create_fizzcdn_subsystem()

@pytest.fixture
def engine():
    e, _, _ = create_fizzcdn_subsystem()
    return e


class TestGeographicRouter:
    def test_route_nearest(self):
        router = GeographicRouter()
        pops = [
            PoP(name="us", latitude=40.0, longitude=-74.0),
            PoP(name="eu", latitude=51.5, longitude=-0.1),
        ]
        # Client in New York
        pop = router.route(40.7, -74.0, pops)
        assert pop.name == "us"

    def test_route_europe(self):
        router = GeographicRouter()
        pops = [
            PoP(name="us", latitude=40.0, longitude=-74.0),
            PoP(name="eu", latitude=51.5, longitude=-0.1),
        ]
        pop = router.route(48.8, 2.3, pops)  # Paris
        assert pop.name == "eu"

    def test_route_skips_offline(self):
        router = GeographicRouter()
        pops = [
            PoP(name="us", latitude=40.0, longitude=-74.0, status=PoPStatus.OFFLINE),
            PoP(name="eu", latitude=51.5, longitude=-0.1),
        ]
        pop = router.route(40.7, -74.0, pops)
        assert pop.name == "eu"


class TestCacheController:
    def test_put_and_get(self):
        config = FizzCDNConfig()
        cc = CacheController(config)
        pop = PoP(name="test")
        cc.put(pop, "/test", b"hello", "text/plain")
        status, entry = cc.get(pop, "/test")
        assert status == CacheStatus.HIT
        assert entry.content == b"hello"

    def test_miss(self):
        config = FizzCDNConfig()
        cc = CacheController(config)
        pop = PoP(name="test")
        status, entry = cc.get(pop, "/missing")
        assert status == CacheStatus.MISS

    def test_purge_url(self):
        config = FizzCDNConfig()
        cc = CacheController(config)
        pop = PoP(name="test")
        cc.put(pop, "/test", b"data")
        count = cc.purge_url([pop], "/test")
        assert count >= 1
        status, _ = cc.get(pop, "/test")
        assert status == CacheStatus.MISS

    def test_purge_prefix(self):
        config = FizzCDNConfig()
        cc = CacheController(config)
        pop = PoP(name="test")
        cc.put(pop, "/api/a", b"1")
        cc.put(pop, "/api/b", b"2")
        cc.put(pop, "/other", b"3")
        count = cc.purge_prefix([pop], "/api/")
        assert count >= 2

    def test_purge_tag(self):
        config = FizzCDNConfig()
        cc = CacheController(config)
        pop = PoP(name="test")
        cc.put(pop, "/a", b"1", tags={"fizz"})
        cc.put(pop, "/b", b"2", tags={"buzz"})
        count = cc.purge_tag([pop], "fizz")
        assert count >= 1


class TestOriginPuller:
    def test_pull_html(self):
        op = OriginPuller(FizzCDNConfig())
        content, ct = op.pull("/index.html")
        assert b"FizzBuzz" in content

    def test_pull_api(self):
        op = OriginPuller(FizzCDNConfig())
        content, ct = op.pull("/api/fizzbuzz/15")
        assert b"FizzBuzz" in content
        assert ct == "text/html"  # Default content type for simulated origin

    def test_pull_count(self):
        op = OriginPuller(FizzCDNConfig())
        op.pull("/a")
        op.pull("/b")
        assert op.pull_count == 2


class TestCDNEngine:
    def test_handle_request_miss(self, engine):
        req = CDNRequest(url="/new-page", client_lat=40.0, client_lon=-74.0)
        resp = engine.handle_request(req)
        assert resp.status == 200
        assert resp.cache_status == CacheStatus.MISS

    def test_handle_request_hit(self, engine):
        req = CDNRequest(url="/api/fizzbuzz/15", client_lat=40.0, client_lon=-74.0)
        resp1 = engine.handle_request(req)
        resp2 = engine.handle_request(req)
        assert resp2.cache_status == CacheStatus.HIT

    def test_preload(self, engine):
        count = engine.preload("/preloaded")
        assert count == 5  # All PoPs

    def test_purge(self, engine):
        engine.handle_request(CDNRequest(url="/to-purge", client_lat=0, client_lon=0))
        count = engine.purge("/to-purge")
        assert count >= 1

    def test_list_pops(self, engine):
        assert len(engine.list_pops()) == 5

    def test_get_pop(self, engine):
        assert engine.get_pop("us-east") is not None
        assert engine.get_pop("nonexistent") is None

    def test_metrics(self, engine):
        engine.handle_request(CDNRequest(url="/test", client_lat=0, client_lon=0))
        m = engine.get_metrics()
        assert m.total_requests >= 1

    def test_hit_rate(self, engine):
        for _ in range(5):
            engine.handle_request(CDNRequest(url="/cached", client_lat=40, client_lon=-74))
        m = engine.get_metrics()
        assert m.hit_rate > 0

    def test_uptime(self, engine):
        assert engine.uptime > 0
        assert engine.is_running

    def test_fizzbuzz_api(self, engine):
        resp = engine.handle_request(CDNRequest(url="/api/fizzbuzz/9", client_lat=35, client_lon=139))
        assert b"Fizz" in resp.content


class TestFizzCDNMiddleware:
    def test_get_name(self, subsystem):
        _, _, mw = subsystem
        assert mw.get_name() == "fizzcdn"

    def test_get_priority(self, subsystem):
        _, _, mw = subsystem
        assert mw.get_priority() == MIDDLEWARE_PRIORITY

    def test_process(self, subsystem):
        _, _, mw = subsystem
        ctx = MagicMock(); ctx.metadata = {}
        mw.process(ctx, None)
        assert ctx.metadata["fizzcdn_version"] == FIZZCDN_VERSION

    def test_render_dashboard(self, subsystem):
        _, _, mw = subsystem
        assert "FizzCDN" in mw.render_dashboard()

    def test_render_status(self, subsystem):
        _, _, mw = subsystem
        assert "UP" in mw.render_status()

    def test_render_analytics(self, subsystem):
        _, _, mw = subsystem
        output = mw.render_analytics()
        assert "Hit Rate" in output

    def test_render_cache_stats(self, subsystem):
        _, _, mw = subsystem
        output = mw.render_cache_stats()
        assert "Cache" in output


class TestCreateSubsystem:
    def test_returns_tuple(self):
        assert len(create_fizzcdn_subsystem()) == 3

    def test_default_pops(self):
        e, _, _ = create_fizzcdn_subsystem()
        assert len(e.list_pops()) == 5

    def test_custom_pops(self):
        e, _, _ = create_fizzcdn_subsystem(num_pops=3)
        assert len(e.list_pops()) == 3

    def test_preloaded_content(self):
        e, _, _ = create_fizzcdn_subsystem()
        req = CDNRequest(url="/api/fizzbuzz/15", client_lat=40, client_lon=-74)
        resp = e.handle_request(req)
        assert resp.cache_status == CacheStatus.HIT


class TestConstants:
    def test_version(self):
        assert FIZZCDN_VERSION == "1.0.0"
    def test_priority(self):
        assert MIDDLEWARE_PRIORITY == 130
