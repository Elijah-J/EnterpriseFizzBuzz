# PLAN.md -- FizzWindow: Windowing System & Display Server

## Motivation

The Enterprise FizzBuzz Platform currently operates 139+ infrastructure modules,
an operating system kernel, a virtual file system, a TCP/IP stack, a GPU shader
compiler, and a terminal emulator subsystem -- yet every graphical interaction
must still be delegated to external display servers.  This is an unacceptable
operational dependency.  FizzWindow provides the platform's own compositor,
window manager, event dispatch pipeline, widget toolkit, and built-in graphical
applications, enabling end-to-end FizzBuzz rendering without third-party display
infrastructure.

Architecture reference: X11 (X Window System), Wayland protocol, Win32 GDI/User,
Quartz Compositor (macOS), SDL2, GTK, Qt.

## File Layout

| File | Purpose |
|------|---------|
| `enterprise_fizzbuzz/infrastructure/fizzwindow.py` | Core module (~3,500 lines) |
| `enterprise_fizzbuzz/infrastructure/features/fizzwindow_feature.py` | Feature descriptor, CLI flags |
| `enterprise_fizzbuzz/infrastructure/config/mixins/fizzwindow.py` | Config mixin for `ConfigurationManager` |
| `enterprise_fizzbuzz/domain/exceptions/fizzwindow_exceptions.py` | Exception hierarchy |
| `fizzwindow.py` | Backward-compatible re-export stub |
| `tests/test_fizzwindow.py` | 200+ tests |

## CLI Flags (12)

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--fizzwindow` | store_true | False | Enable FizzWindow display server |
| `--fizzwindow-resolution` | str | "1920x1080" | Default screen resolution (WxH) |
| `--fizzwindow-refresh-rate` | int | 60 | Display refresh rate in Hz |
| `--fizzwindow-wm-mode` | str | "floating" | Window manager mode: floating or tiling |
| `--fizzwindow-theme` | str | "enterprise-dark" | Theme: enterprise-dark or enterprise-light |
| `--fizzwindow-font-size` | int | 14 | Default font size in pixels |
| `--fizzwindow-multi-monitor` | store_true | False | Enable multi-monitor support |
| `--fizzwindow-monitors` | int | 1 | Number of virtual monitors (1-8) |
| `--fizzwindow-vsync` | store_true | True | Enable vertical sync |
| `--fizzwindow-clipboard` | store_true | True | Enable clipboard manager |
| `--fizzwindow-dnd` | store_true | True | Enable drag-and-drop protocol |
| `--fizzwindow-screen-capture` | store_true | True | Enable screen capture subsystem |

## Exception Hierarchy

All exceptions derive from `FizzBuzzBaseException`.

- `FizzWindowError` -- base for all FizzWindow errors
  - `DisplayServerError` -- compositor or display server failures
    - `CompositorDamageError` -- damage region tracking failures
    - `BufferSwapError` -- double-buffer swap failures
    - `VsyncError` -- vertical sync timing failures
  - `WindowManagerError` -- window management failures
    - `WindowCreationError` -- window creation failures
    - `WindowNotFoundError` -- reference to non-existent window
    - `TilingLayoutError` -- tiling layout constraint violations
    - `FocusError` -- focus state machine violations
  - `EventDispatchError` -- input/event pipeline failures
    - `KeyboardEventError` -- keyboard event processing failures
    - `MouseEventError` -- mouse event processing failures
    - `EventQueueOverflowError` -- event queue capacity exceeded
  - `WidgetError` -- widget toolkit failures
    - `WidgetCreationError` -- widget instantiation failures
    - `WidgetRenderError` -- widget rendering failures
    - `LayoutConstraintError` -- layout engine constraint violations
  - `FontRenderError` -- font rendering failures
    - `GlyphCacheMissError` -- glyph not found in cache
    - `GlyphCacheEvictionError` -- cache eviction policy failure
  - `ThemeError` -- theme engine failures
    - `ThemeNotFoundError` -- requested theme does not exist
    - `ThemeParseError` -- theme definition parse failure
  - `ClipboardError` -- clipboard manager failures
  - `DragDropError` -- drag-and-drop protocol failures
  - `ScreenCaptureError` -- screen capture failures
  - `ApplicationError` -- built-in application failures
    - `FizzTermError` -- terminal emulator failures
    - `FizzViewError` -- image viewer failures
    - `FizzMonitorError` -- system monitor dashboard failures

## Phase 1: Display Server & Compositor (~900 lines)

### 1.1 Pixel Buffer and Color Model

```
class Color(NamedTuple):
    r: int  # 0-255
    g: int  # 0-255
    b: int  # 0-255
    a: int  # 0-255, alpha channel

