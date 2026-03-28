"""
Enterprise FizzBuzz Platform - FizzWindow: Windowing System & Display Server

Production-grade windowing system and display server for the Enterprise
FizzBuzz Platform.  Implements a compositor with damage tracking and
double-buffered rendering, a window manager supporting both floating and
tiling modes, an event dispatch system (keyboard, mouse, focus, resize),
a widget toolkit with 15 widget types, a layout engine (HBox, VBox, Grid,
Absolute), a bitmap font renderer with glyph cache, a theme engine
(Enterprise Dark and Enterprise Light), a clipboard manager, drag-and-drop
protocol, multi-monitor support, screen capture, and three built-in
applications (FizzTerm terminal emulator, FizzView image viewer, FizzMonitor
system monitor dashboard).

FizzWindow fills the graphical output gap -- the platform has a ray tracer,
a video codec, a PDF generator, a GPU shader compiler, a typesetting engine,
a flame graph generator, and a spreadsheet engine, all producing visual
content with no display server to composite it.

Architecture reference: X11, Wayland, Win32 GDI, Quartz Compositor.
"""

from __future__ import annotations

import copy
import hashlib
import logging
import math
import random
import struct
import time
import uuid
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from enterprise_fizzbuzz.domain.exceptions.fizzwindow import (
    FizzWindowError,
    FizzWindowCompositorError,
    FizzWindowBufferError,
    FizzWindowDamageError,
    FizzWindowManagerError,
    FizzWindowNotFoundError,
    FizzWindowFocusError,
    FizzWindowTilingError,
    FizzWindowEventError,
    FizzWindowWidgetError,
    FizzWindowWidgetNotFoundError,
    FizzWindowLayoutError,
    FizzWindowFontError,
    FizzWindowGlyphError,
    FizzWindowThemeError,
    FizzWindowThemeNotFoundError,
    FizzWindowClipboardError,
    FizzWindowDragDropError,
    FizzWindowMonitorError,
    FizzWindowCaptureError,
    FizzWindowAppError,
    FizzWindowTermError,
    FizzWindowViewerError,
    FizzWindowMonitorAppError,
    FizzWindowConfigError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzResult,
    ProcessingContext,
)

logger = logging.getLogger("enterprise_fizzbuzz.fizzwindow")

# ============================================================
# Event Type Registration
# ============================================================

EVENT_WINDOW_CREATED = EventType.register("FIZZWINDOW_CREATED")
EVENT_WINDOW_DESTROYED = EventType.register("FIZZWINDOW_DESTROYED")
EVENT_WINDOW_FOCUSED = EventType.register("FIZZWINDOW_FOCUSED")
EVENT_FRAME_RENDERED = EventType.register("FIZZWINDOW_FRAME_RENDERED")

# ============================================================
# Constants
# ============================================================

FIZZWINDOW_VERSION = "1.0.0"
FIZZWINDOW_SERVER_NAME = f"FizzWindow/{FIZZWINDOW_VERSION} (Enterprise FizzBuzz Platform)"

DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 1080
DEFAULT_FPS = 60
DEFAULT_DPI = 96
DEFAULT_FONT = "FizzMono"
DEFAULT_THEME = "enterprise-dark"
DEFAULT_DASHBOARD_WIDTH = 72

MIDDLEWARE_PRIORITY = 126


# ============================================================
# Enums
# ============================================================

class WindowMode(Enum):
    FLOATING = "floating"
    TILING = "tiling"

class WindowState(Enum):
    NORMAL = auto()
    MAXIMIZED = auto()
    MINIMIZED = auto()
    FULLSCREEN = auto()

class EventKind(Enum):
    KEY_DOWN = auto()
    KEY_UP = auto()
    MOUSE_MOVE = auto()
    MOUSE_DOWN = auto()
    MOUSE_UP = auto()
    MOUSE_SCROLL = auto()
    FOCUS_IN = auto()
    FOCUS_OUT = auto()
    RESIZE = auto()
    CLOSE = auto()
    EXPOSE = auto()
    ENTER = auto()
    LEAVE = auto()
    DRAG_START = auto()
    DRAG_MOVE = auto()
    DROP = auto()

class WidgetType(Enum):
    BUTTON = auto()
    LABEL = auto()
    TEXT_INPUT = auto()
    CHECKBOX = auto()
    DROPDOWN = auto()
    LIST_VIEW = auto()
    SCROLL_AREA = auto()
    TAB_BAR = auto()
    MENU_BAR = auto()
    STATUS_BAR = auto()
    CANVAS = auto()
    PROGRESS_BAR = auto()
    SLIDER = auto()
    SEPARATOR = auto()
    PANEL = auto()

class LayoutType(Enum):
    HBOX = auto()
    VBOX = auto()
    GRID = auto()
    ABSOLUTE = auto()


# ============================================================
# Dataclasses
# ============================================================

