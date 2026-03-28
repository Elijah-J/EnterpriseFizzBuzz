"""
Enterprise FizzBuzz Platform - FizzCapacityPlanner Capacity Planning Tests

Comprehensive test suite for the FizzCapacityPlanner subsystem, validating
demand forecasting accuracy, resource saturation projections, scaling
recommendation generation, middleware pipeline integration, and dashboard
rendering.

Capacity planning is indispensable for enterprise FizzBuzz deployments
operating at scale. Without proactive demand forecasting and scaling
recommendations, operators risk exhausting modulo-computation resources
during peak divisibility-check windows, leading to SLA violations and
unplanned downtime in critical FizzBuzz pipelines.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, AsyncMock

import pytest

from enterprise_fizzbuzz.infrastructure.fizzcapacityplanner import (
    FIZZCAPACITYPLANNER_VERSION,
    MIDDLEWARE_PRIORITY,
    ResourceType,
    ScalingDirection,
    FizzCapacityPlannerConfig,
    ResourceUsage,
    ScalingRecommendation,
    DemandForecaster,
    CapacityPlanner,
    FizzCapacityPlannerDashboard,
    FizzCapacityPlannerMiddleware,
    create_fizzcapacityplanner_subsystem,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def forecaster():
    """Fresh DemandForecaster for each test."""
    return DemandForecaster()


@pytest.fixture
def planner():
    """Fresh CapacityPlanner with pre-registered resources."""
    p = CapacityPlanner()
    p.add_resource(ResourceType.CPU, 100.0)
    p.add_resource(ResourceType.MEMORY, 8192.0)
    return p


# ============================================================
# TestConstants
# ============================================================


class TestConstants:
    """Validate module-level constants for version pinning and middleware
    integration ordering."""

    def test_version_string(self):
        """Module version must follow semver and match the published contract."""
        assert FIZZCAPACITYPLANNER_VERSION == "1.0.0"

    def test_middleware_priority(self):
        """Middleware priority must be 190 to slot correctly in the pipeline."""
        assert MIDDLEWARE_PRIORITY == 190


# ============================================================
# TestDemandForecaster
# ============================================================


class TestDemandForecaster:
    """Validate the DemandForecaster's time-series recording, trend
    detection, and horizon-based forecasting capabilities."""

    def test_record_and_forecast_returns_list(self, forecaster):
        """Recording usage samples and forecasting must return a list of
        projected values whose length matches the requested horizon."""
        base = time.time()
        for i in range(10):
            forecaster.record(ResourceType.CPU, 50.0 + i, base + i * 3600)
        result = forecaster.forecast(ResourceType.CPU, horizon_hours=5)
        assert isinstance(result, list)
        assert len(result) == 5

    def test_trend_increasing(self, forecaster):
        """Monotonically increasing usage must yield an 'increasing' trend."""
        base = time.time()
        for i in range(10):
            forecaster.record(ResourceType.MEMORY, 100.0 + i * 50, base + i * 3600)
        assert forecaster.get_trend(ResourceType.MEMORY) == "increasing"

    def test_trend_decreasing(self, forecaster):
        """Monotonically decreasing usage must yield a 'decreasing' trend."""
        base = time.time()
        for i in range(10):
            forecaster.record(ResourceType.DISK, 1000.0 - i * 50, base + i * 3600)
        assert forecaster.get_trend(ResourceType.DISK) == "decreasing"

    def test_trend_stable(self, forecaster):
        """Flat usage with negligible variance must yield a 'stable' trend."""
        base = time.time()
        for i in range(10):
            forecaster.record(ResourceType.NETWORK, 500.0, base + i * 3600)
        assert forecaster.get_trend(ResourceType.NETWORK) == "stable"


# ============================================================
# TestCapacityPlanner
# ============================================================


class TestCapacityPlanner:
    """Validate the CapacityPlanner's resource registration, usage tracking,
    utilization computation, scaling recommendations, and saturation
    projection."""

    def test_record_usage_returns_resource_usage(self, planner):
        """Recording usage must return a ResourceUsage with correct fields."""
        usage = planner.record_usage(ResourceType.CPU, 75.0)
        assert isinstance(usage, ResourceUsage)
        assert usage.resource_type == ResourceType.CPU
        assert usage.current_usage == 75.0
        assert usage.capacity == 100.0

    def test_utilization_percentage_calculated(self, planner):
        """Utilization percentage must equal (current_usage / capacity) * 100."""
        usage = planner.record_usage(ResourceType.CPU, 50.0)
        assert abs(usage.utilization_pct - 50.0) < 0.01

    def test_recommendations_scale_up_on_high_usage(self, planner):
        """When utilization exceeds the scale-up threshold, recommendations
        must include a ScalingDirection.UP entry for that resource."""
        for _ in range(5):
            planner.record_usage(ResourceType.CPU, 90.0)
        recs = planner.get_recommendations()
        cpu_recs = [r for r in recs if r.resource_type == ResourceType.CPU]
        assert len(cpu_recs) >= 1
        assert cpu_recs[0].direction == ScalingDirection.UP
        assert isinstance(cpu_recs[0].reason, str)
        assert len(cpu_recs[0].reason) > 0

    def test_recommendations_scale_down_on_low_usage(self, planner):
        """When utilization stays well below the scale-down threshold,
        recommendations must include a ScalingDirection.DOWN entry."""
        for _ in range(5):
            planner.record_usage(ResourceType.MEMORY, 200.0)
        recs = planner.get_recommendations()
        mem_recs = [r for r in recs if r.resource_type == ResourceType.MEMORY]
        assert len(mem_recs) >= 1
        assert mem_recs[0].direction == ScalingDirection.DOWN

    def test_recommendations_none_on_normal_usage(self, planner):
        """When utilization is in the normal band, recommendations for that
        resource must be ScalingDirection.NONE or absent."""
        for _ in range(5):
            planner.record_usage(ResourceType.CPU, 50.0)
        recs = planner.get_recommendations()
        cpu_recs = [r for r in recs if r.resource_type == ResourceType.CPU]
        if cpu_recs:
            assert cpu_recs[0].direction == ScalingDirection.NONE

    def test_saturation_time_increasing_trend(self, planner):
        """When usage is trending upward, get_saturation_time must return
        a positive float representing hours until capacity is reached."""
        base = time.time()
        for i in range(10):
            planner.record_usage(ResourceType.CPU, 50.0 + i * 5)
        sat_hours = planner.get_saturation_time(ResourceType.CPU)
        assert isinstance(sat_hours, float)
        assert sat_hours > 0

    def test_saturation_time_not_trending_up(self, planner):
        """When usage is stable or decreasing, get_saturation_time must
        return -1 to indicate no projected saturation."""
        for i in range(10):
            planner.record_usage(ResourceType.MEMORY, 4000.0)
        sat_hours = planner.get_saturation_time(ResourceType.MEMORY)
        assert sat_hours == -1


# ============================================================
# TestDashboard
# ============================================================


class TestDashboard:
    """Validate the FizzCapacityPlannerDashboard renders meaningful
    operational data."""

    def test_render_returns_string(self):
        """Dashboard render must return a non-empty string."""
        planner, dashboard, _ = create_fizzcapacityplanner_subsystem()
        planner.add_resource(ResourceType.CPU, 100.0)
        planner.record_usage(ResourceType.CPU, 60.0)
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_contains_resource_info(self):
        """Dashboard output must contain recognizable resource information."""
        planner, dashboard, _ = create_fizzcapacityplanner_subsystem()
        planner.add_resource(ResourceType.CPU, 100.0)
        planner.record_usage(ResourceType.CPU, 75.0)
        output = dashboard.render()
        assert "CPU" in output.upper()


# ============================================================
# TestMiddleware
# ============================================================


class TestMiddleware:
    """Validate FizzCapacityPlannerMiddleware conforms to the middleware
    pipeline contract."""

    def test_get_name(self):
        """Middleware name must be 'fizzcapacityplanner'."""
        _, _, mw = create_fizzcapacityplanner_subsystem()
        assert mw.get_name() == "fizzcapacityplanner"

    def test_get_priority(self):
        """Middleware priority must match the module constant."""
        _, _, mw = create_fizzcapacityplanner_subsystem()
        assert mw.get_priority() == 190

    def test_process_calls_next(self):
        """Middleware must invoke the next handler in the pipeline and
        return its result."""
        _, _, mw = create_fizzcapacityplanner_subsystem()
        ctx = MagicMock()
        next_handler = MagicMock(return_value="fizz_result")
        result = mw.process(ctx, next_handler)
        next_handler.assert_called_once()
        assert result == "fizz_result"


# ============================================================
# TestCreateSubsystem
# ============================================================


class TestCreateSubsystem:
    """Validate the factory function returns correctly typed and wired
    components."""

    def test_returns_tuple_of_three(self):
        """Factory must return a 3-tuple."""
        result = create_fizzcapacityplanner_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_component_types(self):
        """Each element of the tuple must be the correct type."""
        planner, dashboard, middleware = create_fizzcapacityplanner_subsystem()
        assert isinstance(planner, CapacityPlanner)
        assert isinstance(dashboard, FizzCapacityPlannerDashboard)
        assert isinstance(middleware, FizzCapacityPlannerMiddleware)

    def test_subsystem_planner_is_functional(self):
        """The planner returned by the factory must accept resource
        registration and usage recording without error."""
        planner, _, _ = create_fizzcapacityplanner_subsystem()
        planner.add_resource(ResourceType.DISK, 500.0)
        usage = planner.record_usage(ResourceType.DISK, 250.0)
        assert usage.resource_type == ResourceType.DISK
        assert abs(usage.utilization_pct - 50.0) < 0.01
