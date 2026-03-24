"""Feature descriptor for FizzCodec H.264-inspired video codec."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class VideoCodecFeature(FeatureDescriptor):
    name = "video_codec"
    description = "H.264-inspired video codec with DCT, Exp-Golomb entropy coding, and NAL unit packaging"
    middleware_priority = 122
    cli_flags = [
        ("--codec", {"action": "store_true", "default": False,
                     "help": "Enable FizzCodec: encode FizzBuzz dashboard frames using H.264-style video compression"}),
        ("--codec-output", {"type": str, "default": None, "metavar": "FILE",
                            "help": "Write the compressed video bitstream to FILE (NAL unit Annex B format)"}),
        ("--codec-qp", {"type": int, "default": None, "metavar": "N",
                        "help": "Quantization parameter (0=near-lossless, 51=maximum compression, default: 26)"}),
        ("--codec-dashboard", {"action": "store_true", "default": False,
                               "help": "Display the FizzCodec video compression dashboard after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "codec", False),
            bool(getattr(args, "codec_output", None)),
            getattr(args, "codec_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.video_codec import (
            CodecMiddleware,
        )

        codec_qp = getattr(args, "codec_qp", None)
        if codec_qp is None:
            codec_qp = config.codec_qp

        middleware = CodecMiddleware(
            qp=codec_qp,
            output_path=getattr(args, "codec_output", None),
            enable_dashboard=getattr(args, "codec_dashboard", False),
            gop_size=config.codec_gop_size,
            frame_width=config.codec_frame_width,
            frame_height=config.codec_frame_height,
        )

        return middleware, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None

        parts = []
        codec_stats = middleware.finalize()

        if getattr(args, "codec_dashboard", False) and codec_stats is not None:
            parts.append(middleware.render_dashboard())
        elif getattr(args, "codec_dashboard", False):
            parts.append("\n  FizzCodec: No frames encoded.\n")

        if getattr(args, "codec_output", None) and codec_stats is not None:
            parts.append(
                f"\n  FizzCodec bitstream written to: {args.codec_output}"
                f"\n  Frames: {codec_stats.total_frames}, "
                f"Compression: {codec_stats.compression_ratio:.2f}x, "
                f"PSNR: {codec_stats.average_psnr:.2f} dB"
            )

        return "\n".join(parts) if parts else None
