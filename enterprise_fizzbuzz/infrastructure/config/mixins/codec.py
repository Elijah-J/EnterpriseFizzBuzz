"""FizzCodec H.264-Inspired Video Codec properties"""

from __future__ import annotations

from typing import Any


class CodecConfigMixin:
    """Configuration properties for the codec subsystem."""

    # ------------------------------------------------------------------
    # FizzCodec H.264-Inspired Video Codec properties
    # ------------------------------------------------------------------

    @property
    def codec_enabled(self) -> bool:
        """Whether the FizzCodec video encoder is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("codec", {}).get("enabled", False)

    @property
    def codec_qp(self) -> int:
        """Quantization parameter for the video codec (0-51)."""
        self._ensure_loaded()
        return int(self._raw_config.get("codec", {}).get("qp", 26))

    @property
    def codec_gop_size(self) -> int:
        """Group of Pictures size (number of frames between I-frames)."""
        self._ensure_loaded()
        return int(self._raw_config.get("codec", {}).get("gop_size", 4))

    @property
    def codec_frame_width(self) -> int:
        """Frame width in pixels for the video codec."""
        self._ensure_loaded()
        return int(self._raw_config.get("codec", {}).get("frame_width", 128))

    @property
    def codec_frame_height(self) -> int:
        """Frame height in pixels for the video codec."""
        self._ensure_loaded()
        return int(self._raw_config.get("codec", {}).get("frame_height", 64))

    @property
    def codec_dashboard_width(self) -> int:
        """Width of the FizzCodec ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("codec", {}).get("dashboard", {}).get("width", 60)

