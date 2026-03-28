"""
Enterprise FizzBuzz Platform - FizzWindow Windowing System Errors (EFP-WIN00 .. EFP-WIN24)

Exception hierarchy for the FizzWindow compositing windowing system.  Covers
compositor operations, framebuffer management, damage tracking, window
management, focus handling, tiling layouts, event dispatch, widget trees,
layout engines, font rendering, glyph caching, theme management, clipboard
operations, drag-and-drop, multi-monitor support, screen capture, built-in
applications (FizzTerm, FizzView, FizzMonitor), and configuration management.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class FizzWindowError(FizzBuzzError):
    """Base exception for all FizzWindow windowing system errors.

    FizzWindow is the platform's compositing windowing system that provides
    hardware-accelerated window management, widget rendering, and desktop
    environment capabilities.  It handles the full graphics stack from
    framebuffer allocation through compositor blending and damage-tracked
    screen updates.  All windowing-specific failures inherit from this class
    to enable categorical error handling in the middleware pipeline.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzWindow error: {reason}",
            error_code="EFP-WIN00",
            context={"reason": reason},
        )


class FizzWindowCompositorError(FizzWindowError):
    """Raised on compositor failures.

    Covers failures in the compositing engine including render pass
    initialization, blend mode selection, alpha channel processing,
    V-sync synchronization, and composition pipeline stalls that
    prevent timely frame presentation.
    """

    def __init__(self, stage: str, reason: str) -> None:
        super().__init__(f"Compositor failure at stage '{stage}': {reason}")
        self.error_code = "EFP-WIN01"
        self.context = {"stage": stage, "reason": reason}


class FizzWindowBufferError(FizzWindowError):
    """Raised on framebuffer errors.

    Covers failures in framebuffer allocation, double-buffering swap
    operations, pixel format mismatches, stride alignment violations,
    and GPU memory exhaustion during buffer creation or resize.
    """

    def __init__(self, buffer_id: str, reason: str) -> None:
        super().__init__(f"Framebuffer error for buffer '{buffer_id}': {reason}")
        self.error_code = "EFP-WIN02"
        self.context = {"buffer_id": buffer_id, "reason": reason}


class FizzWindowDamageError(FizzWindowError):
    """Raised on damage tracking errors.

    Covers failures in the damage region tracking subsystem including
    invalid damage rectangle coordinates, region union overflow,
    and stale damage state that causes rendering artifacts from
    missed or duplicated screen updates.
    """

    def __init__(self, region: str, reason: str) -> None:
        super().__init__(f"Damage tracking error in region '{region}': {reason}")
        self.error_code = "EFP-WIN03"
        self.context = {"region": region, "reason": reason}


class FizzWindowManagerError(FizzWindowError):
    """Raised on window manager errors.

    Covers failures in the window manager core including window
    creation, destruction, stacking order maintenance, minimize
    and maximize state transitions, and inter-window relationship
    management such as transient and modal window hierarchies.
    """

    def __init__(self, window_id: str, reason: str) -> None:
        super().__init__(f"Window manager error for window '{window_id}': {reason}")
        self.error_code = "EFP-WIN04"
        self.context = {"window_id": window_id, "reason": reason}


class FizzWindowNotFoundError(FizzWindowError):
    """Raised when a window is not found.

    The window manager maintains an internal registry of all live
    windows indexed by their unique identifier.  This exception is
    raised when an operation references a window identifier that
    does not exist in the registry, either because it was never
    created or has already been destroyed.
    """

    def __init__(self, window_id: str) -> None:
        super().__init__(f"Window not found: '{window_id}'")
        self.error_code = "EFP-WIN05"
        self.context = {"window_id": window_id}


class FizzWindowFocusError(FizzWindowError):
    """Raised on focus management errors.

    Covers failures in keyboard and pointer focus management including
    focus-follows-mouse policy violations, focus theft prevention,
    focus chain corruption, and circular focus delegation between
    parent and child windows.
    """

    def __init__(self, window_id: str, reason: str) -> None:
        super().__init__(f"Focus error for window '{window_id}': {reason}")
        self.error_code = "EFP-WIN06"
        self.context = {"window_id": window_id, "reason": reason}


class FizzWindowTilingError(FizzWindowError):
    """Raised on tiling layout errors.

    Covers failures in the tiling window manager layout engine including
    binary space partitioning errors, split ratio violations, minimum
    size constraint conflicts, and layout tree corruption that prevents
    correct window placement within tiling containers.
    """

    def __init__(self, layout: str, reason: str) -> None:
        super().__init__(f"Tiling layout error for layout '{layout}': {reason}")
        self.error_code = "EFP-WIN07"
        self.context = {"layout": layout, "reason": reason}


