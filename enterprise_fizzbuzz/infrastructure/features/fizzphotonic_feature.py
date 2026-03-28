"""Feature descriptor for the FizzPhotonic computing simulator."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzPhotonicFeature(FeatureDescriptor):
    name = "fizzphotonic"
    description = "Photonic computing simulator with MZI meshes, ring resonators, and optical matrix multiply"
    middleware_priority = 258
    cli_flags = [
        ("--fizzphotonic", {"action": "store_true", "default": False,
                            "help": "Enable FizzPhotonic: optical FizzBuzz evaluation via photonic circuits"}),
        ("--fizzphotonic-mesh-size", {"type": int, "default": 4, "metavar": "N",
                                      "help": "MZI mesh port count (default: 4)"}),
        ("--fizzphotonic-wavelength", {"type": float, "default": 1550.0, "metavar": "NM",
                                       "help": "Operating wavelength in nm (default: 1550)"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "fizzphotonic", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzphotonic import (
            PhotonicFizzBuzzEngine,
            FizzPhotonicMiddleware,
        )

        engine = PhotonicFizzBuzzEngine(
            mesh_size=getattr(args, "fizzphotonic_mesh_size", config.fizzphotonic_mesh_size),
        )
        middleware = FizzPhotonicMiddleware(engine=engine)
        return engine, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZPHOTONIC: PHOTONIC COMPUTING SIMULATOR               |\n"
            "  |   Wavelength: 1550 nm (C-band)  Si waveguides            |\n"
            "  |   MZI mesh: Reck decomposition  Ring resonators           |\n"
            "  |   Photodetection: PIN diodes with NEP tracking            |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        return None
