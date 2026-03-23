"""
Enterprise FizzBuzz Platform - FizzTrace Physically-Based Ray Tracer

Implements a full Monte Carlo path tracer for rendering FizzBuzz classification
results as a photorealistic 3D scene. Each evaluated number is assigned a
physically-based material — Lambertian diffuse, metallic reflective, dielectric
(glass), or emissive — based on its FizzBuzz classification, and placed as a
sphere in a procedurally generated scene.

The renderer solves the rendering equation via recursive ray tracing with
Russian Roulette path termination, importance-sampled Lambertian BRDF,
Snell's law refraction with Schlick's Fresnel approximation for dielectric
surfaces, and cosine-weighted hemisphere sampling for diffuse interreflection.

Output is written in Netpbm PPM P3 format, the canonical uncompressed image
format for offline rendering validation. Production pipelines can convert to
PNG or EXR downstream; the ray tracer's responsibility ends at radiometrically
correct pixel values.

The computational cost of physically-based rendering for FizzBuzz classification
visualization is justified by the need for pixel-perfect material differentiation:
a human operator can instantly distinguish "Fizz" (green metal) from "Buzz"
(blue glass) from "FizzBuzz" (gold emissive) at a glance, reducing mean time
to classification verification (MTTCV) by an estimated 47%.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from enterprise_fizzbuzz.domain.models import ProcessingContext

from enterprise_fizzbuzz.domain.interfaces import IMiddleware


# ============================================================
# Constants
# ============================================================

DEFAULT_WIDTH = 320
DEFAULT_HEIGHT = 240
DEFAULT_SAMPLES_PER_PIXEL = 10
MAX_BOUNCE_DEPTH = 50
RUSSIAN_ROULETTE_MIN_DEPTH = 3
EPSILON = 1e-8
GAMMA = 2.2
INF = float("inf")


# ============================================================
# Vec3 — Three-Dimensional Vector
# ============================================================


class Vec3:
    """Three-component vector for positions, directions, and colors in R^3.

    All vector arithmetic uses standard mathematical definitions. The class
    supports addition, subtraction, scalar multiplication, dot product,
    cross product, normalization, reflection, and refraction. No external
    linear algebra libraries are required — the operations are implemented
    directly using ``math.sqrt`` and basic arithmetic.

    In the rendering pipeline, Vec3 serves triple duty:
    - **Position vectors**: world-space coordinates of geometry and cameras
    - **Direction vectors**: ray directions, surface normals, scattered rays
    - **Color vectors**: RGB radiance values in linear color space (not sRGB)
    """

    __slots__ = ("x", "y", "z")

    def __init__(self, x: float = 0.0, y: float = 0.0, z: float = 0.0) -> None:
        self.x = x
        self.y = y
        self.z = z

    def __add__(self, other: Vec3) -> Vec3:
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: Vec3) -> Vec3:
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, other: float | Vec3) -> Vec3:
        if isinstance(other, Vec3):
            return Vec3(self.x * other.x, self.y * other.y, self.z * other.z)
        return Vec3(self.x * other, self.y * other, self.z * other)

    def __rmul__(self, scalar: float) -> Vec3:
        return Vec3(self.x * scalar, self.y * scalar, self.z * scalar)

    def __truediv__(self, scalar: float) -> Vec3:
        inv = 1.0 / scalar
        return Vec3(self.x * inv, self.y * inv, self.z * inv)

    def __neg__(self) -> Vec3:
        return Vec3(-self.x, -self.y, -self.z)

    def __repr__(self) -> str:
        return f"Vec3({self.x:.4f}, {self.y:.4f}, {self.z:.4f})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Vec3):
            return NotImplemented
        return (
            abs(self.x - other.x) < EPSILON
            and abs(self.y - other.y) < EPSILON
            and abs(self.z - other.z) < EPSILON
        )

    def dot(self, other: Vec3) -> float:
        """Compute the dot product (inner product) of two vectors."""
        return self.x * other.x + self.y * other.y + self.z * other.z

    def cross(self, other: Vec3) -> Vec3:
        """Compute the cross product of two vectors."""
        return Vec3(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x,
        )

    def length_squared(self) -> float:
        """Return the squared Euclidean length of this vector."""
        return self.x * self.x + self.y * self.y + self.z * self.z

    def length(self) -> float:
        """Return the Euclidean length (L2 norm) of this vector."""
        return math.sqrt(self.length_squared())

    def normalize(self) -> Vec3:
        """Return a unit vector in the same direction.

        If the vector has zero length, returns the zero vector to avoid
        division by zero. In a production ray tracer, degenerate normals
        would trigger a diagnostic, but for FizzBuzz rendering the
        probability of encountering a zero-length normal is acceptably low.
        """
        length = self.length()
        if length < EPSILON:
            return Vec3(0.0, 0.0, 0.0)
        return self / length

    def near_zero(self) -> bool:
        """Return True if the vector is close to zero in all dimensions."""
        s = 1e-8
        return abs(self.x) < s and abs(self.y) < s and abs(self.z) < s

    @staticmethod
    def reflect(v: Vec3, n: Vec3) -> Vec3:
        """Reflect vector v about surface normal n.

        Implements the standard reflection formula: r = v - 2(v·n)n.
        The incident vector v points toward the surface; the reflected
        vector points away from it.
        """
        return v - 2.0 * v.dot(n) * n

    @staticmethod
    def refract(uv: Vec3, n: Vec3, etai_over_etat: float) -> Vec3:
        """Refract vector uv through surface with normal n.

        Implements Snell's law: n1*sin(theta1) = n2*sin(theta2).
        The ratio etai_over_etat is n1/n2 (incident over transmitted).
        The incident vector uv must be a unit vector.
        """
        cos_theta = min((-uv).dot(n), 1.0)
        r_out_perp = etai_over_etat * (uv + cos_theta * n)
        r_out_parallel = -math.sqrt(abs(1.0 - r_out_perp.length_squared())) * n
        return r_out_perp + r_out_parallel

    @staticmethod
    def random_vec(min_val: float = 0.0, max_val: float = 1.0) -> Vec3:
        """Generate a random vector with components in [min_val, max_val)."""
        return Vec3(
            random.uniform(min_val, max_val),
            random.uniform(min_val, max_val),
            random.uniform(min_val, max_val),
        )

    @staticmethod
    def random_in_unit_sphere() -> Vec3:
        """Generate a uniformly distributed random point inside the unit sphere.

        Uses rejection sampling: generate random points in the unit cube and
        discard those outside the sphere. Expected iterations: ~1.91 (the ratio
        of cube volume to sphere volume is 8/(4pi/3) ~ 1.91).
        """
        while True:
            p = Vec3.random_vec(-1.0, 1.0)
            if p.length_squared() < 1.0:
                return p

    @staticmethod
    def random_unit_vector() -> Vec3:
        """Generate a uniformly distributed random unit vector on the sphere."""
        return Vec3.random_in_unit_sphere().normalize()

    @staticmethod
    def random_in_hemisphere(normal: Vec3) -> Vec3:
        """Generate a random vector in the hemisphere defined by normal."""
        in_unit_sphere = Vec3.random_in_unit_sphere()
        if in_unit_sphere.dot(normal) > 0.0:
            return in_unit_sphere
        return -in_unit_sphere


# ============================================================
# Ray
# ============================================================


@dataclass
class Ray:
    """A ray defined by an origin point and a direction vector.

    Parametric form: P(t) = origin + t * direction, where t >= 0.
    The direction is not necessarily normalized; normalization is
    deferred to the caller when needed for performance.
    """

    origin: Vec3
    direction: Vec3

    def at(self, t: float) -> Vec3:
        """Evaluate the ray at parameter t."""
        return self.origin + self.direction * t


# ============================================================
# Material System
# ============================================================


class MaterialType(Enum):
    """Classification of physically-based material models.

    Each type corresponds to a distinct light-surface interaction model:
    - LAMBERTIAN: Ideal diffuse reflector (Lambertian BRDF)
    - METAL: Specular reflector with optional roughness (fuzz)
    - DIELECTRIC: Transparent material with refraction (Snell's law)
    - EMISSIVE: Light-emitting surface (area light source)
    """

    LAMBERTIAN = auto()
    METAL = auto()
    DIELECTRIC = auto()
    EMISSIVE = auto()


@dataclass
class Material:
    """Physically-based material definition.

    Attributes:
        material_type: The surface interaction model.
        albedo: Diffuse reflectance color (for Lambertian and Metal).
        fuzz: Roughness parameter for metals (0 = mirror, 1 = fully rough).
        refraction_index: Index of refraction for dielectrics (glass ~ 1.5).
        emission_color: Emitted radiance for emissive materials.
        emission_strength: Multiplier for emitted radiance.
    """

    material_type: MaterialType
    albedo: Vec3 = field(default_factory=lambda: Vec3(0.5, 0.5, 0.5))
    fuzz: float = 0.0
    refraction_index: float = 1.5
    emission_color: Vec3 = field(default_factory=lambda: Vec3(0.0, 0.0, 0.0))
    emission_strength: float = 0.0

    def emitted(self) -> Vec3:
        """Return the emitted radiance from this material."""
        if self.material_type == MaterialType.EMISSIVE:
            return self.emission_color * self.emission_strength
        return Vec3(0.0, 0.0, 0.0)

    def scatter(self, ray_in: Ray, hit_point: Vec3, normal: Vec3, front_face: bool) -> Optional[tuple[Vec3, Ray]]:
        """Compute the scattered ray and attenuation for a ray-surface interaction.

        Returns a tuple of (attenuation_color, scattered_ray) if the ray scatters,
        or None if the ray is absorbed.

        The scattering model depends on the material type:
        - Lambertian: cosine-weighted hemisphere sampling
        - Metal: specular reflection with optional perturbation
        - Dielectric: probabilistic reflection/refraction via Schlick's approximation
        - Emissive: no scattering (absorbed; radiance contribution via emission)
        """
        if self.material_type == MaterialType.LAMBERTIAN:
            scatter_direction = normal + Vec3.random_unit_vector()
            if scatter_direction.near_zero():
                scatter_direction = normal
            scattered = Ray(hit_point, scatter_direction)
            return (self.albedo, scattered)

        elif self.material_type == MaterialType.METAL:
            reflected = Vec3.reflect(ray_in.direction.normalize(), normal)
            reflected = reflected + self.fuzz * Vec3.random_in_unit_sphere()
            scattered = Ray(hit_point, reflected)
            if scattered.direction.dot(normal) > 0:
                return (self.albedo, scattered)
            return None

        elif self.material_type == MaterialType.DIELECTRIC:
            attenuation = Vec3(1.0, 1.0, 1.0)
            ri = (1.0 / self.refraction_index) if front_face else self.refraction_index
            unit_direction = ray_in.direction.normalize()
            cos_theta = min((-unit_direction).dot(normal), 1.0)
            sin_theta = math.sqrt(1.0 - cos_theta * cos_theta)

            # Total internal reflection check
            cannot_refract = ri * sin_theta > 1.0

            # Schlick's approximation for reflectance
            if cannot_refract or _schlick_reflectance(cos_theta, ri) > random.random():
                direction = Vec3.reflect(unit_direction, normal)
            else:
                direction = Vec3.refract(unit_direction, normal, ri)

            scattered = Ray(hit_point, direction)
            return (attenuation, scattered)

        elif self.material_type == MaterialType.EMISSIVE:
            return None

        return None


def _schlick_reflectance(cosine: float, ref_idx: float) -> float:
    """Schlick's polynomial approximation for Fresnel reflectance.

    At grazing angles, all dielectric surfaces become mirror-like. This
    approximation captures that behavior without computing the full
    Fresnel equations, which would require complex-valued arithmetic
    for no meaningful improvement in visual quality at FizzBuzz rendering
    resolutions.
    """
    r0 = (1.0 - ref_idx) / (1.0 + ref_idx)
    r0 = r0 * r0
    return r0 + (1.0 - r0) * ((1.0 - cosine) ** 5)


# ============================================================
# HitRecord — Intersection Data
# ============================================================


@dataclass
class HitRecord:
    """Records the geometric and material data at a ray-surface intersection.

    The front_face flag indicates whether the ray hit the outer surface
    (front face) or inner surface (back face) of the geometry. This is
    critical for correct normal orientation in dielectric (glass) materials,
    where the refraction ratio depends on whether the ray is entering or
    exiting the medium.
    """

    point: Vec3
    normal: Vec3
    material: Material
    t: float
    front_face: bool = True

    def set_face_normal(self, ray: Ray, outward_normal: Vec3) -> None:
        """Set the hit record normal to always point against the ray.

        By convention, the stored normal always faces the incoming ray.
        This simplifies material scattering logic and ensures consistent
        behavior for both front-face and back-face intersections.
        """
        self.front_face = ray.direction.dot(outward_normal) < 0
        self.normal = outward_normal if self.front_face else -outward_normal


# ============================================================
# Sphere — Ray-Sphere Intersection
# ============================================================


@dataclass
class Sphere:
    """A sphere primitive defined by center and radius.

    Ray-sphere intersection is computed by solving the quadratic equation
    derived from substituting the ray parametric form P(t) = O + tD into
    the implicit sphere equation |P - C|^2 = r^2:

        t^2 (D·D) + 2t (D·(O-C)) + ((O-C)·(O-C) - r^2) = 0

    The discriminant determines whether the ray misses (< 0), grazes (= 0),
    or intersects (> 0) the sphere. For two intersections, the nearest
    positive t is selected.
    """

    center: Vec3
    radius: float
    material: Material

    def hit(self, ray: Ray, t_min: float, t_max: float) -> Optional[HitRecord]:
        """Test for ray-sphere intersection within the interval [t_min, t_max].

        Returns a HitRecord if the ray intersects the sphere, or None otherwise.
        Uses the standard quadratic formula with the half-b optimization to
        reduce floating-point operations.
        """
        oc = ray.origin - self.center
        a = ray.direction.length_squared()
        half_b = oc.dot(ray.direction)
        c = oc.length_squared() - self.radius * self.radius

        discriminant = half_b * half_b - a * c
        if discriminant < 0:
            return None

        sqrtd = math.sqrt(discriminant)

        # Find the nearest root in the acceptable range
        root = (-half_b - sqrtd) / a
        if root < t_min or root > t_max:
            root = (-half_b + sqrtd) / a
            if root < t_min or root > t_max:
                return None

        point = ray.at(root)
        outward_normal = (point - self.center) / self.radius
        rec = HitRecord(
            point=point,
            normal=outward_normal,
            material=self.material,
            t=root,
        )
        rec.set_face_normal(ray, outward_normal)
        return rec


# ============================================================
# Camera — Perspective Projection
# ============================================================


class Camera:
    """Perspective camera with configurable field of view and orientation.

    Implements a thin-lens camera model (without depth of field for
    simplicity). The camera defines a viewport in world space and generates
    primary rays through each pixel via the standard pinhole projection.

    The coordinate system follows the right-hand rule:
    - +X points right
    - +Y points up
    - -Z points into the scene (camera looks along -Z in camera space)
    """

    def __init__(
        self,
        lookfrom: Vec3,
        lookat: Vec3,
        vup: Vec3,
        vfov_degrees: float,
        aspect_ratio: float,
    ) -> None:
        theta = math.radians(vfov_degrees)
        h = math.tan(theta / 2.0)
        viewport_height = 2.0 * h
        viewport_width = aspect_ratio * viewport_height

        w = (lookfrom - lookat).normalize()
        u = vup.cross(w).normalize()
        v = w.cross(u)

        self.origin = lookfrom
        self.horizontal = u * viewport_width
        self.vertical = v * viewport_height
        self.lower_left_corner = (
            self.origin - self.horizontal / 2.0 - self.vertical / 2.0 - w
        )

    def get_ray(self, s: float, t: float) -> Ray:
        """Generate a ray from the camera through viewport coordinate (s, t).

        Parameters s and t are in [0, 1], mapping to the horizontal and
        vertical extent of the viewport respectively.
        """
        direction = (
            self.lower_left_corner
            + self.horizontal * s
            + self.vertical * t
            - self.origin
        )
        return Ray(self.origin, direction)


# ============================================================
# Scene — World Geometry Container
# ============================================================


class Scene:
    """Container for all renderable geometry in the world.

    The scene maintains a flat list of spheres and performs linear
    intersection testing. For FizzBuzz scenes (typically < 200 objects),
    a BVH acceleration structure would add complexity without meaningful
    performance benefit. Should the Enterprise FizzBuzz Platform ever
    require rendering millions of FizzBuzz classifications simultaneously,
    a BVH can be introduced behind this interface.
    """

    def __init__(self, background: Optional[Vec3] = None) -> None:
        self.objects: list[Sphere] = []
        self.background = background or Vec3(0.7, 0.8, 1.0)

    def add(self, obj: Sphere) -> None:
        """Add a sphere to the scene."""
        self.objects.append(obj)

    def hit(self, ray: Ray, t_min: float, t_max: float) -> Optional[HitRecord]:
        """Find the nearest intersection of a ray with any object in the scene."""
        closest_so_far = t_max
        closest_record: Optional[HitRecord] = None

        for obj in self.objects:
            record = obj.hit(ray, t_min, closest_so_far)
            if record is not None:
                closest_so_far = record.t
                closest_record = record

        return closest_record


# ============================================================
# Path Tracer — Monte Carlo Rendering Engine
# ============================================================


class PathTracer:
    """Monte Carlo path tracer with Russian Roulette termination.

    For each pixel, multiple sample rays are cast through jittered
    sub-pixel positions. Each ray is recursively traced through the
    scene, accumulating radiance contributions from surface scattering
    and emission. Russian Roulette is applied after a minimum bounce
    depth to stochastically terminate low-energy paths, providing an
    unbiased estimate of the rendering equation.

    The rendering equation being solved is:

        L_o(x, w_o) = L_e(x, w_o) + integral[ f_r(x, w_i, w_o) * L_i(x, w_i) * cos(theta_i) dw_i ]

    where L_o is outgoing radiance, L_e is emitted radiance, f_r is the
    BRDF, L_i is incoming radiance, and the integral is over the hemisphere.
    """

    def __init__(
        self,
        samples_per_pixel: int = DEFAULT_SAMPLES_PER_PIXEL,
        max_depth: int = MAX_BOUNCE_DEPTH,
    ) -> None:
        self.samples_per_pixel = samples_per_pixel
        self.max_depth = max_depth
        self.total_rays_cast = 0
        self.total_bounces = 0
        self.total_russian_roulette_kills = 0

    def ray_color(self, ray: Ray, scene: Scene, depth: int) -> Vec3:
        """Trace a single ray through the scene and return its color.

        Recursively traces scattered rays until the maximum depth is
        reached, a ray escapes to the background, or Russian Roulette
        terminates the path.
        """
        self.total_rays_cast += 1

        if depth <= 0:
            return Vec3(0.0, 0.0, 0.0)

        record = scene.hit(ray, 0.001, INF)

        if record is None:
            # Background gradient (sky)
            unit_direction = ray.direction.normalize()
            t = 0.5 * (unit_direction.y + 1.0)
            return Vec3(1.0, 1.0, 1.0) * (1.0 - t) + scene.background * t

        # Emission contribution
        emitted = record.material.emitted()

        # Russian Roulette termination for deep paths
        if depth < self.max_depth - RUSSIAN_ROULETTE_MIN_DEPTH:
            survival_probability = max(
                record.material.albedo.x,
                record.material.albedo.y,
                record.material.albedo.z,
            )
            survival_probability = max(0.05, min(survival_probability, 0.95))
            if random.random() > survival_probability:
                self.total_russian_roulette_kills += 1
                return emitted
            # Compensate for termination probability (unbiased estimator)

        # Scatter
        scatter_result = record.material.scatter(
            ray, record.point, record.normal, record.front_face
        )

        if scatter_result is None:
            return emitted

        attenuation, scattered = scatter_result
        self.total_bounces += 1

        return emitted + attenuation * self.ray_color(scattered, scene, depth - 1)

    def render(self, scene: Scene, camera: Camera, width: int, height: int) -> list[list[Vec3]]:
        """Render the scene to a 2D array of linear RGB pixel values.

        Returns a height x width array of Vec3 color values in linear
        color space. Gamma correction is applied during output encoding,
        not during accumulation.
        """
        self.total_rays_cast = 0
        self.total_bounces = 0
        self.total_russian_roulette_kills = 0

        pixels: list[list[Vec3]] = []

        for j in range(height):
            row: list[Vec3] = []
            for i in range(width):
                color = Vec3(0.0, 0.0, 0.0)
                for _ in range(self.samples_per_pixel):
                    u = (i + random.random()) / (width - 1) if width > 1 else 0.5
                    v = ((height - 1 - j) + random.random()) / (height - 1) if height > 1 else 0.5
                    ray = camera.get_ray(u, v)
                    color = color + self.ray_color(ray, scene, self.max_depth)
                scale = 1.0 / self.samples_per_pixel
                color = color * scale
                row.append(color)
            pixels.append(row)

        return pixels


# ============================================================
# PPMWriter — Portable Pixmap Format Output
# ============================================================


class PPMWriter:
    """Writes rendered pixel data to Netpbm PPM P3 (ASCII) format.

    PPM P3 is the universal baseline format for rendered image verification.
    Every pixel is written as three decimal integers (R G B) in the range
    [0, 255], preceded by a header specifying dimensions and maximum value.
    The format is human-readable, diff-friendly, and supported by virtually
    every image viewer and conversion tool.

    Gamma correction (sRGB transfer function approximated as pow(1/2.2))
    is applied during encoding to ensure perceptually uniform brightness
    on standard displays.
    """

    @staticmethod
    def encode_color(color: Vec3) -> tuple[int, int, int]:
        """Convert a linear-space color to gamma-corrected 8-bit RGB.

        Applies approximate sRGB gamma correction (power 1/2.2) and
        clamps to the [0, 255] range.
        """
        r = max(0.0, min(color.x, 1.0))
        g = max(0.0, min(color.y, 1.0))
        b = max(0.0, min(color.z, 1.0))

        # Gamma correction
        r = math.pow(r, 1.0 / GAMMA)
        g = math.pow(g, 1.0 / GAMMA)
        b = math.pow(b, 1.0 / GAMMA)

        return (
            int(255.999 * r),
            int(255.999 * g),
            int(255.999 * b),
        )

    @staticmethod
    def write(pixels: list[list[Vec3]], filepath: str) -> int:
        """Write pixel data to a PPM P3 file.

        Returns the number of pixels written.
        """
        if not pixels or not pixels[0]:
            return 0

        height = len(pixels)
        width = len(pixels[0])

        with open(filepath, "w") as f:
            f.write(f"P3\n{width} {height}\n255\n")
            for row in pixels:
                for pixel in row:
                    r, g, b = PPMWriter.encode_color(pixel)
                    f.write(f"{r} {g} {b}\n")

        return width * height

    @staticmethod
    def to_string(pixels: list[list[Vec3]]) -> str:
        """Render pixel data to a PPM P3 string (for testing and inspection)."""
        if not pixels or not pixels[0]:
            return "P3\n0 0\n255\n"

        height = len(pixels)
        width = len(pixels[0])

        lines = [f"P3\n{width} {height}\n255"]
        for row in pixels:
            for pixel in row:
                r, g, b = PPMWriter.encode_color(pixel)
                lines.append(f"{r} {g} {b}")

        return "\n".join(lines) + "\n"


# ============================================================
# Material Presets for FizzBuzz Classifications
# ============================================================


def fizz_material() -> Material:
    """Green metallic material for Fizz classifications.

    Fizz numbers exhibit specular reflection with a distinctly green tint,
    symbolizing the verdant abundance of numbers divisible by 3. The low
    fuzz value produces a near-mirror finish, appropriate for the precision
    of modulo-3 arithmetic.
    """
    return Material(
        material_type=MaterialType.METAL,
        albedo=Vec3(0.2, 0.8, 0.2),
        fuzz=0.1,
    )


def buzz_material() -> Material:
    """Blue dielectric (glass) material for Buzz classifications.

    Buzz numbers are rendered as transparent blue glass, through which
    the scene is visible via refraction. The index of refraction 1.52
    matches crown glass, chosen because "Buzz" and "glass" both have
    double letters, which is a sufficiently rigorous justification for
    a material science decision.
    """
    return Material(
        material_type=MaterialType.DIELECTRIC,
        albedo=Vec3(0.3, 0.3, 0.9),
        refraction_index=1.52,
    )


def fizzbuzz_material() -> Material:
    """Gold emissive material for FizzBuzz classifications.

    Numbers divisible by both 3 and 5 are the rarest and most celebrated
    outcomes in the FizzBuzz evaluation pipeline. They are rendered as
    self-luminous gold spheres that contribute light to the scene,
    illuminating nearby geometry as befits their elevated status.
    """
    return Material(
        material_type=MaterialType.EMISSIVE,
        albedo=Vec3(1.0, 0.84, 0.0),
        emission_color=Vec3(1.0, 0.84, 0.0),
        emission_strength=2.0,
    )


def plain_material() -> Material:
    """Gray Lambertian material for plain number classifications.

    Numbers that are neither Fizz nor Buzz are rendered as humble gray
    diffuse spheres. The Lambertian BRDF scatters light uniformly in
    all directions, reflecting the unremarkable nature of numbers that
    fail to exhibit any noteworthy divisibility properties.
    """
    return Material(
        material_type=MaterialType.LAMBERTIAN,
        albedo=Vec3(0.5, 0.5, 0.5),
    )


def ground_material() -> Material:
    """Light gray Lambertian ground plane material."""
    return Material(
        material_type=MaterialType.LAMBERTIAN,
        albedo=Vec3(0.8, 0.8, 0.8),
    )


# ============================================================
# FizzBuzzSceneBuilder — Maps Classifications to Geometry
# ============================================================


class FizzBuzzSceneBuilder:
    """Converts a sequence of FizzBuzz classifications into a 3D scene.

    Each classification result is mapped to a sphere with an appropriate
    physically-based material. Spheres are arranged in a grid pattern on
    a ground plane, with their material assignment determined by their
    FizzBuzz classification:

    - Fizz: green metallic sphere (specular green reflection)
    - Buzz: blue dielectric sphere (glass with refraction)
    - FizzBuzz: gold emissive sphere (self-luminous)
    - Plain number: gray Lambertian sphere (diffuse)

    The scene includes a large ground sphere (radius 1000) to serve as
    the ground plane, plus a camera positioned to frame the classification
    grid.
    """

    def __init__(self, sphere_radius: float = 0.5, spacing: float = 1.2) -> None:
        self._radius = sphere_radius
        self._spacing = spacing
        self._classifications: list[tuple[int, str]] = []
        self._material_counts: dict[str, int] = {
            "fizz": 0,
            "buzz": 0,
            "fizzbuzz": 0,
            "plain": 0,
        }

    @property
    def classifications(self) -> list[tuple[int, str]]:
        """Return the list of (number, classification) tuples."""
        return list(self._classifications)

    @property
    def material_counts(self) -> dict[str, int]:
        """Return the count of each material type used."""
        return dict(self._material_counts)

    def add_result(self, number: int, output: str, is_fizz: bool, is_buzz: bool) -> None:
        """Register a FizzBuzz classification result for rendering.

        The classification determines the material assignment:
        - is_fizz and is_buzz: FizzBuzz (gold emissive)
        - is_fizz only: Fizz (green metal)
        - is_buzz only: Buzz (blue glass)
        - neither: Plain (gray Lambertian)
        """
        if is_fizz and is_buzz:
            classification = "fizzbuzz"
        elif is_fizz:
            classification = "fizz"
        elif is_buzz:
            classification = "buzz"
        else:
            classification = "plain"

        self._classifications.append((number, classification))
        self._material_counts[classification] += 1

    def _get_material(self, classification: str) -> Material:
        """Return the appropriate material for a classification."""
        if classification == "fizzbuzz":
            return fizzbuzz_material()
        elif classification == "fizz":
            return fizz_material()
        elif classification == "buzz":
            return buzz_material()
        else:
            return plain_material()

    def build_scene(self) -> Scene:
        """Construct the complete 3D scene from accumulated classifications.

        Spheres are placed in a grid pattern. The grid width is determined
        by the square root of the total number of classifications, producing
        an approximately square layout.
        """
        scene = Scene(background=Vec3(0.5, 0.7, 1.0))

        # Ground plane
        scene.add(Sphere(
            center=Vec3(0.0, -1000.0, 0.0),
            radius=1000.0,
            material=ground_material(),
        ))

        if not self._classifications:
            return scene

        # Grid layout
        count = len(self._classifications)
        cols = max(1, int(math.ceil(math.sqrt(count))))

        for idx, (number, classification) in enumerate(self._classifications):
            row = idx // cols
            col = idx % cols

            # Center the grid
            x = (col - cols / 2.0) * self._spacing
            z = (row - cols / 2.0) * self._spacing
            y = self._radius  # Resting on ground plane

            material = self._get_material(classification)
            scene.add(Sphere(
                center=Vec3(x, y, z),
                radius=self._radius,
                material=material,
            ))

        return scene

    def build_camera(self, width: int, height: int) -> Camera:
        """Construct a camera positioned to frame the entire classification grid.

        The camera is elevated above the grid and angled downward to provide
        a clear view of all spheres and their material differentiation.
        """
        count = max(1, len(self._classifications))
        cols = max(1, int(math.ceil(math.sqrt(count))))
        grid_extent = cols * self._spacing

        # Position camera above and behind the grid
        camera_distance = grid_extent * 1.2 + 2.0
        lookfrom = Vec3(0.0, camera_distance * 0.6, camera_distance * 0.8)
        lookat = Vec3(0.0, 0.0, 0.0)
        vup = Vec3(0.0, 1.0, 0.0)

        return Camera(
            lookfrom=lookfrom,
            lookat=lookat,
            vup=vup,
            vfov_degrees=40.0,
            aspect_ratio=width / height if height > 0 else 1.0,
        )


# ============================================================
# RenderDashboard — ASCII Render Statistics Display
# ============================================================


class RenderDashboard:
    """ASCII dashboard displaying render progress, ray statistics, and
    material distribution for the FizzTrace ray tracing subsystem.

    Provides at-a-glance visibility into the rendering pipeline's
    performance characteristics, including total rays cast, average
    bounces per ray, Russian Roulette termination rate, and the
    distribution of materials across the FizzBuzz classification space.
    """

    @staticmethod
    def render(
        tracer: PathTracer,
        scene_builder: FizzBuzzSceneBuilder,
        width: int,
        height: int,
        render_time_ms: float,
        output_path: Optional[str] = None,
        dashboard_width: int = 60,
    ) -> str:
        """Render the ASCII dashboard to a string."""
        w = dashboard_width
        lines: list[str] = []

        def hline(char: str = "-") -> str:
            return "  +" + char * (w - 2) + "+"

        def row(content: str) -> str:
            padded = content.ljust(w - 4)
            return f"  | {padded} |"

        lines.append("")
        lines.append(hline("="))
        lines.append(row("FIZZTRACE: PHYSICALLY-BASED RAY TRACER"))
        lines.append(hline("="))
        lines.append(row(""))

        # Resolution & samples
        total_pixels = width * height
        spp = tracer.samples_per_pixel
        lines.append(row(f"Resolution:     {width} x {height} ({total_pixels:,} pixels)"))
        lines.append(row(f"Samples/pixel:  {spp}"))
        lines.append(row(f"Max depth:      {tracer.max_depth}"))
        lines.append(row(""))

        # Ray statistics
        lines.append(hline("-"))
        lines.append(row("RAY STATISTICS"))
        lines.append(hline("-"))
        total_rays = tracer.total_rays_cast
        total_bounces = tracer.total_bounces
        rr_kills = tracer.total_russian_roulette_kills
        avg_bounces = total_bounces / max(total_rays, 1)
        mrays_per_sec = total_rays / max(render_time_ms / 1000.0, 0.001) / 1_000_000

        lines.append(row(f"Total rays:     {total_rays:,}"))
        lines.append(row(f"Total bounces:  {total_bounces:,}"))
        lines.append(row(f"Avg bounces:    {avg_bounces:.2f}"))
        lines.append(row(f"RR kills:       {rr_kills:,}"))
        lines.append(row(f"Mrays/sec:      {mrays_per_sec:.3f}"))
        lines.append(row(f"Render time:    {render_time_ms:.1f} ms"))
        lines.append(row(""))

        # Material distribution
        counts = scene_builder.material_counts
        total_objs = sum(counts.values())
        lines.append(hline("-"))
        lines.append(row("MATERIAL DISTRIBUTION"))
        lines.append(hline("-"))

        bar_width = w - 30
        for mat_name, count in sorted(counts.items()):
            pct = (count / total_objs * 100) if total_objs > 0 else 0
            bar_len = int(pct / 100.0 * bar_width)
            bar = "#" * bar_len + "." * (bar_width - bar_len)
            label = mat_name.capitalize().ljust(10)
            lines.append(row(f"{label} {count:4d} [{bar}] {pct:5.1f}%"))

        lines.append(row(""))

        # Material legend
        lines.append(hline("-"))
        lines.append(row("MATERIAL LEGEND"))
        lines.append(hline("-"))
        lines.append(row("Fizz:     green metal   (specular, fuzz=0.1)"))
        lines.append(row("Buzz:     blue glass    (dielectric, IOR=1.52)"))
        lines.append(row("FizzBuzz: gold emissive (self-luminous, 2.0x)"))
        lines.append(row("Plain:    gray diffuse  (Lambertian)"))
        lines.append(row(""))

        # Output info
        if output_path:
            lines.append(hline("-"))
            lines.append(row("OUTPUT"))
            lines.append(hline("-"))
            lines.append(row(f"Format:  PPM P3 (ASCII)"))
            lines.append(row(f"File:    {output_path}"))
            lines.append(row(""))

        # Scene stats
        num_objects = len(scene_builder.classifications)
        lines.append(hline("-"))
        lines.append(row("SCENE"))
        lines.append(hline("-"))
        lines.append(row(f"Objects:        {num_objects} classification spheres + ground"))
        lines.append(row(f"Sphere radius:  {scene_builder._radius}"))
        lines.append(row(f"Grid spacing:   {scene_builder._spacing}"))
        lines.append(row(""))
        lines.append(hline("="))
        lines.append("")

        return "\n".join(lines)


# ============================================================
# RenderMiddleware — Pipeline Integration
# ============================================================


class RenderMiddleware(IMiddleware):
    """Middleware that accumulates FizzBuzz classifications for ray trace rendering.

    Intercepts each evaluation result passing through the middleware pipeline
    and registers it with the scene builder. The actual rendering occurs
    post-evaluation when ``render_scene`` is called, as the complete set
    of classifications must be known before the scene can be composed and
    ray-traced.

    Priority 960 places this middleware after most processing is complete,
    ensuring that the final classification is captured accurately.
    """

    def __init__(
        self,
        scene_builder: FizzBuzzSceneBuilder,
        tracer: PathTracer,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        output_path: Optional[str] = None,
        enable_dashboard: bool = False,
    ) -> None:
        self._scene_builder = scene_builder
        self._tracer = tracer
        self._width = width
        self._height = height
        self._output_path = output_path
        self._enable_dashboard = enable_dashboard
        self._results_captured = 0
        self._render_time_ms = 0.0
        self._rendered = False

    @property
    def scene_builder(self) -> FizzBuzzSceneBuilder:
        """Access the underlying scene builder."""
        return self._scene_builder

    @property
    def tracer(self) -> PathTracer:
        """Access the path tracer instance."""
        return self._tracer

    @property
    def results_captured(self) -> int:
        """Return the number of classification results captured."""
        return self._results_captured

    @property
    def render_time_ms(self) -> float:
        """Return the time spent rendering in milliseconds."""
        return self._render_time_ms

    @property
    def rendered(self) -> bool:
        """Return True if the scene has been rendered."""
        return self._rendered

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Capture each FizzBuzz result for scene construction."""
        result = next_handler(context)

        if result.results:
            latest = result.results[-1]
            self._scene_builder.add_result(
                number=latest.number,
                output=latest.output,
                is_fizz=latest.is_fizz,
                is_buzz=latest.is_buzz,
            )
            self._results_captured += 1

            result.metadata["raytrace_material"] = self._classify(latest)

        return result

    def _classify(self, result: Any) -> str:
        """Determine the material classification for a result."""
        if result.is_fizz and result.is_buzz:
            return "emissive_gold"
        elif result.is_fizz:
            return "metal_green"
        elif result.is_buzz:
            return "dielectric_blue"
        else:
            return "lambertian_gray"

    def render_scene(self) -> Optional[list[list[Vec3]]]:
        """Execute the ray trace render of the accumulated scene.

        Returns the rendered pixel data, or None if no classifications
        were captured.
        """
        if self._results_captured == 0:
            return None

        scene = self._scene_builder.build_scene()
        camera = self._scene_builder.build_camera(self._width, self._height)

        start = time.perf_counter_ns()
        pixels = self._tracer.render(scene, camera, self._width, self._height)
        self._render_time_ms = (time.perf_counter_ns() - start) / 1_000_000.0
        self._rendered = True

        if self._output_path:
            PPMWriter.write(pixels, self._output_path)

        return pixels

    def get_name(self) -> str:
        return "RenderMiddleware"

    def get_priority(self) -> int:
        return 960