class PixelBuffer:
    """RGBA pixel buffer backed by a flat bytearray."""
    width: int
    height: int
    data: bytearray  # length = width * height * 4

    def get_pixel(x, y) -> Color
    def set_pixel(x, y, color: Color)
    def fill_rect(x, y, w, h, color: Color)
    def blit(src: PixelBuffer, dst_x, dst_y, src_rect: Optional[Rect])
    def clear(color: Color)
```

### 1.2 Damage Tracking

```
class DamageTracker:
    """Tracks rectangular dirty regions for incremental re-rendering."""
    _regions: list[Rect]

    def mark_damaged(rect: Rect)
    def merge_regions() -> list[Rect]  # coalesce overlapping rects
    def clear()
    def is_damaged() -> bool
```

Merge algorithm: iterate regions, union any overlapping or adjacent rectangles.
This avoids full-screen redraws when only localized updates occur.

### 1.3 Compositor

```
class Compositor:
    """Double-buffered compositor with damage-tracked rendering."""
    front_buffer: PixelBuffer
    back_buffer: PixelBuffer
    damage_tracker: DamageTracker
    layers: list[CompositorLayer]  # ordered back-to-front (painter's algorithm)

    def add_layer(layer: CompositorLayer)
    def remove_layer(layer_id: str)
    def reorder_layer(layer_id: str, z_index: int)
    def compose_frame()  # render damaged regions to back buffer
    def swap_buffers()   # swap front/back (double buffering)
    def get_framebuffer() -> PixelBuffer  # read-only access to front buffer
```

`compose_frame()` iterates damaged regions, for each region iterates layers
back-to-front, blits the intersecting portion of each layer's surface into the
back buffer.  Alpha compositing uses the standard Porter-Duff "over" operator.

### 1.4 VSync Simulation

```
class VsyncController:
    """Simulates vertical sync timing at the configured refresh rate."""
    refresh_rate: int
    frame_time_ns: int
    last_frame_time: int

    def wait_for_vsync()  # returns when next vsync interval arrives
    def get_frame_number() -> int
```

### Tests: ~40 tests

- PixelBuffer get/set, fill_rect, blit, clear, out-of-bounds handling
- DamageTracker mark, merge (overlapping, adjacent, disjoint), clear
- Compositor layer ordering, compose with damage, swap buffers, alpha blending
- VsyncController frame timing accuracy

## Phase 2: Window Manager & Event Dispatch (~900 lines)

### 2.1 Window

```
class Window:
    window_id: str
    title: str
    x, y, width, height: int
    min_width, min_height: int
    max_width, max_height: int
    visible: bool
    focused: bool
    resizable: bool
    decorations: bool  # title bar, borders
    surface: PixelBuffer
    children: list[Widget]
```

### 2.2 Window Manager

```
class WindowManager:
    """Manages window lifecycle, positioning, and focus."""
    mode: str  # "floating" or "tiling"
    windows: dict[str, Window]
    focus_stack: list[str]  # window IDs, most-recent-first
    screen_width, screen_height: int

    def create_window(title, x, y, w, h, **kwargs) -> Window
    def close_window(window_id)
    def move_window(window_id, x, y)
    def resize_window(window_id, w, h)
    def focus_window(window_id)
    def minimize_window(window_id)
    def maximize_window(window_id)
    def tile_windows()  # apply tiling layout to all visible windows
    def get_window_at(x, y) -> Optional[Window]  # hit testing
    def get_focused_window() -> Optional[Window]
