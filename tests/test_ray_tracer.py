"""
Enterprise FizzBuzz Platform - FizzTrace Ray Tracer Test Suite

Comprehensive verification of the physically-based ray tracing pipeline,
from fundamental vector arithmetic through material scattering, ray-sphere
intersection, camera projection, Monte Carlo path tracing, PPM output
encoding, scene construction from FizzBuzz classifications, and middleware
integration.

Photorealistic rendering correctness is not merely a visual nicety — it is
the foundation upon which operators base their classification verification
decisions. A numerically incorrect reflection vector could cause a Fizz
sphere to appear Buzz-like, leading to downstream confusion and potential
compliance violations in audit scenarios.

Test resolution and sample counts are kept deliberately low (80x60, 4-10 SPP)
to ensure the full suite completes within seconds. Production renders would
use higher settings, but the mathematical correctness verified here is
resolution-independent.
"""

from __future__ import annotations

import math
import os
import random
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Callable
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.ray_tracer import (
    DEFAULT_HEIGHT,
    DEFAULT_SAMPLES_PER_PIXEL,
    DEFAULT_WIDTH,
    EPSILON,
    GAMMA,
    INF,
    MAX_BOUNCE_DEPTH,
    Camera,
    FizzBuzzSceneBuilder,
    HitRecord,
    Material,
    MaterialType,
    PathTracer,
    PPMWriter,
    Ray,
    RenderDashboard,
    RenderMiddleware,
    Scene,
    Sphere,
    Vec3,
    _schlick_reflectance,
    buzz_material,
    fizz_material,
    fizzbuzz_material,
    ground_material,
    plain_material,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
    RuleDefinition,
    RuleMatch,
)


# ============================================================
# Helpers
# ============================================================


def _make_context(number: int, output: str = "", matched_rules: list | None = None) -> ProcessingContext:
    """Create a ProcessingContext with a FizzBuzzResult for testing."""
    ctx = ProcessingContext(number=number, session_id=str(uuid.uuid4()))
    rules = matched_rules or []
    result = FizzBuzzResult(number=number, output=output or str(number), matched_rules=rules)
    ctx.results.append(result)
    return ctx


def _fizz_rule_match(number: int = 3) -> RuleMatch:
    return RuleMatch(rule=RuleDefinition(name="FizzRule", divisor=3, label="Fizz", priority=1), number=number)


def _buzz_rule_match(number: int = 5) -> RuleMatch:
    return RuleMatch(rule=RuleDefinition(name="BuzzRule", divisor=5, label="Buzz", priority=2), number=number)


def _identity_handler(ctx: ProcessingContext) -> ProcessingContext:
    return ctx


# ============================================================
# Vec3 Tests
# ============================================================