class FizzWindowEventError(FizzWindowError):
    """Raised on event dispatch errors.

    Covers failures in the windowing event system including event
    queue overflow, undeliverable events, malformed event payloads,
    and event handler exceptions that propagate through the dispatch
    pipeline without being caught by application code.
    """

    def __init__(self, event_type: str, reason: str) -> None:
        super().__init__(f"Event dispatch error for event '{event_type}': {reason}")
        self.error_code = "EFP-WIN08"
        self.context = {"event_type": event_type, "reason": reason}


class FizzWindowWidgetError(FizzWindowError):
    """Raised on widget errors.

    Covers failures in the widget toolkit including widget tree
    construction errors, property binding failures, render method
    exceptions, and invalid widget state transitions that violate
    the widget lifecycle contract.
    """

    def __init__(self, widget_type: str, reason: str) -> None:
        super().__init__(f"Widget error for '{widget_type}': {reason}")
        self.error_code = "EFP-WIN09"
        self.context = {"widget_type": widget_type, "reason": reason}


class FizzWindowWidgetNotFoundError(FizzWindowError):
    """Raised when a widget is not found.

    The widget tree maintains a registry of all instantiated widgets
    indexed by their unique identifier.  This exception is raised when
    a lookup, update, or removal operation references a widget
    identifier that does not exist in the current widget tree.
    """

    def __init__(self, widget_id: str) -> None:
        super().__init__(f"Widget not found: '{widget_id}'")
        self.error_code = "EFP-WIN10"
        self.context = {"widget_id": widget_id}


class FizzWindowLayoutError(FizzWindowError):
    """Raised on layout engine errors.

    Covers failures in the constraint-based layout engine including
    unsatisfiable constraint systems, circular dependency detection
    in layout expressions, overflow handling errors, and intrinsic
    size measurement failures during the layout pass.
    """

    def __init__(self, container: str, reason: str) -> None:
        super().__init__(f"Layout error in container '{container}': {reason}")
        self.error_code = "EFP-WIN11"
        self.context = {"container": container, "reason": reason}


class FizzWindowFontError(FizzWindowError):
    """Raised on font rendering errors.

    Covers failures in the font subsystem including font file parsing
    errors, missing required font tables, unsupported font formats,
    rasterization failures, and font fallback chain exhaustion when
    no installed font provides coverage for the requested codepoints.
    """

    def __init__(self, font_name: str, reason: str) -> None:
        super().__init__(f"Font error for '{font_name}': {reason}")
        self.error_code = "EFP-WIN12"
        self.context = {"font_name": font_name, "reason": reason}


class FizzWindowGlyphError(FizzWindowError):
    """Raised on glyph cache errors.

    Covers failures in the glyph cache subsystem including cache
    eviction under memory pressure, texture atlas fragmentation,
    glyph rasterization failures for specific codepoints, and
    cache coherence violations between the CPU and GPU glyph stores.
    """

    def __init__(self, codepoint: int, reason: str) -> None:
        super().__init__(f"Glyph cache error for codepoint U+{codepoint:04X}: {reason}")
        self.error_code = "EFP-WIN13"
        self.context = {"codepoint": codepoint, "reason": reason}


class FizzWindowThemeError(FizzWindowError):
    """Raised on theme errors.

    Covers failures in the theming engine including malformed theme
    definition files, invalid color specifications, missing required
    theme assets, and theme inheritance chain resolution errors that
    prevent the compositor from applying visual styling.
    """

    def __init__(self, theme: str, reason: str) -> None:
        super().__init__(f"Theme error for '{theme}': {reason}")
        self.error_code = "EFP-WIN14"
        self.context = {"theme": theme, "reason": reason}


class FizzWindowThemeNotFoundError(FizzWindowError):
    """Raised when a theme is not found.

    The theme registry maintains an index of all available themes
    loaded from the theme search path.  This exception is raised
    when an activation request references a theme name that does
    not exist in the registry or on the filesystem.
    """

    def __init__(self, theme: str) -> None:
        super().__init__(f"Theme not found: '{theme}'")
        self.error_code = "EFP-WIN15"
        self.context = {"theme": theme}


class FizzWindowClipboardError(FizzWindowError):
    """Raised on clipboard errors.

    Covers failures in the clipboard subsystem including selection
    ownership conflicts, MIME type negotiation failures, data
    conversion errors between clipboard formats, and clipboard
    content size limit violations.
    """

    def __init__(self, mime_type: str, reason: str) -> None:
        super().__init__(f"Clipboard error for MIME type '{mime_type}': {reason}")
        self.error_code = "EFP-WIN16"
        self.context = {"mime_type": mime_type, "reason": reason}