```

Floating mode: windows freely positioned, overlap allowed, z-order follows
focus stack.  Tiling mode: windows arranged in a binary split tree that fills
the screen without overlap (similar to i3/dwm).

### 2.3 Event System

```
class EventType(Enum):
    KEY_DOWN, KEY_UP, MOUSE_DOWN, MOUSE_UP, MOUSE_MOVE,
    MOUSE_SCROLL, FOCUS_IN, FOCUS_OUT, WINDOW_RESIZE,
    WINDOW_CLOSE, WINDOW_MOVE, DRAG_START, DRAG_MOVE,
    DRAG_DROP, CLIPBOARD_COPY, CLIPBOARD_PASTE

class Event:
    event_type: EventType
    target_window_id: Optional[str]
    timestamp: float
    data: dict[str, Any]

class EventQueue:
    """Thread-safe bounded event queue."""
    _queue: deque
    max_size: int

    def push(event: Event)
    def pop() -> Optional[Event]
    def peek() -> Optional[Event]
    def is_empty() -> bool

class EventDispatcher:
    """Routes events to target windows and widgets."""
    event_queue: EventQueue
    window_manager: WindowManager
    handlers: dict[EventType, list[Callable]]

    def dispatch_event(event: Event)
    def register_handler(event_type: EventType, handler: Callable)
    def unregister_handler(event_type: EventType, handler: Callable)
    def process_all_pending()
```

Event routing: keyboard events go to the focused window.  Mouse events go to
the window under the cursor (hit test via `get_window_at`).  Focus events are
generated when the focused window changes.  Resize events are generated by the
window manager.

### 2.4 Multi-Monitor Support

```
class Monitor:
    monitor_id: str
    x, y: int           # position in virtual desktop
    width, height: int
    refresh_rate: int
    primary: bool

class MultiMonitorManager:
    monitors: dict[str, Monitor]
    virtual_desktop: Rect  # bounding box of all monitors

    def add_monitor(monitor: Monitor)
    def remove_monitor(monitor_id: str)
    def get_monitor_at(x, y) -> Optional[Monitor]
    def get_primary_monitor() -> Monitor
    def arrange_horizontal()  # place monitors side-by-side
```

### Tests: ~50 tests

- Window create, close, move, resize, minimize, maximize
- Floating mode: overlap, z-order, focus stack
- Tiling mode: binary split, screen coverage, no overlap
- EventQueue push/pop/overflow
- EventDispatcher routing: keyboard to focused, mouse to hit-test target
- Multi-monitor arrangement, get_monitor_at, primary detection

## Phase 3: Widget Toolkit, Layout Engine & Font Renderer (~1,100 lines)

### 3.1 Widget Base

```
class Widget(ABC):
    widget_id: str
    x, y, width, height: int  # relative to parent
    visible: bool
    enabled: bool
    parent: Optional[Widget]
    children: list[Widget]

    @abstractmethod
    def render(surface: PixelBuffer)

    @abstractmethod
    def handle_event(event: Event) -> bool  # consumed?

    def get_absolute_position() -> tuple[int, int]
    def invalidate()  # marks widget region as damaged
```

### 3.2 Concrete Widgets

| Widget | Key Properties | Behavior |
|--------|---------------|----------|
| `Button` | label, on_click callback | Renders label, hover/pressed states, fires on_click |
| `Label` | text, alignment | Static text rendering |
| `TextInput` | text, cursor_pos, on_change | Editable text field with cursor, selection |
| `Checkbox` | checked, on_toggle | Toggle boolean state |
| `Dropdown` | items, selected_index, on_select | Expandable list with single selection |
| `ListView` | items, selected_index, on_select | Scrollable list of items |
| `ScrollArea` | content_widget, scroll_x, scroll_y | Scrollable viewport over a child widget |
| `TabBar` | tabs, active_tab, on_tab_change | Horizontal tab strip |
| `MenuBar` | menus (nested), on_menu_select | Horizontal menu bar with dropdown submenus |
| `StatusBar` | segments (list of str) | Horizontal status segments at bottom of window |
| `Canvas` | draw commands list | Programmable drawing surface (lines, rects, circles) |

### 3.3 Layout Engine

```
class LayoutEngine(ABC):
    @abstractmethod
    def layout(widgets: list[Widget], bounds: Rect)