class TestVec3:
    """Verification of 3D vector arithmetic operations."""

    def test_default_construction(self) -> None:
        v = Vec3()
        assert v.x == 0.0
        assert v.y == 0.0
        assert v.z == 0.0

    def test_parameterized_construction(self) -> None:
        v = Vec3(1.0, 2.0, 3.0)
        assert v.x == 1.0
        assert v.y == 2.0
        assert v.z == 3.0

    def test_addition(self) -> None:
        a = Vec3(1.0, 2.0, 3.0)
        b = Vec3(4.0, 5.0, 6.0)
        result = a + b
        assert result == Vec3(5.0, 7.0, 9.0)

    def test_subtraction(self) -> None:
        a = Vec3(4.0, 5.0, 6.0)
        b = Vec3(1.0, 2.0, 3.0)
        result = a - b
        assert result == Vec3(3.0, 3.0, 3.0)

    def test_scalar_multiplication(self) -> None:
        v = Vec3(1.0, 2.0, 3.0)
        result = v * 2.0
        assert result == Vec3(2.0, 4.0, 6.0)

    def test_reverse_scalar_multiplication(self) -> None:
        v = Vec3(1.0, 2.0, 3.0)
        result = 2.0 * v
        assert result == Vec3(2.0, 4.0, 6.0)

    def test_component_wise_multiplication(self) -> None:
        a = Vec3(1.0, 2.0, 3.0)
        b = Vec3(4.0, 5.0, 6.0)
        result = a * b
        assert result == Vec3(4.0, 10.0, 18.0)

    def test_division(self) -> None:
        v = Vec3(2.0, 4.0, 6.0)
        result = v / 2.0
        assert result == Vec3(1.0, 2.0, 3.0)

    def test_negation(self) -> None:
        v = Vec3(1.0, -2.0, 3.0)
        result = -v
        assert result == Vec3(-1.0, 2.0, -3.0)

    def test_dot_product(self) -> None:
        a = Vec3(1.0, 2.0, 3.0)
        b = Vec3(4.0, 5.0, 6.0)
        assert abs(a.dot(b) - 32.0) < EPSILON

    def test_dot_product_orthogonal(self) -> None:
        a = Vec3(1.0, 0.0, 0.0)
        b = Vec3(0.0, 1.0, 0.0)
        assert abs(a.dot(b)) < EPSILON

    def test_cross_product(self) -> None:
        a = Vec3(1.0, 0.0, 0.0)
        b = Vec3(0.0, 1.0, 0.0)
        result = a.cross(b)
        assert result == Vec3(0.0, 0.0, 1.0)

    def test_cross_product_anticommutative(self) -> None:
        a = Vec3(1.0, 2.0, 3.0)
        b = Vec3(4.0, 5.0, 6.0)
        assert a.cross(b) == -(b.cross(a))

    def test_length(self) -> None:
        v = Vec3(3.0, 4.0, 0.0)
        assert abs(v.length() - 5.0) < EPSILON

    def test_length_squared(self) -> None:
        v = Vec3(3.0, 4.0, 0.0)
        assert abs(v.length_squared() - 25.0) < EPSILON

    def test_normalize(self) -> None:
        v = Vec3(3.0, 0.0, 0.0)
        n = v.normalize()
        assert abs(n.length() - 1.0) < EPSILON
        assert n == Vec3(1.0, 0.0, 0.0)

    def test_normalize_zero_vector(self) -> None:
        v = Vec3(0.0, 0.0, 0.0)
        n = v.normalize()
        assert n == Vec3(0.0, 0.0, 0.0)

    def test_near_zero(self) -> None:
        v = Vec3(1e-9, 1e-9, 1e-9)
        assert v.near_zero()

    def test_not_near_zero(self) -> None:
        v = Vec3(1.0, 0.0, 0.0)
        assert not v.near_zero()

    def test_reflect(self) -> None:
        # Reflecting a downward ray off a horizontal surface
        v = Vec3(1.0, -1.0, 0.0)
        n = Vec3(0.0, 1.0, 0.0)
        r = Vec3.reflect(v, n)
        assert r == Vec3(1.0, 1.0, 0.0)

    def test_reflect_normal_incidence(self) -> None:
        v = Vec3(0.0, -1.0, 0.0)
        n = Vec3(0.0, 1.0, 0.0)
        r = Vec3.reflect(v, n)
        assert r == Vec3(0.0, 1.0, 0.0)

    def test_refract_straight_through(self) -> None:
        # Normal incidence, same medium — should pass straight through
        uv = Vec3(0.0, -1.0, 0.0)
        n = Vec3(0.0, 1.0, 0.0)
        r = Vec3.refract(uv, n, 1.0)
        assert abs(r.x) < EPSILON
        assert abs(r.y - (-1.0)) < EPSILON
        assert abs(r.z) < EPSILON

    def test_refract_snells_law(self) -> None:
        # Verify Snell's law: n1*sin(theta1) = n2*sin(theta2)
        angle = math.radians(30)
        uv = Vec3(math.sin(angle), -math.cos(angle), 0.0)
        n = Vec3(0.0, 1.0, 0.0)
        eta = 1.0 / 1.5
        r = Vec3.refract(uv, n, eta)
        sin_refracted = math.sqrt(r.x * r.x + r.z * r.z)
        # n1 * sin(30) should equal n2 * sin(refracted_angle)
        # => 1.0 * 0.5 = 1.5 * sin_refracted => sin_refracted ~ 0.333
        expected = math.sin(angle) * eta  # = sin(30) / 1.5
        assert abs(sin_refracted - abs(expected)) < 0.01

    def test_random_in_unit_sphere(self) -> None:
        random.seed(42)
        for _ in range(100):
            v = Vec3.random_in_unit_sphere()
            assert v.length_squared() < 1.0

    def test_random_unit_vector(self) -> None:
        random.seed(42)
        for _ in range(100):
            v = Vec3.random_unit_vector()
            assert abs(v.length() - 1.0) < 0.01

    def test_random_in_hemisphere(self) -> None:
        random.seed(42)
        normal = Vec3(0.0, 1.0, 0.0)
        for _ in range(100):
            v = Vec3.random_in_hemisphere(normal)
            assert v.dot(normal) >= 0.0

    def test_equality_within_epsilon(self) -> None:
        a = Vec3(1.0, 2.0, 3.0)
        b = Vec3(1.0 + 1e-9, 2.0 - 1e-9, 3.0 + 1e-9)
        assert a == b

    def test_inequality(self) -> None:
        a = Vec3(1.0, 2.0, 3.0)
        b = Vec3(1.0, 2.0, 4.0)
        assert a != b

    def test_repr(self) -> None:
        v = Vec3(1.0, 2.0, 3.0)
        r = repr(v)
        assert "Vec3" in r
        assert "1.0000" in r


# ============================================================
# Ray Tests
# ============================================================


class TestRay:
    """Verification of ray parametric evaluation."""

    def test_ray_at_origin(self) -> None:
        r = Ray(origin=Vec3(0.0, 0.0, 0.0), direction=Vec3(1.0, 0.0, 0.0))
        assert r.at(0.0) == Vec3(0.0, 0.0, 0.0)

    def test_ray_at_t(self) -> None:
        r = Ray(origin=Vec3(1.0, 2.0, 3.0), direction=Vec3(1.0, 0.0, 0.0))
        assert r.at(2.0) == Vec3(3.0, 2.0, 3.0)

    def test_ray_at_negative_t(self) -> None:
        r = Ray(origin=Vec3(0.0, 0.0, 0.0), direction=Vec3(1.0, 0.0, 0.0))
        assert r.at(-1.0) == Vec3(-1.0, 0.0, 0.0)