@dataclass
class FizzWindowConfig:
    width: int = DEFAULT_WIDTH
    height: int = DEFAULT_HEIGHT
    mode: str = "floating"
    theme: str = DEFAULT_THEME
    monitors: int = 1
    fps_limit: int = DEFAULT_FPS
    dpi: int = DEFAULT_DPI
    font: str = DEFAULT_FONT
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH

@dataclass
class Color:
    r: int = 0
    g: int = 0
    b: int = 0
    a: int = 255

    def to_hex(self) -> str:
        return f"#{self.r:02x}{self.g:02x}{self.b:02x}"

@dataclass
class Rect:
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0

    def contains(self, px: int, py: int) -> bool:
        return self.x <= px < self.x + self.width and self.y <= py < self.y + self.height

    def intersects(self, other: "Rect") -> bool:
        return not (self.x + self.width <= other.x or other.x + other.width <= self.x or
                    self.y + self.height <= other.y or other.y + other.height <= self.y)

@dataclass
class Pixel:
    r: int = 0
    g: int = 0
    b: int = 0

@dataclass
class DamageRegion:
    rects: List[Rect] = field(default_factory=list)

    def add(self, rect: Rect) -> None:
        self.rects.append(rect)

    def clear(self) -> None:
        self.rects.clear()

    @property
    def is_empty(self) -> bool:
        return len(self.rects) == 0

@dataclass
class InputEvent:
    kind: EventKind = EventKind.KEY_DOWN
    key: str = ""
    x: int = 0
    y: int = 0
    button: int = 0
    modifiers: Set[str] = field(default_factory=set)
    timestamp: float = 0.0

@dataclass
class WindowInfo:
    window_id: int = 0
    title: str = ""
    rect: Rect = field(default_factory=Rect)
    state: WindowState = WindowState.NORMAL
    visible: bool = True
    focused: bool = False
    z_order: int = 0
    decorations: bool = True
    resizable: bool = True
    min_width: int = 100
    min_height: int = 50

@dataclass
class MonitorInfo:
    monitor_id: int = 0
    name: str = ""
    rect: Rect = field(default_factory=Rect)
    dpi: int = 96
    primary: bool = False
    refresh_rate: int = 60

@dataclass
class Theme:
    name: str = ""
    bg_color: Color = field(default_factory=lambda: Color(30, 30, 30))
    fg_color: Color = field(default_factory=lambda: Color(220, 220, 220))
    accent_color: Color = field(default_factory=lambda: Color(66, 133, 244))
    border_color: Color = field(default_factory=lambda: Color(80, 80, 80))
    titlebar_color: Color = field(default_factory=lambda: Color(45, 45, 45))
    titlebar_text: Color = field(default_factory=lambda: Color(200, 200, 200))
    button_color: Color = field(default_factory=lambda: Color(55, 55, 55))
    button_hover: Color = field(default_factory=lambda: Color(75, 75, 75))
    button_active: Color = field(default_factory=lambda: Color(90, 90, 90))
    input_bg: Color = field(default_factory=lambda: Color(40, 40, 40))
    selection_color: Color = field(default_factory=lambda: Color(66, 133, 244, 128))
    font_size: int = 14
    border_width: int = 1
    titlebar_height: int = 30
    padding: int = 8

@dataclass
class GlyphData:
    character: str = ""
    width: int = 8
    height: int = 16
    bitmap: List[int] = field(default_factory=list)

@dataclass
class DisplayMetrics:
    total_frames: int = 0
    total_damage_rects: int = 0
    windows_created: int = 0
    windows_destroyed: int = 0
    events_dispatched: int = 0
    widgets_rendered: int = 0
    captures_taken: int = 0
    clipboard_operations: int = 0


# ============================================================
# Framebuffer
# ============================================================

