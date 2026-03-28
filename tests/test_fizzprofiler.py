"""Tests for enterprise_fizzbuzz.infrastructure.fizzprofiler"""
from __future__ import annotations
from unittest.mock import MagicMock
import pytest
from enterprise_fizzbuzz.infrastructure.fizzprofiler import (
    FIZZPROFILER_VERSION, MIDDLEWARE_PRIORITY, ProfileType,
    FizzProfilerConfig, ProfilerEngine, FizzProfilerDashboard,
    FizzProfilerMiddleware, create_fizzprofiler_subsystem,
)

@pytest.fixture
def subsystem():
    return create_fizzprofiler_subsystem()

class TestProfilerEngine:
    def test_capture_cpu(self):
        e = ProfilerEngine(FizzProfilerConfig()); e.start()
        s = e.capture_profile(ProfileType.CPU, 200)
        assert s.total_samples > 0
        assert len(s.hotspots) > 0

    def test_capture_memory(self):
        e = ProfilerEngine(FizzProfilerConfig()); e.start()
        s = e.capture_profile(ProfileType.MEMORY, 200)
        assert s.total_samples > 0

    def test_hotspot_ranking(self):
        e = ProfilerEngine(FizzProfilerConfig()); e.start()
        s = e.capture_profile()
        assert s.hotspots[0].rank == 1
        assert s.hotspots[0].self_time_pct >= s.hotspots[-1].self_time_pct

    def test_call_graph(self):
        e = ProfilerEngine(FizzProfilerConfig()); e.start()
        s = e.capture_profile()
        assert s.call_graph is not None
        assert s.call_graph.function == "<root>"
        assert len(s.call_graph.children) > 0

    def test_callgraph_ascii(self):
        e = ProfilerEngine(FizzProfilerConfig()); e.start()
        s = e.capture_profile()
        output = e.render_callgraph_ascii(s.call_graph)
        assert "<root>" in output

    def test_baseline_comparison(self):
        e = ProfilerEngine(FizzProfilerConfig()); e.start()
        s1 = e.capture_profile()
        e.set_baseline(s1.session_id)
        s2 = e.capture_profile()
        regressions = e.compare_baseline(s2)
        assert isinstance(regressions, list)

    def test_metrics(self):
        e = ProfilerEngine(FizzProfilerConfig()); e.start()
        e.capture_profile()
        m = e.get_metrics()
        assert m.sessions == 1
        assert m.total_samples > 0

    def test_list_sessions(self):
        e = ProfilerEngine(FizzProfilerConfig()); e.start()
        e.capture_profile()
        e.capture_profile()
        assert len(e.list_sessions()) == 2

class TestFizzProfilerMiddleware:
    def test_get_name(self, subsystem):
        _, _, mw = subsystem
        assert mw.get_name() == "fizzprofiler"

    def test_get_priority(self, subsystem):
        _, _, mw = subsystem
        assert mw.get_priority() == MIDDLEWARE_PRIORITY

    def test_process(self, subsystem):
        _, _, mw = subsystem
        ctx = MagicMock(); ctx.metadata = {}
        mw.process(ctx, None)
        assert ctx.metadata["fizzprofiler_version"] == FIZZPROFILER_VERSION

    def test_render_dashboard(self, subsystem):
        _, _, mw = subsystem
        assert "FizzProfiler" in mw.render_dashboard()

    def test_render_hotspots(self, subsystem):
        _, _, mw = subsystem
        output = mw.render_hotspots()
        assert "Hotspots" in output

    def test_render_callgraph(self, subsystem):
        _, _, mw = subsystem
        output = mw.render_callgraph()
        assert "<root>" in output

class TestCreateSubsystem:
    def test_returns_tuple(self):
        assert len(create_fizzprofiler_subsystem()) == 3

    def test_baseline_captured(self):
        e, _, _ = create_fizzprofiler_subsystem()
        assert e._baseline is not None