# ============================================================
# Material Tests
# ============================================================


class TestMaterial:
    """Verification of physically-based material models."""

    def test_lambertian_scatter(self) -> None:
        random.seed(42)
        mat = Material(material_type=MaterialType.LAMBERTIAN, albedo=Vec3(0.5, 0.5, 0.5))
        ray_in = Ray(Vec3(0, 1, 0), Vec3(0, -1, 0))
        hit_point = Vec3(0, 0, 0)
        normal = Vec3(0, 1, 0)
        result = mat.scatter(ray_in, hit_point, normal, front_face=True)
        assert isinstance(result, tuple), "Lambertian material must scatter"
        attenuation, scattered = result
        assert attenuation == mat.albedo
        # Scattered ray should originate from hit point
        assert scattered.origin == hit_point

    def test_metal_scatter_reflects(self) -> None:
        random.seed(42)
        mat = Material(material_type=MaterialType.METAL, albedo=Vec3(0.8, 0.8, 0.8), fuzz=0.0)
        ray_in = Ray(Vec3(0, 1, 0), Vec3(0, -1, 0))
        normal = Vec3(0, 1, 0)
        result = mat.scatter(ray_in, Vec3(0, 0, 0), normal, front_face=True)
        assert isinstance(result, tuple), "Metal material must scatter on direct hit"
        attenuation, scattered = result
        # With zero fuzz, reflected ray should be along normal
        assert scattered.direction.dot(normal) > 0

    def test_metal_scatter_with_fuzz(self) -> None:
        random.seed(42)
        mat = Material(material_type=MaterialType.METAL, albedo=Vec3(0.8, 0.8, 0.8), fuzz=0.3)
        ray_in = Ray(Vec3(0, 1, 0), Vec3(0, -1, 0))
        normal = Vec3(0, 1, 0)
        result = mat.scatter(ray_in, Vec3(0, 0, 0), normal, front_face=True)
        # May or may not scatter depending on fuzz direction, but should not error
        assert result is None or result[1].direction.dot(normal) > 0

    def test_dielectric_scatter(self) -> None:
        random.seed(42)
        mat = Material(material_type=MaterialType.DIELECTRIC, refraction_index=1.5)
        ray_in = Ray(Vec3(0, 1, 0), Vec3(0, -1, 0))
        normal = Vec3(0, 1, 0)
        result = mat.scatter(ray_in, Vec3(0, 0, 0), normal, front_face=True)
        assert isinstance(result, tuple), "Dielectric material must scatter"
        attenuation, scattered = result
        # Dielectric always scatters with white attenuation
        assert attenuation == Vec3(1.0, 1.0, 1.0)

    def test_emissive_no_scatter(self) -> None:
        mat = Material(
            material_type=MaterialType.EMISSIVE,
            emission_color=Vec3(1.0, 0.8, 0.0),
            emission_strength=2.0,
        )
        ray_in = Ray(Vec3(0, 1, 0), Vec3(0, -1, 0))
        result = mat.scatter(ray_in, Vec3(0, 0, 0), Vec3(0, 1, 0), front_face=True)
        assert result is None

    def test_emissive_emitted_radiance(self) -> None:
        mat = Material(
            material_type=MaterialType.EMISSIVE,
            emission_color=Vec3(1.0, 0.5, 0.0),
            emission_strength=3.0,
        )
        emitted = mat.emitted()
        assert emitted == Vec3(3.0, 1.5, 0.0)

    def test_non_emissive_zero_emission(self) -> None:
        mat = Material(material_type=MaterialType.LAMBERTIAN)
        assert mat.emitted() == Vec3(0.0, 0.0, 0.0)


class TestSchlickReflectance:
    """Verification of Schlick's Fresnel approximation."""

    def test_normal_incidence(self) -> None:
        # At normal incidence for glass (n=1.5), reflectance ~ 4%
        r = _schlick_reflectance(1.0, 1.5)
        expected = ((1.0 - 1.5) / (1.0 + 1.5)) ** 2
        assert abs(r - expected) < 0.001

    def test_grazing_angle(self) -> None:
        # At grazing angles, reflectance approaches 1.0
        r = _schlick_reflectance(0.01, 1.5)
        assert r > 0.9

    def test_same_medium_normal_incidence(self) -> None:
        # Same medium (n=1) at normal incidence, reflectance = 0
        r = _schlick_reflectance(1.0, 1.0)
        assert abs(r) < EPSILON


# ============================================================
# HitRecord Tests
# ============================================================