class HBoxLayout(LayoutEngine):
    """Horizontal box: widgets placed left-to-right."""
    spacing: int
    alignment: str  # "start", "center", "end"

class VBoxLayout(LayoutEngine):
    """Vertical box: widgets placed top-to-bottom."""
    spacing: int
    alignment: str

class GridLayout(LayoutEngine):
    """Grid: widgets placed in rows and columns."""
    rows: int
    columns: int
    row_spacing: int
    col_spacing: int

class AbsoluteLayout(LayoutEngine):
    """Absolute positioning: widgets placed at explicit coordinates."""
```

Layout resolution: each layout engine computes the `(x, y, width, height)` of
each child widget within the given bounds rect.  HBox/VBox distribute available
space equally among children, then apply spacing and alignment.  Grid divides
the bounds into a rows x columns grid.  Absolute layout uses each widget's
explicit coordinates.

### 3.4 Font Renderer

```
class BitmapFont:
    """Fixed-width bitmap font with configurable glyph size."""
    glyph_width: int
    glyph_height: int
    glyphs: dict[str, list[list[int]]]  # char -> 2D bitmap (1/0)

    def get_glyph(char: str) -> list[list[int]]
    def text_width(text: str) -> int
    def text_height() -> int

class GlyphCache:
    """LRU cache for pre-rendered glyph bitmaps."""
    max_size: int
    _cache: OrderedDict[tuple[str, Color], PixelBuffer]

    def get(char: str, color: Color) -> Optional[PixelBuffer]
    def put(char: str, color: Color, rendered: PixelBuffer)
    def evict_lru()
    def clear()

class TextRenderer:
    """Renders text strings to pixel buffers using BitmapFont + GlyphCache."""
    font: BitmapFont
    glyph_cache: GlyphCache

    def render_text(text: str, color: Color) -> PixelBuffer
    def render_text_to(surface: PixelBuffer, x: int, y: int, text: str, color: Color)
```

The bitmap font ships with printable ASCII glyphs (32-126) defined as
hard-coded pixel matrices.  Enterprise production environments require
deterministic rendering without external font file dependencies.

### 3.5 Theme Engine

```
class ThemeColors(NamedTuple):
    background: Color
    foreground: Color
    primary: Color
    secondary: Color
    accent: Color
    border: Color
    title_bar: Color
    title_text: Color
    button_bg: Color
    button_hover: Color
    button_pressed: Color
    input_bg: Color
    input_border: Color
    selection: Color
    scrollbar: Color
    status_bar_bg: Color
    status_bar_fg: Color

class Theme:
    name: str
    colors: ThemeColors

ENTERPRISE_DARK = Theme(...)   # dark backgrounds, light text
ENTERPRISE_LIGHT = Theme(...)  # light backgrounds, dark text

class ThemeEngine:
    current_theme: Theme
    available_themes: dict[str, Theme]

    def set_theme(name: str)
    def get_color(role: str) -> Color
    def register_theme(theme: Theme)
```

### Tests: ~60 tests

- Each widget type: creation, rendering, event handling
- Layout engine: HBox, VBox, Grid, Absolute -- correct positioning
- Font renderer: glyph lookup, text rendering, cache hit/miss/eviction
- Theme engine: switching themes, color lookups, custom theme registration

## Phase 4: Clipboard, Drag-and-Drop, Screen Capture & Built-in Applications (~600 lines)

### 4.1 Clipboard Manager

```
class ClipboardManager:
    """Platform clipboard with text and pixel buffer support."""
    _text: Optional[str]
    _image: Optional[PixelBuffer]
    _history: list[dict]  # clipboard history (last 50 entries)

    def copy_text(text: str)
    def paste_text() -> Optional[str]
    def copy_image(image: PixelBuffer)
    def paste_image() -> Optional[PixelBuffer]
    def clear()
    def get_history() -> list[dict]
```

### 4.2 Drag-and-Drop Protocol

```
class DragDropManager:
    """Manages drag-and-drop state machine between source and target widgets."""
    _active_drag: Optional[DragSession]

    def start_drag(source_widget: Widget, data: Any, data_type: str)
    def update_drag(x: int, y: int)  # generates DRAG_MOVE events
    def drop(target_widget: Widget)   # generates DRAG_DROP events
    def cancel_drag()