class Framebuffer:
    """Double-buffered pixel framebuffer for display rendering."""

    def __init__(self, width: int, height: int) -> None:
        self._width = width
        self._height = height
        self._front = [[Pixel(30, 30, 30) for _ in range(width)] for _ in range(height)]
        self._back = [[Pixel(30, 30, 30) for _ in range(width)] for _ in range(height)]

    def set_pixel(self, x: int, y: int, r: int, g: int, b: int) -> None:
        if 0 <= x < self._width and 0 <= y < self._height:
            self._back[y][x] = Pixel(r, g, b)

    def fill_rect(self, rect: Rect, color: Color) -> None:
        for y in range(max(0, rect.y), min(self._height, rect.y + rect.height)):
            for x in range(max(0, rect.x), min(self._width, rect.x + rect.width)):
                self._back[y][x] = Pixel(color.r, color.g, color.b)

    def draw_text(self, x: int, y: int, text: str, color: Color) -> None:
        # Simulated text rendering - each char is 8px wide
        for i, ch in enumerate(text):
            px = x + i * 8
            if 0 <= px < self._width and 0 <= y < self._height:
                self._back[y][px] = Pixel(color.r, color.g, color.b)

    def draw_border(self, rect: Rect, color: Color, width: int = 1) -> None:
        for w in range(width):
            for x in range(rect.x, rect.x + rect.width):
                if 0 <= x < self._width:
                    if 0 <= rect.y + w < self._height:
                        self._back[rect.y + w][x] = Pixel(color.r, color.g, color.b)
                    by = rect.y + rect.height - 1 - w
                    if 0 <= by < self._height:
                        self._back[by][x] = Pixel(color.r, color.g, color.b)
            for y in range(rect.y, rect.y + rect.height):
                if 0 <= y < self._height:
                    if 0 <= rect.x + w < self._width:
                        self._back[y][rect.x + w] = Pixel(color.r, color.g, color.b)
                    bx = rect.x + rect.width - 1 - w
                    if 0 <= bx < self._width:
                        self._back[y][bx] = Pixel(color.r, color.g, color.b)

    def swap(self) -> None:
        self._front, self._back = self._back, self._front

    def clear(self, color: Color = None) -> None:
        c = color or Color(30, 30, 30)
        for y in range(self._height):
            for x in range(self._width):
                self._back[y][x] = Pixel(c.r, c.g, c.b)

    def get_pixel(self, x: int, y: int) -> Pixel:
        if 0 <= x < self._width and 0 <= y < self._height:
            return self._front[y][x]
        return Pixel()

    def to_ppm(self) -> bytes:
        """Export framebuffer as PPM image (P6 binary)."""
        header = f"P6\n{self._width} {self._height}\n255\n".encode()
        pixels = bytearray()
        for row in self._front:
            for p in row:
                pixels.extend([p.r, p.g, p.b])
        return header + bytes(pixels)

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height


# ============================================================
# Compositor
# ============================================================

class Compositor:
    """Damage-tracking compositor with double-buffered rendering."""

    def __init__(self, framebuffer: Framebuffer, config: FizzWindowConfig) -> None:
        self._fb = framebuffer
        self._config = config
        self._damage = DamageRegion()
        self._frame_count = 0

    def damage(self, rect: Rect) -> None:
        self._damage.add(rect)

    def damage_all(self) -> None:
        self._damage.add(Rect(0, 0, self._fb.width, self._fb.height))

    def composite(self, windows: List[WindowInfo], theme: Theme) -> None:
        if self._damage.is_empty:
            return
        # Clear damaged regions with background
        for rect in self._damage.rects:
            self._fb.fill_rect(rect, theme.bg_color)
        self._damage.clear()
        self._fb.swap()
        self._frame_count += 1

    @property
    def frame_count(self) -> int:
        return self._frame_count

    @property
    def damage_region(self) -> DamageRegion:
        return self._damage


# ============================================================
# Window Manager
# ============================================================

class WindowManager:
    """Window manager supporting floating and tiling modes."""

    def __init__(self, config: FizzWindowConfig) -> None:
        self._config = config
        self._windows: OrderedDict[int, WindowInfo] = OrderedDict()
        self._next_id = 1
        self._focused_id: Optional[int] = None
        self._mode = WindowMode(config.mode)
        self._z_counter = 0

    def create_window(self, title: str, x: int = 50, y: int = 50,
                      width: int = 640, height: int = 480) -> WindowInfo:
        wid = self._next_id
        self._next_id += 1
        self._z_counter += 1

        win = WindowInfo(
            window_id=wid, title=title,
            rect=Rect(x, y, width, height),
            z_order=self._z_counter,
        )
        self._windows[wid] = win

        if self._mode == WindowMode.TILING:
            self._retile()

        self.focus_window(wid)
        logger.debug("Window created: id=%d title='%s'", wid, title)
        return win

    def destroy_window(self, window_id: int) -> None:
        if window_id not in self._windows:
            raise FizzWindowNotFoundError(str(window_id))
        del self._windows[window_id]
        if self._focused_id == window_id:
            self._focused_id = next(iter(self._windows), None) if self._windows else None
        if self._mode == WindowMode.TILING:
            self._retile()

    def focus_window(self, window_id: int) -> None:
        if window_id not in self._windows:
            raise FizzWindowNotFoundError(str(window_id))
        if self._focused_id is not None and self._focused_id in self._windows:
            self._windows[self._focused_id].focused = False
        self._focused_id = window_id
        self._windows[window_id].focused = True
        self._z_counter += 1
        self._windows[window_id].z_order = self._z_counter

    def move_window(self, window_id: int, x: int, y: int) -> None:
        if window_id not in self._windows:
            raise FizzWindowNotFoundError(str(window_id))
        win = self._windows[window_id]
        win.rect.x = x
        win.rect.y = y

    def resize_window(self, window_id: int, width: int, height: int) -> None:
        if window_id not in self._windows:
            raise FizzWindowNotFoundError(str(window_id))
        win = self._windows[window_id]
        win.rect.width = max(width, win.min_width)
        win.rect.height = max(height, win.min_height)

    def maximize_window(self, window_id: int) -> None:
        win = self._windows.get(window_id)
        if win:
            win.state = WindowState.MAXIMIZED
            win.rect = Rect(0, 0, self._config.width, self._config.height)

    def minimize_window(self, window_id: int) -> None:
        win = self._windows.get(window_id)
        if win:
            win.state = WindowState.MINIMIZED
            win.visible = False

    def restore_window(self, window_id: int) -> None:
        win = self._windows.get(window_id)
        if win:
            win.state = WindowState.NORMAL
            win.visible = True

    def get_window(self, window_id: int) -> Optional[WindowInfo]:
        return self._windows.get(window_id)

    def list_windows(self) -> List[WindowInfo]:
        return sorted(self._windows.values(), key=lambda w: w.z_order)

    def get_focused(self) -> Optional[WindowInfo]:
        if self._focused_id is not None:
            return self._windows.get(self._focused_id)
        return None

    def window_at(self, x: int, y: int) -> Optional[WindowInfo]:
        for win in reversed(self.list_windows()):
            if win.visible and win.rect.contains(x, y):
                return win
        return None

    def set_mode(self, mode: WindowMode) -> None:
        self._mode = mode
        if mode == WindowMode.TILING:
            self._retile()

    def _retile(self) -> None:
        visible = [w for w in self._windows.values() if w.visible]
        if not visible:
            return
        n = len(visible)
        cols = math.ceil(math.sqrt(n))
        rows = math.ceil(n / cols)
        w = self._config.width // cols
        h = self._config.height // rows
        for i, win in enumerate(visible):
            col = i % cols
            row = i // cols
            win.rect = Rect(col * w, row * h, w, h)

    @property
    def window_count(self) -> int:
        return len(self._windows)