class TestHitRecord:
    """Verification of intersection record normal orientation."""

    def test_front_face_detection(self) -> None:
        rec = HitRecord(
            point=Vec3(0, 0, 0),
            normal=Vec3(0, 1, 0),
            material=Material(material_type=MaterialType.LAMBERTIAN),
            t=1.0,
        )
        ray = Ray(Vec3(0, 1, 0), Vec3(0, -1, 0))
        outward_normal = Vec3(0, 1, 0)
        rec.set_face_normal(ray, outward_normal)
        assert rec.front_face is True
        assert rec.normal == Vec3(0, 1, 0)

    def test_back_face_detection(self) -> None:
        rec = HitRecord(
            point=Vec3(0, 0, 0),
            normal=Vec3(0, 1, 0),
            material=Material(material_type=MaterialType.LAMBERTIAN),
            t=1.0,
        )
        ray = Ray(Vec3(0, -1, 0), Vec3(0, 1, 0))
        outward_normal = Vec3(0, 1, 0)
        rec.set_face_normal(ray, outward_normal)
        assert rec.front_face is False
        assert rec.normal == Vec3(0, -1, 0)


# ============================================================
# Sphere Intersection Tests
# ============================================================


class TestSphere:
    """Verification of ray-sphere intersection via the quadratic formula."""

    def test_ray_hits_sphere(self) -> None:
        sphere = Sphere(
            center=Vec3(0, 0, -1),
            radius=0.5,
            material=Material(material_type=MaterialType.LAMBERTIAN),
        )
        ray = Ray(Vec3(0, 0, 0), Vec3(0, 0, -1))
        hit = sphere.hit(ray, 0.001, INF)
        assert isinstance(hit, HitRecord)
        assert abs(hit.t - 0.5) < 0.01

    def test_ray_misses_sphere(self) -> None:
        sphere = Sphere(
            center=Vec3(0, 0, -1),
            radius=0.5,
            material=Material(material_type=MaterialType.LAMBERTIAN),
        )
        ray = Ray(Vec3(0, 0, 0), Vec3(0, 1, 0))
        hit = sphere.hit(ray, 0.001, INF)
        assert hit is None

    def test_ray_inside_sphere(self) -> None:
        sphere = Sphere(
            center=Vec3(0, 0, 0),
            radius=1.0,
            material=Material(material_type=MaterialType.LAMBERTIAN),
        )
        ray = Ray(Vec3(0, 0, 0), Vec3(0, 0, -1))
        hit = sphere.hit(ray, 0.001, INF)
        assert isinstance(hit, HitRecord)
        # Should hit the far side
        assert hit.t > 0

    def test_intersection_normal_direction(self) -> None:
        sphere = Sphere(
            center=Vec3(0, 0, -2),
            radius=1.0,
            material=Material(material_type=MaterialType.LAMBERTIAN),
        )
        ray = Ray(Vec3(0, 0, 0), Vec3(0, 0, -1))
        hit = sphere.hit(ray, 0.001, INF)
        assert isinstance(hit, HitRecord)
        # Normal should point toward the camera (front face)
        assert hit.normal.z > 0

    def test_t_range_filtering(self) -> None:
        sphere = Sphere(
            center=Vec3(0, 0, -1),
            radius=0.5,
            material=Material(material_type=MaterialType.LAMBERTIAN),
        )
        ray = Ray(Vec3(0, 0, 0), Vec3(0, 0, -1))
        # Set t_min beyond the intersection
        hit = sphere.hit(ray, 2.0, INF)
        assert hit is None


# ============================================================
# Camera Tests
# ============================================================


class TestCamera:
    """Verification of perspective camera ray generation."""

    def test_center_ray(self) -> None:
        cam = Camera(
            lookfrom=Vec3(0, 0, 0),
            lookat=Vec3(0, 0, -1),
            vup=Vec3(0, 1, 0),
            vfov_degrees=90.0,
            aspect_ratio=1.0,
        )
        ray = cam.get_ray(0.5, 0.5)
        # Center ray should point roughly along -Z
        d = ray.direction.normalize()
        assert abs(d.x) < 0.1
        assert abs(d.y) < 0.1
        assert d.z < 0

    def test_corner_rays_diverge(self) -> None:
        cam = Camera(
            lookfrom=Vec3(0, 0, 0),
            lookat=Vec3(0, 0, -1),
            vup=Vec3(0, 1, 0),
            vfov_degrees=90.0,
            aspect_ratio=1.0,
        )
        top_left = cam.get_ray(0.0, 1.0).direction.normalize()
        bottom_right = cam.get_ray(1.0, 0.0).direction.normalize()
        # These should point in different directions
        assert top_left.dot(bottom_right) < 0.9


# ============================================================
# Scene Tests
# ============================================================


class TestScene:
    """Verification of scene intersection logic."""

    def test_empty_scene_no_hit(self) -> None:
        scene = Scene()
        ray = Ray(Vec3(0, 0, 0), Vec3(0, 0, -1))
        assert scene.hit(ray, 0.001, INF) is None

    def test_nearest_intersection(self) -> None:
        scene = Scene()
        mat = Material(material_type=MaterialType.LAMBERTIAN)
        scene.add(Sphere(Vec3(0, 0, -2), 0.5, mat))
        scene.add(Sphere(Vec3(0, 0, -4), 0.5, mat))
        ray = Ray(Vec3(0, 0, 0), Vec3(0, 0, -1))
        hit = scene.hit(ray, 0.001, INF)
        assert isinstance(hit, HitRecord)
        # Should hit the closer sphere
        assert abs(hit.t - 1.5) < 0.1

    def test_background_color(self) -> None:
        bg = Vec3(0.1, 0.2, 0.3)
        scene = Scene(background=bg)
        assert scene.background == bg


