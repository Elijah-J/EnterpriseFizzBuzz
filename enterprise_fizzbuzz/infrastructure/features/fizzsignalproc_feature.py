"""Feature descriptor for the FizzSignalProc digital signal processing engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzSignalProcFeature(FeatureDescriptor):
    name = "fizzsignalproc"
    description = "Digital signal processing with FFT, FIR/IIR filters, windowing, spectrograms, and Hilbert transform"
    middleware_priority = 290
    cli_flags = [
        ("--fizzsignalproc", {"action": "store_true", "default": False,
                               "help": "Enable FizzSignalProc: spectral analysis of FizzBuzz evaluation sequences"}),
        ("--fizzsignalproc-buffer-size", {"type": int, "metavar": "N", "default": None,
                                           "help": "DSP analysis buffer size in samples (default: 256)"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "fizzsignalproc", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzsignalproc import (
            DSPEngine,
            SignalProcMiddleware,
        )

        buffer_size = getattr(args, "fizzsignalproc_buffer_size", None) or config.fizzsignalproc_buffer_size
        middleware = SignalProcMiddleware(buffer_size=buffer_size)
        return middleware.engine, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZSIGNALPROC: DIGITAL SIGNAL PROCESSING ENGINE         |\n"
            "  |   Cooley-Tukey FFT with bit-reversal permutation         |\n"
            "  |   Windowed sinc FIR filter design                        |\n"
            "  |   Hilbert transform for envelope detection               |\n"
            "  +---------------------------------------------------------+"
        )