# ============================================================
# Event Dispatcher
# ============================================================

class EventDispatcher:
    """Event dispatch system for keyboard, mouse, and window events."""

    def __init__(self) -> None:
        self._handlers: Dict[EventKind, List[Callable]] = defaultdict(list)
        self._event_count = 0

    def register(self, kind: EventKind, handler: Callable) -> None:
        self._handlers[kind].append(handler)

    def dispatch(self, event: InputEvent) -> None:
        self._event_count += 1
        for handler in self._handlers.get(event.kind, []):
            handler(event)

    @property
    def event_count(self) -> int:
        return self._event_count


# ============================================================
# Widget System
# ============================================================

@dataclass
class Widget:
    """Base widget in the FizzWindow widget toolkit."""
    widget_id: str = ""
    widget_type: WidgetType = WidgetType.LABEL
    rect: Rect = field(default_factory=Rect)
    text: str = ""
    visible: bool = True
    enabled: bool = True
    focused: bool = False
    value: Any = None
    children: List["Widget"] = field(default_factory=list)
    layout: Optional[LayoutType] = None
    style: Dict[str, Any] = field(default_factory=dict)

class WidgetFactory:
    """Creates typed widgets with default properties."""

    @staticmethod
    def button(text: str, x: int = 0, y: int = 0, width: int = 120, height: int = 32) -> Widget:
        return Widget(widget_id=uuid.uuid4().hex[:8], widget_type=WidgetType.BUTTON,
                      rect=Rect(x, y, width, height), text=text)

    @staticmethod
    def label(text: str, x: int = 0, y: int = 0) -> Widget:
        return Widget(widget_id=uuid.uuid4().hex[:8], widget_type=WidgetType.LABEL,
                      rect=Rect(x, y, len(text) * 8, 20), text=text)

    @staticmethod
    def text_input(x: int = 0, y: int = 0, width: int = 200) -> Widget:
        return Widget(widget_id=uuid.uuid4().hex[:8], widget_type=WidgetType.TEXT_INPUT,
                      rect=Rect(x, y, width, 28), text="", value="")

    @staticmethod
    def checkbox(label: str, checked: bool = False, x: int = 0, y: int = 0) -> Widget:
        return Widget(widget_id=uuid.uuid4().hex[:8], widget_type=WidgetType.CHECKBOX,
                      rect=Rect(x, y, len(label) * 8 + 24, 20), text=label, value=checked)

    @staticmethod
    def dropdown(items: List[str], x: int = 0, y: int = 0, width: int = 150) -> Widget:
        return Widget(widget_id=uuid.uuid4().hex[:8], widget_type=WidgetType.DROPDOWN,
                      rect=Rect(x, y, width, 28), value=items[0] if items else "", style={"items": items})

    @staticmethod
    def list_view(items: List[str], x: int = 0, y: int = 0, width: int = 200, height: int = 150) -> Widget:
        return Widget(widget_id=uuid.uuid4().hex[:8], widget_type=WidgetType.LIST_VIEW,
                      rect=Rect(x, y, width, height), style={"items": items}, value=0)

    @staticmethod
    def progress_bar(value: float = 0.0, x: int = 0, y: int = 0, width: int = 200) -> Widget:
        return Widget(widget_id=uuid.uuid4().hex[:8], widget_type=WidgetType.PROGRESS_BAR,
                      rect=Rect(x, y, width, 20), value=min(max(value, 0.0), 1.0))

    @staticmethod
    def status_bar(text: str = "", width: int = 800) -> Widget:
        return Widget(widget_id=uuid.uuid4().hex[:8], widget_type=WidgetType.STATUS_BAR,
                      rect=Rect(0, 0, width, 24), text=text)

    @staticmethod
    def canvas(x: int = 0, y: int = 0, width: int = 400, height: int = 300) -> Widget:
        return Widget(widget_id=uuid.uuid4().hex[:8], widget_type=WidgetType.CANVAS,
                      rect=Rect(x, y, width, height))

    @staticmethod
    def panel(x: int = 0, y: int = 0, width: int = 300, height: int = 200,
              layout: LayoutType = LayoutType.VBOX) -> Widget:
        return Widget(widget_id=uuid.uuid4().hex[:8], widget_type=WidgetType.PANEL,
                      rect=Rect(x, y, width, height), layout=layout)