# ============================================================
# PathTracer Tests
# ============================================================


class TestPathTracer:
    """Verification of the Monte Carlo path tracing engine."""

    def test_background_color_for_miss(self) -> None:
        random.seed(42)
        tracer = PathTracer(samples_per_pixel=1, max_depth=2)
        scene = Scene()
        ray = Ray(Vec3(0, 0, 0), Vec3(0, 1, 0))
        color = tracer.ray_color(ray, scene, 2)
        # Looking up should give a sky-like color (blueish)
        assert color.y > 0.5

    def test_diffuse_sphere_not_black(self) -> None:
        random.seed(42)
        tracer = PathTracer(samples_per_pixel=4, max_depth=10)
        scene = Scene()
        mat = Material(material_type=MaterialType.LAMBERTIAN, albedo=Vec3(0.8, 0.2, 0.2))
        scene.add(Sphere(Vec3(0, 0, -1), 0.5, mat))
        ray = Ray(Vec3(0, 0, 0), Vec3(0, 0, -1))
        color = tracer.ray_color(ray, scene, 10)
        # Should have some color (not pure black)
        assert color.length() > 0.01

    def test_render_produces_pixels(self) -> None:
        random.seed(42)
        tracer = PathTracer(samples_per_pixel=1, max_depth=2)
        scene = Scene()
        camera = Camera(
            lookfrom=Vec3(0, 0, 0),
            lookat=Vec3(0, 0, -1),
            vup=Vec3(0, 1, 0),
            vfov_degrees=90.0,
            aspect_ratio=2.0,
        )
        pixels = tracer.render(scene, camera, 4, 2)
        assert len(pixels) == 2
        assert len(pixels[0]) == 4

    def test_render_tracks_ray_count(self) -> None:
        random.seed(42)
        tracer = PathTracer(samples_per_pixel=2, max_depth=2)
        scene = Scene()
        camera = Camera(
            lookfrom=Vec3(0, 0, 0),
            lookat=Vec3(0, 0, -1),
            vup=Vec3(0, 1, 0),
            vfov_degrees=90.0,
            aspect_ratio=1.0,
        )
        tracer.render(scene, camera, 4, 4)
        # Each pixel casts 2 samples, 4x4 = 16 pixels => 32 primary rays minimum
        assert tracer.total_rays_cast >= 32

    def test_emissive_sphere_contributes_light(self) -> None:
        random.seed(42)
        tracer = PathTracer(samples_per_pixel=4, max_depth=5)
        scene = Scene()
        emissive = Material(
            material_type=MaterialType.EMISSIVE,
            emission_color=Vec3(1.0, 1.0, 1.0),
            emission_strength=5.0,
        )
        scene.add(Sphere(Vec3(0, 0, -1), 0.5, emissive))
        ray = Ray(Vec3(0, 0, 0), Vec3(0, 0, -1))
        color = tracer.ray_color(ray, scene, 5)
        # Emissive sphere should produce bright color
        assert color.length() > 1.0

    def test_max_depth_zero_returns_black(self) -> None:
        tracer = PathTracer()
        scene = Scene()
        ray = Ray(Vec3(0, 0, 0), Vec3(0, 0, -1))
        color = tracer.ray_color(ray, scene, 0)
        assert color == Vec3(0, 0, 0)


# ============================================================
# PPMWriter Tests
# ============================================================


class TestPPMWriter:
    """Verification of PPM P3 image output encoding."""

    def test_encode_black(self) -> None:
        r, g, b = PPMWriter.encode_color(Vec3(0, 0, 0))
        assert r == 0
        assert g == 0
        assert b == 0

    def test_encode_white(self) -> None:
        r, g, b = PPMWriter.encode_color(Vec3(1.0, 1.0, 1.0))
        assert r == 255
        assert g == 255
        assert b == 255

    def test_encode_clamps_above_one(self) -> None:
        r, g, b = PPMWriter.encode_color(Vec3(2.0, 2.0, 2.0))
        assert r == 255
        assert g == 255
        assert b == 255

    def test_encode_clamps_below_zero(self) -> None:
        r, g, b = PPMWriter.encode_color(Vec3(-1.0, -1.0, -1.0))
        assert r == 0
        assert g == 0
        assert b == 0

    def test_gamma_correction_applied(self) -> None:
        # Mid-gray in linear space should be brighter after gamma
        r, g, b = PPMWriter.encode_color(Vec3(0.5, 0.5, 0.5))
        linear_mid = int(255.999 * 0.5)
        # Gamma-corrected value should be higher
        assert r > linear_mid

    def test_to_string_format(self) -> None:
        pixels = [[Vec3(1.0, 0.0, 0.0), Vec3(0.0, 1.0, 0.0)]]
        result = PPMWriter.to_string(pixels)
        assert result.startswith("P3\n2 1\n255\n")
        lines = result.strip().split("\n")
        assert len(lines) == 5  # header (3 lines) + 2 pixel lines

    def test_write_creates_file(self) -> None:
        pixels = [[Vec3(1.0, 0.0, 0.0)]]
        with tempfile.NamedTemporaryFile(suffix=".ppm", delete=False) as f:
            path = f.name
        try:
            count = PPMWriter.write(pixels, path)
            assert count == 1
            assert os.path.exists(path)
            with open(path, "r") as f:
                content = f.read()
            assert content.startswith("P3\n1 1\n255\n")
        finally:
            os.unlink(path)

    def test_empty_pixels(self) -> None:
        result = PPMWriter.to_string([])
        assert "0 0" in result

    def test_write_empty_returns_zero(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".ppm", delete=False) as f:
            path = f.name
        try:
            count = PPMWriter.write([], path)
            assert count == 0
        finally:
            if os.path.exists(path):
                os.unlink(path)