class FizzWindowDragDropError(FizzWindowError):
    """Raised on drag-and-drop errors.

    Covers failures in the drag-and-drop protocol including drag
    source initialization errors, drop target rejection, data
    transfer failures between source and target windows, and
    drag cancel operations due to invalid drop coordinates.
    """

    def __init__(self, source_id: str, target_id: str, reason: str) -> None:
        super().__init__(f"Drag-and-drop error from '{source_id}' to '{target_id}': {reason}")
        self.error_code = "EFP-WIN17"
        self.context = {"source_id": source_id, "target_id": target_id, "reason": reason}


class FizzWindowMonitorError(FizzWindowError):
    """Raised on multi-monitor errors.

    Covers failures in multi-monitor management including display
    enumeration errors, resolution and refresh rate negotiation
    failures, monitor hotplug handling errors, and DPI scaling
    inconsistencies across heterogeneous display configurations.
    """

    def __init__(self, monitor_id: str, reason: str) -> None:
        super().__init__(f"Monitor error for '{monitor_id}': {reason}")
        self.error_code = "EFP-WIN18"
        self.context = {"monitor_id": monitor_id, "reason": reason}


class FizzWindowCaptureError(FizzWindowError):
    """Raised on screen capture errors.

    Covers failures in the screen capture subsystem including
    framebuffer readback errors, pixel format conversion failures,
    capture region validation errors, and permission denials when
    secure windows opt out of capture.
    """

    def __init__(self, region: str, reason: str) -> None:
        super().__init__(f"Screen capture error for region '{region}': {reason}")
        self.error_code = "EFP-WIN19"
        self.context = {"region": region, "reason": reason}


class FizzWindowAppError(FizzWindowError):
    """Raised on built-in application errors.

    Covers general failures in FizzWindow's built-in desktop
    applications.  Each built-in application also has a dedicated
    exception subclass for more granular error handling.  This
    base application error covers cross-cutting concerns such as
    application lifecycle management and IPC failures.
    """

    def __init__(self, app_name: str, reason: str) -> None:
        super().__init__(f"Application error in '{app_name}': {reason}")
        self.error_code = "EFP-WIN20"
        self.context = {"app_name": app_name, "reason": reason}


class FizzWindowTermError(FizzWindowError):
    """Raised on FizzTerm errors.

    Covers failures in the FizzTerm terminal emulator including
    VT100/VT220 escape sequence parsing errors, PTY allocation
    failures, shell process spawning errors, and terminal buffer
    overflow conditions during high-throughput output.
    """

    def __init__(self, session_id: str, reason: str) -> None:
        super().__init__(f"FizzTerm error for session '{session_id}': {reason}")
        self.error_code = "EFP-WIN21"
        self.context = {"session_id": session_id, "reason": reason}


class FizzWindowViewerError(FizzWindowError):
    """Raised on FizzView errors.

    Covers failures in the FizzView document and image viewer
    including unsupported file format detection, rendering pipeline
    failures, zoom and pan calculation errors, and document pagination
    issues during multi-page rendering.
    """

    def __init__(self, file_path: str, reason: str) -> None:
        super().__init__(f"FizzView error for '{file_path}': {reason}")
        self.error_code = "EFP-WIN22"
        self.context = {"file_path": file_path, "reason": reason}


class FizzWindowMonitorAppError(FizzWindowError):
    """Raised on FizzMonitor errors.

    Covers failures in the FizzMonitor system monitoring application
    including process enumeration errors, CPU and memory metric
    collection failures, graph rendering errors, and refresh interval
    timer failures that prevent real-time system status display.
    """

    def __init__(self, subsystem: str, reason: str) -> None:
        super().__init__(f"FizzMonitor error in subsystem '{subsystem}': {reason}")
        self.error_code = "EFP-WIN23"
        self.context = {"subsystem": subsystem, "reason": reason}


class FizzWindowConfigError(FizzWindowError):
    """Raised on configuration errors.

    Covers invalid windowing system configuration parameters including
    unsupported display backends, invalid compositor pipeline settings,
    conflicting keybinding definitions, and theme directory path
    resolution failures during startup initialization.
    """

    def __init__(self, parameter: str, reason: str) -> None:
        super().__init__(f"Window configuration error for '{parameter}': {reason}")
        self.error_code = "EFP-WIN24"
        self.context = {"parameter": parameter, "reason": reason}