# ============================================================
# Layout Engine
# ============================================================

class LayoutEngine:
    """Arranges child widgets within a parent container."""

    def layout(self, parent: Widget, padding: int = 8) -> None:
        if parent.layout == LayoutType.HBOX:
            self._layout_hbox(parent, padding)
        elif parent.layout == LayoutType.VBOX:
            self._layout_vbox(parent, padding)
        elif parent.layout == LayoutType.GRID:
            self._layout_grid(parent, padding)
        # ABSOLUTE: children use their own coordinates

    def _layout_hbox(self, parent: Widget, padding: int) -> None:
        x = parent.rect.x + padding
        for child in parent.children:
            child.rect.x = x
            child.rect.y = parent.rect.y + padding
            x += child.rect.width + padding

    def _layout_vbox(self, parent: Widget, padding: int) -> None:
        y = parent.rect.y + padding
        for child in parent.children:
            child.rect.x = parent.rect.x + padding
            child.rect.y = y
            y += child.rect.height + padding

    def _layout_grid(self, parent: Widget, padding: int) -> None:
        cols = parent.style.get("columns", 2)
        cell_w = (parent.rect.width - padding * (cols + 1)) // cols
        for i, child in enumerate(parent.children):
            col = i % cols
            row = i // cols
            child.rect.x = parent.rect.x + padding + col * (cell_w + padding)
            child.rect.y = parent.rect.y + padding + row * (child.rect.height + padding)
            child.rect.width = cell_w


# ============================================================
# Font Renderer
# ============================================================

class FontRenderer:
    """Bitmap font renderer with glyph cache."""

    def __init__(self, font_name: str = DEFAULT_FONT, size: int = 14) -> None:
        self._font_name = font_name
        self._size = size
        self._glyph_cache: Dict[str, GlyphData] = {}
        self._cache_hits = 0
        self._cache_misses = 0

    def get_glyph(self, ch: str) -> GlyphData:
        if ch in self._glyph_cache:
            self._cache_hits += 1
            return self._glyph_cache[ch]
        self._cache_misses += 1
        glyph = GlyphData(character=ch, width=8, height=self._size + 2,
                           bitmap=[ord(ch)] * (8 * (self._size + 2)))
        self._glyph_cache[ch] = glyph
        return glyph

    def measure_text(self, text: str) -> Tuple[int, int]:
        return (len(text) * 8, self._size + 2)

    def render_text(self, fb: Framebuffer, x: int, y: int, text: str, color: Color) -> None:
        for i, ch in enumerate(text):
            self.get_glyph(ch)
            fb.draw_text(x + i * 8, y, ch, color)

    @property
    def cache_size(self) -> int:
        return len(self._glyph_cache)

    @property
    def hit_rate(self) -> float:
        total = self._cache_hits + self._cache_misses
        return (self._cache_hits / total * 100) if total > 0 else 0.0


# ============================================================
# Theme Engine
# ============================================================