# ============================================================
# Material Preset Tests
# ============================================================


class TestMaterialPresets:
    """Verification of FizzBuzz classification material assignments."""

    def test_fizz_material_is_metal(self) -> None:
        mat = fizz_material()
        assert mat.material_type == MaterialType.METAL
        assert mat.albedo.y > mat.albedo.x  # Green dominant
        assert mat.fuzz == 0.1

    def test_buzz_material_is_dielectric(self) -> None:
        mat = buzz_material()
        assert mat.material_type == MaterialType.DIELECTRIC
        assert abs(mat.refraction_index - 1.52) < 0.01

    def test_fizzbuzz_material_is_emissive(self) -> None:
        mat = fizzbuzz_material()
        assert mat.material_type == MaterialType.EMISSIVE
        assert mat.emission_strength == 2.0
        # Gold color
        assert mat.emission_color.x > mat.emission_color.z

    def test_plain_material_is_lambertian(self) -> None:
        mat = plain_material()
        assert mat.material_type == MaterialType.LAMBERTIAN
        # Gray
        assert abs(mat.albedo.x - mat.albedo.y) < EPSILON
        assert abs(mat.albedo.y - mat.albedo.z) < EPSILON

    def test_ground_material_is_lambertian(self) -> None:
        mat = ground_material()
        assert mat.material_type == MaterialType.LAMBERTIAN
        assert mat.albedo.x > 0.5  # Light gray


# ============================================================
# FizzBuzzSceneBuilder Tests
# ============================================================


class TestFizzBuzzSceneBuilder:
    """Verification of FizzBuzz classification to 3D scene mapping."""

    def test_add_fizz_result(self) -> None:
        builder = FizzBuzzSceneBuilder()
        builder.add_result(3, "Fizz", is_fizz=True, is_buzz=False)
        assert builder.material_counts["fizz"] == 1
        assert len(builder.classifications) == 1

    def test_add_buzz_result(self) -> None:
        builder = FizzBuzzSceneBuilder()
        builder.add_result(5, "Buzz", is_fizz=False, is_buzz=True)
        assert builder.material_counts["buzz"] == 1

    def test_add_fizzbuzz_result(self) -> None:
        builder = FizzBuzzSceneBuilder()
        builder.add_result(15, "FizzBuzz", is_fizz=True, is_buzz=True)
        assert builder.material_counts["fizzbuzz"] == 1

    def test_add_plain_result(self) -> None:
        builder = FizzBuzzSceneBuilder()
        builder.add_result(7, "7", is_fizz=False, is_buzz=False)
        assert builder.material_counts["plain"] == 1

    def test_build_empty_scene_has_ground(self) -> None:
        builder = FizzBuzzSceneBuilder()
        scene = builder.build_scene()
        assert len(scene.objects) == 1  # Ground only

    def test_build_scene_object_count(self) -> None:
        builder = FizzBuzzSceneBuilder()
        for i in range(1, 16):
            is_fizz = i % 3 == 0
            is_buzz = i % 5 == 0
            output = ""
            if is_fizz:
                output += "Fizz"
            if is_buzz:
                output += "Buzz"
            if not output:
                output = str(i)
            builder.add_result(i, output, is_fizz=is_fizz, is_buzz=is_buzz)
        scene = builder.build_scene()
        # 15 classification spheres + 1 ground
        assert len(scene.objects) == 16

    def test_build_camera_returns_camera(self) -> None:
        builder = FizzBuzzSceneBuilder()
        builder.add_result(1, "1", is_fizz=False, is_buzz=False)
        camera = builder.build_camera(80, 60)
        assert isinstance(camera, Camera)

    def test_material_counts_accumulate(self) -> None:
        builder = FizzBuzzSceneBuilder()
        builder.add_result(3, "Fizz", is_fizz=True, is_buzz=False)
        builder.add_result(6, "Fizz", is_fizz=True, is_buzz=False)
        builder.add_result(5, "Buzz", is_fizz=False, is_buzz=True)
        assert builder.material_counts["fizz"] == 2
        assert builder.material_counts["buzz"] == 1


# ============================================================
# RenderDashboard Tests
# ============================================================


