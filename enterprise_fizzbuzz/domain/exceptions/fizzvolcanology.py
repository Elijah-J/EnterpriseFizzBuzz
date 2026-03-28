"""
Enterprise FizzBuzz Platform - FizzVolcanology Exceptions (EFP-VOL00 through EFP-VOL09)
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzVolcanologyError(FizzBuzzError):
    """Base exception for all FizzVolcanology eruption simulation errors.

    The FizzVolcanology engine models volcanic processes from magma chamber
    pressurization through eruption column dynamics. Accurate simulation
    of lava viscosity, volatile content, and conduit geometry is essential
    for determining the Volcanic Explosivity Index of each FizzBuzz
    evaluation event.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-VOL00",
        context: dict | None = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class MagmaChamberError(FizzVolcanologyError):
    """Raised when magma chamber parameters are non-physical.

    Magma chamber pressure must exceed lithostatic pressure to drive
    eruption, but cannot exceed the tensile strength of the surrounding
    rock by more than a factor that would cause caldera collapse rather
    than conduit-fed eruption.
    """

    def __init__(self, pressure_mpa: float, reason: str) -> None:
        super().__init__(
            f"Magma chamber pressure {pressure_mpa:.1f} MPa is invalid: {reason}",
            error_code="EFP-VOL01",
            context={"pressure_mpa": pressure_mpa, "reason": reason},
        )


class LavaViscosityError(FizzVolcanologyError):
    """Raised when lava viscosity falls outside the known range.

    Silicate melt viscosity spans approximately 10^1 to 10^14 Pa*s
    depending on temperature, composition, and crystal content. Values
    outside this range indicate an error in the Arrhenius viscosity
    model or invalid magma composition parameters.
    """

    def __init__(self, viscosity_pa_s: float, composition: str) -> None:
        super().__init__(
            f"Lava viscosity {viscosity_pa_s:.2e} Pa*s for {composition} composition "
            f"is outside the physically realizable range",
            error_code="EFP-VOL02",
            context={"viscosity_pa_s": viscosity_pa_s, "composition": composition},
        )


class EruptionTypeError(FizzVolcanologyError):
    """Raised when eruption type classification fails.

    Eruption type depends on the interplay between magma viscosity,
    volatile content, and discharge rate. Conflicting parameters
    (e.g., high viscosity with zero volatile content) prevent
    classification into standard eruption categories.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Eruption type classification failed: {reason}",
            error_code="EFP-VOL03",
            context={"reason": reason},
        )


class PyroclasticFlowError(FizzVolcanologyError):
    """Raised when pyroclastic flow simulation yields non-physical results.

    Pyroclastic density currents must have positive velocity, temperature
    above ambient, and density between that of air and solid rock.
    A negative flow velocity would imply material flowing uphill against
    gravity, which is not observed in nature.
    """

    def __init__(self, velocity_ms: float, temperature_k: float) -> None:
        super().__init__(
            f"Non-physical pyroclastic flow: velocity={velocity_ms:.1f} m/s, "
            f"temperature={temperature_k:.0f} K",
            error_code="EFP-VOL04",
            context={"velocity_ms": velocity_ms, "temperature_k": temperature_k},
        )


class VEIClassificationError(FizzVolcanologyError):
    """Raised when the Volcanic Explosivity Index cannot be computed.

    The VEI scale ranges from 0 (non-explosive) to 8 (mega-colossal).
    Classification requires valid ejecta volume, column height, and
    eruption duration. Missing or contradictory inputs prevent
    assignment to a VEI category.
    """

    def __init__(self, ejecta_volume_km3: float, reason: str) -> None:
        super().__init__(
            f"VEI classification failed for ejecta volume {ejecta_volume_km3:.4f} km^3: {reason}",
            error_code="EFP-VOL05",
            context={"ejecta_volume_km3": ejecta_volume_km3, "reason": reason},
        )


class VolcanologyMiddlewareError(FizzVolcanologyError):
    """Raised when the FizzVolcanology middleware pipeline encounters a fault."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzVolcanology middleware error: {reason}",
            error_code="EFP-VOL06",
            context={"reason": reason},
        )