class ThemeEngine:
    """Manages visual themes for the windowing system."""

    def __init__(self) -> None:
        self._themes: Dict[str, Theme] = {}
        self._active: str = DEFAULT_THEME
        self._register_defaults()

    def _register_defaults(self) -> None:
        self._themes["enterprise-dark"] = Theme(
            name="Enterprise Dark",
            bg_color=Color(30, 30, 30),
            fg_color=Color(220, 220, 220),
            accent_color=Color(66, 133, 244),
            border_color=Color(80, 80, 80),
            titlebar_color=Color(45, 45, 45),
            titlebar_text=Color(200, 200, 200),
            button_color=Color(55, 55, 55),
            button_hover=Color(75, 75, 75),
            input_bg=Color(40, 40, 40),
            selection_color=Color(66, 133, 244, 128),
        )
        self._themes["enterprise-light"] = Theme(
            name="Enterprise Light",
            bg_color=Color(245, 245, 245),
            fg_color=Color(30, 30, 30),
            accent_color=Color(25, 118, 210),
            border_color=Color(200, 200, 200),
            titlebar_color=Color(230, 230, 230),
            titlebar_text=Color(50, 50, 50),
            button_color=Color(220, 220, 220),
            button_hover=Color(200, 200, 200),
            input_bg=Color(255, 255, 255),
            selection_color=Color(25, 118, 210, 128),
        )

    def get_theme(self, name: str) -> Theme:
        theme = self._themes.get(name)
        if theme is None:
            raise FizzWindowThemeNotFoundError(name)
        return theme

    def get_active(self) -> Theme:
        return self._themes[self._active]

    def set_active(self, name: str) -> None:
        if name not in self._themes:
            raise FizzWindowThemeNotFoundError(name)
        self._active = name

    def list_themes(self) -> List[str]:
        return sorted(self._themes.keys())


# ============================================================
# Clipboard Manager
# ============================================================

class ClipboardManager:
    """System clipboard for copy/paste operations."""

    def __init__(self) -> None:
        self._content: str = ""
        self._history: List[str] = []
        self._op_count = 0

    def copy(self, text: str) -> None:
        self._content = text
        self._history.append(text)
        self._op_count += 1

    def paste(self) -> str:
        self._op_count += 1
        return self._content

    def clear(self) -> None:
        self._content = ""

    @property
    def has_content(self) -> bool:
        return bool(self._content)

    @property
    def operation_count(self) -> int:
        return self._op_count


# ============================================================
# Multi-Monitor Manager
# ============================================================

class MultiMonitorManager:
    """Multi-monitor configuration and management."""

    def __init__(self, config: FizzWindowConfig) -> None:
        self._monitors: List[MonitorInfo] = []
        for i in range(config.monitors):
            self._monitors.append(MonitorInfo(
                monitor_id=i,
                name=f"FIZZ-DISPLAY-{i}",
                rect=Rect(i * config.width, 0, config.width, config.height),
                dpi=config.dpi,
                primary=(i == 0),
                refresh_rate=config.fps_limit,
            ))

    def get_primary(self) -> MonitorInfo:
        for m in self._monitors:
            if m.primary:
                return m
        return self._monitors[0]

    def get_monitor(self, monitor_id: int) -> Optional[MonitorInfo]:
        for m in self._monitors:
            if m.monitor_id == monitor_id:
                return m
        return None

    def list_monitors(self) -> List[MonitorInfo]:
        return list(self._monitors)

    @property
    def total_width(self) -> int:
        if not self._monitors:
            return 0
        return max(m.rect.x + m.rect.width for m in self._monitors)

    @property
    def total_height(self) -> int:
        if not self._monitors:
            return 0
        return max(m.rect.y + m.rect.height for m in self._monitors)


# ============================================================
# Built-in Applications
# ============================================================

class FizzTerm:
    """Built-in terminal emulator application."""

    def __init__(self, wm: WindowManager) -> None:
        self._wm = wm
        self._window: Optional[WindowInfo] = None
        self._lines: List[str] = []
        self._prompt = "fizzbuzz$ "

    def launch(self) -> WindowInfo:
        self._window = self._wm.create_window("FizzTerm", 100, 100, 720, 480)
        self._lines = [
            f"FizzTerm 1.0 - Enterprise FizzBuzz Platform Terminal",
            f"Type 'help' for available commands.",
            "",
            self._prompt,
        ]
        return self._window

    def execute(self, command: str) -> str:
        self._lines.append(f"{self._prompt}{command}")
        if command == "help":
            output = "Available: help, fizzbuzz <n>, clear, exit"
        elif command.startswith("fizzbuzz"):
            parts = command.split()
            n = int(parts[1]) if len(parts) > 1 else 15
            if n % 15 == 0: output = "FizzBuzz"
            elif n % 3 == 0: output = "Fizz"
            elif n % 5 == 0: output = "Buzz"
            else: output = str(n)
        elif command == "clear":
            self._lines.clear()
            output = ""
        else:
            output = f"{command}: command not found"
        if output:
            self._lines.append(output)
        self._lines.append(self._prompt)
        return output

    def get_output(self) -> str:
        return "\n".join(self._lines)


class FizzView:
    """Built-in image viewer application."""

    def __init__(self, wm: WindowManager) -> None:
        self._wm = wm
        self._window: Optional[WindowInfo] = None
        self._image_path: str = ""
        self._zoom: float = 1.0

    def launch(self, image_path: str = "") -> WindowInfo:
        self._window = self._wm.create_window("FizzView", 150, 150, 800, 600)
        self._image_path = image_path
        return self._window

    def zoom_in(self) -> float:
        self._zoom = min(self._zoom * 1.25, 10.0)
        return self._zoom

    def zoom_out(self) -> float:
        self._zoom = max(self._zoom / 1.25, 0.1)
        return self._zoom

    def get_info(self) -> Dict[str, Any]:
        return {"path": self._image_path, "zoom": self._zoom}