class TestRenderDashboard:
    """Verification of the ASCII render statistics dashboard."""

    def test_dashboard_contains_header(self) -> None:
        tracer = PathTracer(samples_per_pixel=4)
        builder = FizzBuzzSceneBuilder()
        builder.add_result(3, "Fizz", is_fizz=True, is_buzz=False)
        output = RenderDashboard.render(
            tracer=tracer,
            scene_builder=builder,
            width=80,
            height=60,
            render_time_ms=100.0,
        )
        assert "FIZZTRACE" in output

    def test_dashboard_contains_ray_stats(self) -> None:
        tracer = PathTracer(samples_per_pixel=4)
        tracer.total_rays_cast = 1000
        tracer.total_bounces = 500
        builder = FizzBuzzSceneBuilder()
        output = RenderDashboard.render(
            tracer=tracer,
            scene_builder=builder,
            width=80,
            height=60,
            render_time_ms=100.0,
        )
        assert "Total rays" in output
        assert "1,000" in output

    def test_dashboard_contains_material_legend(self) -> None:
        tracer = PathTracer()
        builder = FizzBuzzSceneBuilder()
        output = RenderDashboard.render(
            tracer=tracer,
            scene_builder=builder,
            width=80,
            height=60,
            render_time_ms=50.0,
        )
        assert "green metal" in output
        assert "blue glass" in output
        assert "gold emissive" in output
        assert "Lambertian" in output

    def test_dashboard_shows_output_path(self) -> None:
        tracer = PathTracer()
        builder = FizzBuzzSceneBuilder()
        output = RenderDashboard.render(
            tracer=tracer,
            scene_builder=builder,
            width=80,
            height=60,
            render_time_ms=50.0,
            output_path="/tmp/fizztrace.ppm",
        )
        assert "/tmp/fizztrace.ppm" in output
        assert "PPM P3" in output

    def test_dashboard_resolution_info(self) -> None:
        tracer = PathTracer(samples_per_pixel=8)
        builder = FizzBuzzSceneBuilder()
        output = RenderDashboard.render(
            tracer=tracer,
            scene_builder=builder,
            width=320,
            height=240,
            render_time_ms=500.0,
        )
        assert "320 x 240" in output
        assert "76,800 pixels" in output


# ============================================================
# RenderMiddleware Tests
# ============================================================


class TestRenderMiddleware:
    """Verification of the ray trace middleware pipeline integration."""

    def test_implements_imiddleware(self) -> None:
        builder = FizzBuzzSceneBuilder()
        tracer = PathTracer()
        mw = RenderMiddleware(builder, tracer)
        assert isinstance(mw, IMiddleware)

    def test_get_name(self) -> None:
        mw = RenderMiddleware(FizzBuzzSceneBuilder(), PathTracer())
        assert mw.get_name() == "RenderMiddleware"

    def test_get_priority(self) -> None:
        mw = RenderMiddleware(FizzBuzzSceneBuilder(), PathTracer())
        assert mw.get_priority() == 960

    def test_captures_fizz_result(self) -> None:
        builder = FizzBuzzSceneBuilder()
        tracer = PathTracer()
        mw = RenderMiddleware(builder, tracer)
        ctx = _make_context(3, "Fizz", [_fizz_rule_match(3)])
        mw.process(ctx, _identity_handler)
        assert mw.results_captured == 1
        assert builder.material_counts["fizz"] == 1

    def test_captures_buzz_result(self) -> None:
        builder = FizzBuzzSceneBuilder()
        tracer = PathTracer()
        mw = RenderMiddleware(builder, tracer)
        ctx = _make_context(5, "Buzz", [_buzz_rule_match(5)])
        mw.process(ctx, _identity_handler)
        assert builder.material_counts["buzz"] == 1

    def test_captures_fizzbuzz_result(self) -> None:
        builder = FizzBuzzSceneBuilder()
        tracer = PathTracer()
        mw = RenderMiddleware(builder, tracer)
        ctx = _make_context(15, "FizzBuzz", [_fizz_rule_match(15), _buzz_rule_match(15)])
        mw.process(ctx, _identity_handler)
        assert builder.material_counts["fizzbuzz"] == 1

    def test_captures_plain_result(self) -> None:
        builder = FizzBuzzSceneBuilder()
        tracer = PathTracer()
        mw = RenderMiddleware(builder, tracer)
        ctx = _make_context(7, "7", [])
        mw.process(ctx, _identity_handler)
        assert builder.material_counts["plain"] == 1

    def test_metadata_annotation(self) -> None:
        builder = FizzBuzzSceneBuilder()
        tracer = PathTracer()
        mw = RenderMiddleware(builder, tracer)
        ctx = _make_context(3, "Fizz", [_fizz_rule_match(3)])
        result = mw.process(ctx, _identity_handler)
        assert result.metadata.get("raytrace_material") == "metal_green"

    def test_render_scene_produces_pixels(self) -> None:
        random.seed(42)
        builder = FizzBuzzSceneBuilder()
        tracer = PathTracer(samples_per_pixel=1, max_depth=2)
        mw = RenderMiddleware(builder, tracer, width=4, height=3)

        for i in range(1, 6):
            is_fizz = i % 3 == 0
            is_buzz = i % 5 == 0
            output = ""
            if is_fizz:
                output += "Fizz"
            if is_buzz:
                output += "Buzz"
            if not output:
                output = str(i)
            ctx = _make_context(
                i, output,
                ([_fizz_rule_match(i)] if is_fizz else [])
                + ([_buzz_rule_match(i)] if is_buzz else []),
            )
            mw.process(ctx, _identity_handler)

        pixels = mw.render_scene()
        assert isinstance(pixels, list)
        assert len(pixels) == 3
        assert len(pixels[0]) == 4
        assert mw.rendered is True
        assert mw.render_time_ms > 0

    def test_render_scene_writes_ppm(self) -> None:
        random.seed(42)
        with tempfile.NamedTemporaryFile(suffix=".ppm", delete=False) as f:
            path = f.name

        try:
            builder = FizzBuzzSceneBuilder()
            tracer = PathTracer(samples_per_pixel=1, max_depth=2)
            mw = RenderMiddleware(builder, tracer, width=4, height=3, output_path=path)

            ctx = _make_context(7, "7", [])
            mw.process(ctx, _identity_handler)
            mw.render_scene()

            assert os.path.exists(path)
            with open(path, "r") as f:
                content = f.read()
            assert content.startswith("P3\n4 3\n255\n")
        finally:
            os.unlink(path)

    def test_render_scene_no_results_returns_none(self) -> None:
        builder = FizzBuzzSceneBuilder()
        tracer = PathTracer()
        mw = RenderMiddleware(builder, tracer)
        assert mw.render_scene() is None

    def test_multiple_results_accumulate(self) -> None:
        builder = FizzBuzzSceneBuilder()
        tracer = PathTracer()
        mw = RenderMiddleware(builder, tracer)
        for i in range(1, 11):
            ctx = _make_context(i, str(i), [])
            mw.process(ctx, _identity_handler)
        assert mw.results_captured == 10