```

State machine: IDLE -> DRAGGING (on start_drag) -> DROPPED (on drop) -> IDLE.
Target widgets declare accepted data types; drops on non-accepting widgets are
rejected.

### 4.3 Screen Capture

```
class ScreenCapture:
    """Captures framebuffer contents to PPM image format."""
    def capture_full_screen(compositor: Compositor) -> bytes  # PPM P6
    def capture_window(window: Window) -> bytes               # PPM P6
    def capture_region(compositor: Compositor, rect: Rect) -> bytes
```

PPM (Portable Pixmap) format is used because it requires no external libraries
and is widely supported by image viewers.

### 4.4 Built-in Applications

#### FizzTerm -- Terminal Emulator

```
class FizzTerm:
    """Built-in terminal emulator for the FizzWindow display server."""
    window: Window
    columns, rows: int
    cursor_x, cursor_y: int
    screen_buffer: list[list[tuple[str, Color, Color]]]  # char, fg, bg
    input_buffer: str

    def write(text: str)       # write text at cursor, advance cursor
    def handle_key(event: Event)
    def scroll_up(lines: int)
    def clear_screen()
    def render(surface: PixelBuffer)
```

Supports printable ASCII output, newline/carriage-return handling, basic cursor
movement, and backspace.

#### FizzView -- Image Viewer

```
class FizzView:
    """Built-in PPM image viewer."""
    window: Window
    image: Optional[PixelBuffer]

    def load_ppm(data: bytes)
    def render(surface: PixelBuffer)  # scales image to fit window
```

Reads PPM P6 (binary) format and renders to a FizzWindow window.

#### FizzMonitor -- System Monitor Dashboard

```
class FizzMonitor:
    """Built-in system monitor dashboard displaying platform metrics."""
    window: Window
    panels: list[Widget]  # labels showing live metrics

    def update_metrics(metrics: dict)
    def render(surface: PixelBuffer)
```

Displays: active windows count, event queue depth, compositor frame count,
glyph cache hit rate, clipboard history size, memory estimate.

### Tests: ~50 tests

- Clipboard: copy/paste text, copy/paste image, history, clear
- DragDropManager: state machine transitions, accept/reject by type
- ScreenCapture: full screen, window, region -- validate PPM header and dimensions
- FizzTerm: write, cursor movement, scroll, clear, key handling
- FizzView: load valid PPM, render
- FizzMonitor: update metrics, panel rendering

## Config Mixin Properties

```
fizzwindow_enabled: bool
fizzwindow_resolution: str
fizzwindow_refresh_rate: int
fizzwindow_wm_mode: str
fizzwindow_theme: str
fizzwindow_font_size: int
fizzwindow_multi_monitor: bool
fizzwindow_monitor_count: int
fizzwindow_vsync: bool
fizzwindow_clipboard_enabled: bool
fizzwindow_dnd_enabled: bool
fizzwindow_screen_capture_enabled: bool
```

## Integration Points

- **`__main__.py`**: Register CLI flags via feature descriptor, wire
  `FizzWindowDisplayServer` into the service builder.
- **`config/_compose.py`**: Import `FizzwindowConfigMixin` into the
  `ConfigurationManager` MRO.
- **Backward compat stub**: `fizzwindow.py` at project root re-exports from
  `enterprise_fizzbuzz.infrastructure.fizzwindow`.

## Summary

| Phase | Lines | Tests | Deliverable |
|-------|-------|-------|-------------|
| 1 | ~900 | ~40 | Display server, compositor, damage tracking, double buffering |
| 2 | ~900 | ~50 | Window manager (floating + tiling), event dispatch, multi-monitor |
| 3 | ~1,100 | ~60 | Widget toolkit (11 widgets), layout engine (4 modes), font renderer, theme engine |
| 4 | ~600 | ~50 | Clipboard, drag-and-drop, screen capture, FizzTerm, FizzView, FizzMonitor |
| **Total** | **~3,500** | **~200** | Complete windowing system and display server |