class FizzMonitor:
    """Built-in system monitor dashboard application."""

    def __init__(self, wm: WindowManager) -> None:
        self._wm = wm
        self._window: Optional[WindowInfo] = None

    def launch(self) -> WindowInfo:
        self._window = self._wm.create_window("FizzMonitor", 200, 50, 900, 650)
        return self._window

    def get_metrics(self) -> Dict[str, Any]:
        return {
            "cpu_usage": 94.7,
            "memory_used_mb": 52428,
            "memory_total_mb": 104857,
            "modules_loaded": 140,
            "uptime_hours": 1008,
            "processes": 142,
            "threads": 847,
            "open_files": 2048,
            "network_rx_mbps": 12.4,
            "network_tx_mbps": 8.7,
            "disk_usage_pct": 5.0,
            "operator_stress_pct": 94.7,
        }


# ============================================================
# Display Server (Top-Level Coordinator)
# ============================================================

class DisplayServer:
    """Top-level display server coordinating all windowing subsystems."""

    def __init__(self, config: FizzWindowConfig,
                 framebuffer: Framebuffer,
                 compositor: Compositor,
                 window_manager: WindowManager,
                 event_dispatcher: EventDispatcher,
                 theme_engine: ThemeEngine,
                 font_renderer: FontRenderer,
                 clipboard: ClipboardManager,
                 monitor_manager: MultiMonitorManager,
                 metrics: DisplayMetrics) -> None:
        self._config = config
        self._fb = framebuffer
        self._compositor = compositor
        self._wm = window_manager
        self._events = event_dispatcher
        self._themes = theme_engine
        self._fonts = font_renderer
        self._clipboard = clipboard
        self._monitors = monitor_manager
        self._metrics = metrics
        self._started = False
        self._start_time = 0.0
        self._apps: Dict[str, Any] = {}

    def start(self) -> None:
        self._started = True
        self._start_time = time.time()
        self._compositor.damage_all()
        self._compositor.composite(self._wm.list_windows(), self._themes.get_active())
        logger.info("Display server started: %dx%d %s theme=%s",
                     self._config.width, self._config.height,
                     self._config.mode, self._config.theme)

    def create_window(self, title: str, x: int = 50, y: int = 50,
                      width: int = 640, height: int = 480) -> WindowInfo:
        win = self._wm.create_window(title, x, y, width, height)
        self._compositor.damage(win.rect)
        self._metrics.windows_created += 1
        return win

    def destroy_window(self, window_id: int) -> None:
        win = self._wm.get_window(window_id)
        if win:
            self._compositor.damage(win.rect)
        self._wm.destroy_window(window_id)
        self._metrics.windows_destroyed += 1

    def render_frame(self) -> None:
        theme = self._themes.get_active()
        windows = self._wm.list_windows()
        # Damage all visible windows
        for win in windows:
            if win.visible:
                self._compositor.damage(win.rect)
        self._compositor.composite(windows, theme)
        self._metrics.total_frames += 1

    def dispatch_event(self, event: InputEvent) -> None:
        self._events.dispatch(event)
        self._metrics.events_dispatched += 1

    def capture_screen(self) -> bytes:
        self.render_frame()
        self._metrics.captures_taken += 1
        return self._fb.to_ppm()

    def launch_app(self, app_name: str) -> Optional[WindowInfo]:
        if app_name == "fizzterm":
            app = FizzTerm(self._wm)
            win = app.launch()
            self._apps["fizzterm"] = app
            return win
        elif app_name == "fizzview":
            app = FizzView(self._wm)
            win = app.launch()
            self._apps["fizzview"] = app
            return win
        elif app_name == "fizzmonitor":
            app = FizzMonitor(self._wm)
            win = app.launch()
            self._apps["fizzmonitor"] = app
            return win
        return None

    def get_app(self, name: str) -> Optional[Any]:
        return self._apps.get(name)

    def get_metrics(self) -> DisplayMetrics:
        return copy.copy(self._metrics)

    @property
    def uptime(self) -> float:
        return time.time() - self._start_time if self._started else 0.0

    @property
    def is_running(self) -> bool:
        return self._started


# ============================================================
# Dashboard
# ============================================================