# ============================================================
# Integration Test — Full Pipeline
# ============================================================


class TestFizzTraceIntegration:
    """End-to-end verification of the FizzTrace rendering pipeline.

    Exercises the complete path from FizzBuzz classification through
    scene construction, camera setup, Monte Carlo path tracing, and
    PPM output encoding. Uses minimal resolution and sample count to
    keep execution time under one second while still verifying the
    mathematical correctness of the entire pipeline.
    """

    def test_full_render_pipeline(self) -> None:
        random.seed(42)

        builder = FizzBuzzSceneBuilder()
        for i in range(1, 16):
            is_fizz = i % 3 == 0
            is_buzz = i % 5 == 0
            output = ""
            if is_fizz:
                output += "Fizz"
            if is_buzz:
                output += "Buzz"
            if not output:
                output = str(i)
            builder.add_result(i, output, is_fizz=is_fizz, is_buzz=is_buzz)

        scene = builder.build_scene()
        camera = builder.build_camera(80, 60)
        tracer = PathTracer(samples_per_pixel=4, max_depth=10)
        pixels = tracer.render(scene, camera, 80, 60)

        assert len(pixels) == 60
        assert len(pixels[0]) == 80

        # Verify PPM output
        ppm = PPMWriter.to_string(pixels)
        assert ppm.startswith("P3\n80 60\n255\n")

        # Verify statistics
        assert tracer.total_rays_cast > 80 * 60 * 4

    def test_full_render_to_file(self) -> None:
        random.seed(42)

        builder = FizzBuzzSceneBuilder()
        builder.add_result(3, "Fizz", is_fizz=True, is_buzz=False)
        builder.add_result(5, "Buzz", is_fizz=False, is_buzz=True)
        builder.add_result(15, "FizzBuzz", is_fizz=True, is_buzz=True)

        scene = builder.build_scene()
        camera = builder.build_camera(40, 30)
        tracer = PathTracer(samples_per_pixel=2, max_depth=5)
        pixels = tracer.render(scene, camera, 40, 30)

        with tempfile.NamedTemporaryFile(suffix=".ppm", delete=False) as f:
            path = f.name

        try:
            count = PPMWriter.write(pixels, path)
            assert count == 40 * 30
            with open(path, "r") as f:
                header = f.readline()
            assert header.strip() == "P3"
        finally:
            os.unlink(path)

    def test_dashboard_after_render(self) -> None:
        random.seed(42)

        builder = FizzBuzzSceneBuilder()
        for i in range(1, 6):
            builder.add_result(
                i,
                "Fizz" if i % 3 == 0 else ("Buzz" if i % 5 == 0 else str(i)),
                is_fizz=(i % 3 == 0),
                is_buzz=(i % 5 == 0),
            )

        scene = builder.build_scene()
        camera = builder.build_camera(20, 15)
        tracer = PathTracer(samples_per_pixel=2, max_depth=3)
        tracer.render(scene, camera, 20, 15)

        dashboard = RenderDashboard.render(
            tracer=tracer,
            scene_builder=builder,
            width=20,
            height=15,
            render_time_ms=50.0,
        )
        assert "FIZZTRACE" in dashboard
        assert "Total rays" in dashboard