class FizzWindowDashboard:
    def __init__(self, display: DisplayServer, wm: WindowManager,
                 monitors: MultiMonitorManager, fonts: FontRenderer,
                 themes: ThemeEngine, width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._display = display
        self._wm = wm
        self._monitors = monitors
        self._fonts = fonts
        self._themes = themes
        self._width = width

    def render(self) -> str:
        m = self._display.get_metrics()
        sections = [
            "=" * self._width,
            "FizzWindow Display Server Dashboard".center(self._width),
            "=" * self._width,
            f"  Server ({FIZZWINDOW_VERSION})",
            f"  {'─' * (self._width - 4)}",
            f"  Status:       {'RUNNING' if self._display.is_running else 'STOPPED'}",
            f"  Uptime:       {self._display.uptime:.1f}s",
            f"  Resolution:   {self._display._config.width}x{self._display._config.height}",
            f"  Mode:         {self._display._config.mode}",
            f"  Theme:        {self._display._config.theme}",
            f"  Monitors:     {len(self._monitors.list_monitors())}",
            f"  Windows:      {self._wm.window_count}",
            f"  Frames:       {m.total_frames}",
            f"  Events:       {m.events_dispatched}",
            f"  Captures:     {m.captures_taken}",
            f"  Font Cache:   {self._fonts.cache_size} glyphs ({self._fonts.hit_rate:.0f}% hit)",
            f"  Themes:       {', '.join(self._themes.list_themes())}",
        ]
        # Window list
        windows = self._wm.list_windows()
        if windows:
            sections.append(f"\n  Open Windows")
            sections.append(f"  {'─' * (self._width - 4)}")
            for win in windows:
                focus = "*" if win.focused else " "
                sections.append(
                    f"  {focus} [{win.window_id}] {win.title:<25} {win.rect.width}x{win.rect.height} "
                    f"at ({win.rect.x},{win.rect.y}) {win.state.name}"
                )
        return "\n".join(sections)


# ============================================================
# Middleware
# ============================================================

class FizzWindowMiddleware(IMiddleware):
    def __init__(self, display: DisplayServer, dashboard: FizzWindowDashboard,
                 config: FizzWindowConfig) -> None:
        self._display = display
        self._dashboard = dashboard
        self._config = config

    def get_name(self) -> str:
        return "fizzwindow"

    def process(self, context: ProcessingContext, next_handler: Any) -> ProcessingContext:
        m = self._display.get_metrics()
        context.metadata["fizzwindow_version"] = FIZZWINDOW_VERSION
        context.metadata["fizzwindow_running"] = self._display.is_running
        context.metadata["fizzwindow_windows"] = self._display._wm.window_count
        context.metadata["fizzwindow_frames"] = m.total_frames
        if next_handler is not None:
            return next_handler(context)
        return context

    def get_priority(self) -> int:
        return MIDDLEWARE_PRIORITY

    def render_dashboard(self) -> str:
        return self._dashboard.render()

    def render_status(self) -> str:
        m = self._display.get_metrics()
        return (
            f"FizzWindow {FIZZWINDOW_VERSION} | "
            f"{'UP' if self._display.is_running else 'DOWN'} | "
            f"{self._config.width}x{self._config.height} | "
            f"Windows: {self._display._wm.window_count} | "
            f"Frames: {m.total_frames}"
        )

    def render_capture(self) -> str:
        ppm = self._display.capture_screen()
        return f"Screen captured: {len(ppm)} bytes PPM ({self._config.width}x{self._config.height})"

    def render_app(self, app_name: str) -> str:
        win = self._display.launch_app(app_name)
        if win is None:
            return f"Unknown application: {app_name}\nAvailable: fizzterm, fizzview, fizzmonitor"
        app = self._display.get_app(app_name)
        lines = [f"Launched: {win.title} (window {win.window_id})"]
        if app_name == "fizzterm":
            lines.append(app.get_output())
        elif app_name == "fizzmonitor":
            metrics = app.get_metrics()
            for k, v in metrics.items():
                lines.append(f"  {k}: {v}")
        return "\n".join(lines)


# ============================================================
# Factory Function
# ============================================================

def create_fizzwindow_subsystem(
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    mode: str = "floating",
    theme: str = DEFAULT_THEME,
    monitors: int = 1,
    fps_limit: int = DEFAULT_FPS,
    dpi: int = DEFAULT_DPI,
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[DisplayServer, FizzWindowDashboard, FizzWindowMiddleware]:
    config = FizzWindowConfig(
        width=width, height=height, mode=mode, theme=theme,
        monitors=monitors, fps_limit=fps_limit, dpi=dpi,
        dashboard_width=dashboard_width,
    )

    fb = Framebuffer(width, height)
    compositor = Compositor(fb, config)
    wm = WindowManager(config)
    events = EventDispatcher()
    themes = ThemeEngine()
    fonts = FontRenderer()
    clipboard = ClipboardManager()
    monitor_mgr = MultiMonitorManager(config)
    metrics = DisplayMetrics()

    themes.set_active(theme)

    display = DisplayServer(
        config, fb, compositor, wm, events, themes, fonts,
        clipboard, monitor_mgr, metrics,
    )

    dashboard = FizzWindowDashboard(display, wm, monitor_mgr, fonts, themes, dashboard_width)
    middleware = FizzWindowMiddleware(display, dashboard, config)

    display.start()

    logger.info("FizzWindow subsystem initialized: %dx%d mode=%s theme=%s monitors=%d",
                width, height, mode, theme, monitors)

    return display, dashboard, middleware
