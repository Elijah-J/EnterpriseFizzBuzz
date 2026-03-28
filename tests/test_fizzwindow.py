"""
Tests for enterprise_fizzbuzz.infrastructure.fizzwindow
"""

from __future__ import annotations
from unittest.mock import MagicMock
import pytest

from enterprise_fizzbuzz.infrastructure.fizzwindow import (
    FIZZWINDOW_VERSION, MIDDLEWARE_PRIORITY,
    WindowMode, WindowState, EventKind, WidgetType, LayoutType,
    FizzWindowConfig, Color, Rect, Pixel, DamageRegion, InputEvent,
    WindowInfo, MonitorInfo, Theme, GlyphData, DisplayMetrics,
    Framebuffer, Compositor, WindowManager, EventDispatcher,
    Widget, WidgetFactory, LayoutEngine, FontRenderer, ThemeEngine,
    ClipboardManager, MultiMonitorManager,
    FizzTerm, FizzView, FizzMonitor,
    DisplayServer, FizzWindowDashboard, FizzWindowMiddleware,
    create_fizzwindow_subsystem,
)


@pytest.fixture
def config():
    return FizzWindowConfig(width=320, height=240)

@pytest.fixture
def subsystem():
    return create_fizzwindow_subsystem(width=320, height=240)


class TestColor:
    def test_to_hex(self):
        assert Color(255, 0, 128).to_hex() == "#ff0080"

    def test_defaults(self):
        c = Color()
        assert c.r == 0 and c.a == 255

class TestRect:
    def test_contains(self):
        r = Rect(10, 10, 100, 100)
        assert r.contains(50, 50)
        assert not r.contains(5, 5)

    def test_intersects(self):
        r1 = Rect(0, 0, 100, 100)
        r2 = Rect(50, 50, 100, 100)
        r3 = Rect(200, 200, 10, 10)
        assert r1.intersects(r2)
        assert not r1.intersects(r3)

class TestDamageRegion:
    def test_add_and_clear(self):
        d = DamageRegion()
        assert d.is_empty
        d.add(Rect(0, 0, 10, 10))
        assert not d.is_empty
        d.clear()
        assert d.is_empty

class TestFramebuffer:
    def test_set_and_get_pixel(self):
        fb = Framebuffer(10, 10)
        fb.set_pixel(5, 5, 255, 0, 0)
        fb.swap()
        p = fb.get_pixel(5, 5)
        assert p.r == 255

    def test_fill_rect(self):
        fb = Framebuffer(10, 10)
        fb.fill_rect(Rect(0, 0, 5, 5), Color(0, 255, 0))
        fb.swap()
        assert fb.get_pixel(2, 2).g == 255

    def test_to_ppm(self):
        fb = Framebuffer(2, 2)
        fb.swap()
        ppm = fb.to_ppm()
        assert ppm.startswith(b"P6\n2 2\n255\n")

    def test_out_of_bounds(self):
        fb = Framebuffer(5, 5)
        fb.set_pixel(-1, -1, 255, 0, 0)  # Should not crash
        fb.set_pixel(100, 100, 255, 0, 0)  # Should not crash

    def test_dimensions(self):
        fb = Framebuffer(320, 240)
        assert fb.width == 320
        assert fb.height == 240

class TestCompositor:
    def test_composite(self, config):
        fb = Framebuffer(config.width, config.height)
        comp = Compositor(fb, config)
        comp.damage_all()
        comp.composite([], Theme())
        assert comp.frame_count == 1

    def test_no_damage_no_composite(self, config):
        fb = Framebuffer(config.width, config.height)
        comp = Compositor(fb, config)
        comp.composite([], Theme())
        assert comp.frame_count == 0

class TestWindowManager:
    def test_create_window(self, config):
        wm = WindowManager(config)
        win = wm.create_window("Test", 10, 10, 200, 150)
        assert win.title == "Test"
        assert win.window_id == 1
        assert wm.window_count == 1

    def test_destroy_window(self, config):
        wm = WindowManager(config)
        win = wm.create_window("Test")
        wm.destroy_window(win.window_id)
        assert wm.window_count == 0

    def test_destroy_nonexistent(self, config):
        wm = WindowManager(config)
        with pytest.raises(Exception):
            wm.destroy_window(999)

    def test_focus(self, config):
        wm = WindowManager(config)
        w1 = wm.create_window("A")
        w2 = wm.create_window("B")
        wm.focus_window(w1.window_id)
        assert wm.get_focused().window_id == w1.window_id

    def test_move(self, config):
        wm = WindowManager(config)
        win = wm.create_window("Test", 10, 10)
        wm.move_window(win.window_id, 50, 50)
        assert win.rect.x == 50

    def test_resize(self, config):
        wm = WindowManager(config)
        win = wm.create_window("Test")
        wm.resize_window(win.window_id, 300, 200)
        assert win.rect.width == 300

    def test_maximize(self, config):
        wm = WindowManager(config)
        win = wm.create_window("Test")
        wm.maximize_window(win.window_id)
        assert win.state == WindowState.MAXIMIZED

    def test_minimize(self, config):
        wm = WindowManager(config)
        win = wm.create_window("Test")
        wm.minimize_window(win.window_id)
        assert win.state == WindowState.MINIMIZED
        assert not win.visible

    def test_restore(self, config):
        wm = WindowManager(config)
        win = wm.create_window("Test")
        wm.minimize_window(win.window_id)
        wm.restore_window(win.window_id)
        assert win.state == WindowState.NORMAL
        assert win.visible

    def test_window_at(self, config):
        wm = WindowManager(config)
        wm.create_window("Test", 10, 10, 100, 100)
        assert wm.window_at(50, 50) is not None
        assert wm.window_at(300, 300) is None

    def test_tiling_mode(self):
        config = FizzWindowConfig(width=320, height=240, mode="tiling")
        wm = WindowManager(config)
        wm.create_window("A")
        wm.create_window("B")
        wins = wm.list_windows()
        assert wins[0].rect.width > 0
        assert wins[1].rect.width > 0

    def test_list_windows_sorted(self, config):
        wm = WindowManager(config)
        wm.create_window("A")
        wm.create_window("B")
        wm.create_window("C")
        wins = wm.list_windows()
        assert len(wins) == 3

class TestEventDispatcher:
    def test_dispatch(self):
        ed = EventDispatcher()
        received = []
        ed.register(EventKind.KEY_DOWN, lambda e: received.append(e))
        ed.dispatch(InputEvent(kind=EventKind.KEY_DOWN, key="a"))
        assert len(received) == 1
        assert ed.event_count == 1

    def test_no_handler(self):
        ed = EventDispatcher()
        ed.dispatch(InputEvent(kind=EventKind.MOUSE_MOVE))
        assert ed.event_count == 1

class TestWidgetFactory:
    def test_button(self):
        w = WidgetFactory.button("Click", 10, 20)
        assert w.widget_type == WidgetType.BUTTON
        assert w.text == "Click"

    def test_label(self):
        w = WidgetFactory.label("Hello")
        assert w.widget_type == WidgetType.LABEL

    def test_text_input(self):
        w = WidgetFactory.text_input()
        assert w.widget_type == WidgetType.TEXT_INPUT

    def test_checkbox(self):
        w = WidgetFactory.checkbox("Enable", True)
        assert w.value is True

    def test_dropdown(self):
        w = WidgetFactory.dropdown(["A", "B", "C"])
        assert w.value == "A"

    def test_list_view(self):
        w = WidgetFactory.list_view(["Item1", "Item2"])
        assert w.widget_type == WidgetType.LIST_VIEW

    def test_progress_bar(self):
        w = WidgetFactory.progress_bar(0.5)
        assert w.value == 0.5

    def test_progress_bar_clamp(self):
        w = WidgetFactory.progress_bar(1.5)
        assert w.value == 1.0

    def test_canvas(self):
        w = WidgetFactory.canvas(width=400, height=300)
        assert w.rect.width == 400

    def test_panel(self):
        w = WidgetFactory.panel(layout=LayoutType.HBOX)
        assert w.layout == LayoutType.HBOX

class TestLayoutEngine:
    def test_hbox(self):
        le = LayoutEngine()
        parent = Widget(rect=Rect(0, 0, 400, 100), layout=LayoutType.HBOX)
        parent.children = [
            Widget(rect=Rect(0, 0, 50, 30)),
            Widget(rect=Rect(0, 0, 50, 30)),
        ]
        le.layout(parent)
        assert parent.children[0].rect.x < parent.children[1].rect.x

    def test_vbox(self):
        le = LayoutEngine()
        parent = Widget(rect=Rect(0, 0, 200, 400), layout=LayoutType.VBOX)
        parent.children = [
            Widget(rect=Rect(0, 0, 100, 30)),
            Widget(rect=Rect(0, 0, 100, 30)),
        ]
        le.layout(parent)
        assert parent.children[0].rect.y < parent.children[1].rect.y

    def test_grid(self):
        le = LayoutEngine()
        parent = Widget(rect=Rect(0, 0, 300, 300), layout=LayoutType.GRID,
                        style={"columns": 2})
        parent.children = [Widget(rect=Rect(0, 0, 50, 30)) for _ in range(4)]
        le.layout(parent)
        # 4 items in 2 columns
        assert parent.children[0].rect.x != parent.children[1].rect.x

class TestFontRenderer:
    def test_get_glyph(self):
        fr = FontRenderer()
        g = fr.get_glyph("A")
        assert g.character == "A"
        assert g.width == 8

    def test_cache(self):
        fr = FontRenderer()
        fr.get_glyph("A")
        fr.get_glyph("A")
        assert fr.cache_size == 1
        assert fr.hit_rate == 50.0

    def test_measure_text(self):
        fr = FontRenderer()
        w, h = fr.measure_text("Hello")
        assert w == 40  # 5 * 8

class TestThemeEngine:
    def test_list_themes(self):
        te = ThemeEngine()
        assert "enterprise-dark" in te.list_themes()
        assert "enterprise-light" in te.list_themes()

    def test_get_theme(self):
        te = ThemeEngine()
        t = te.get_theme("enterprise-dark")
        assert t.name == "Enterprise Dark"

    def test_get_nonexistent(self):
        te = ThemeEngine()
        with pytest.raises(Exception):
            te.get_theme("nope")

    def test_set_active(self):
        te = ThemeEngine()
        te.set_active("enterprise-light")
        assert te.get_active().name == "Enterprise Light"

class TestClipboardManager:
    def test_copy_paste(self):
        cb = ClipboardManager()
        cb.copy("Hello")
        assert cb.paste() == "Hello"
        assert cb.has_content

    def test_clear(self):
        cb = ClipboardManager()
        cb.copy("data")
        cb.clear()
        assert not cb.has_content

    def test_op_count(self):
        cb = ClipboardManager()
        cb.copy("a")
        cb.paste()
        assert cb.operation_count == 2

class TestMultiMonitorManager:
    def test_single(self):
        mm = MultiMonitorManager(FizzWindowConfig(monitors=1))
        assert len(mm.list_monitors()) == 1
        assert mm.get_primary().primary

    def test_multi(self):
        mm = MultiMonitorManager(FizzWindowConfig(monitors=3, width=1920))
        assert len(mm.list_monitors()) == 3
        assert mm.total_width == 5760

    def test_get_monitor(self):
        mm = MultiMonitorManager(FizzWindowConfig(monitors=2))
        assert mm.get_monitor(0) is not None
        assert mm.get_monitor(5) is None

class TestFizzTerm:
    def test_launch(self):
        wm = WindowManager(FizzWindowConfig(width=320, height=240))
        term = FizzTerm(wm)
        win = term.launch()
        assert "FizzTerm" in win.title

    def test_execute_fizzbuzz(self):
        wm = WindowManager(FizzWindowConfig(width=320, height=240))
        term = FizzTerm(wm)
        term.launch()
        assert term.execute("fizzbuzz 15") == "FizzBuzz"
        assert term.execute("fizzbuzz 9") == "Fizz"

    def test_execute_help(self):
        wm = WindowManager(FizzWindowConfig(width=320, height=240))
        term = FizzTerm(wm)
        term.launch()
        output = term.execute("help")
        assert "help" in output

class TestFizzView:
    def test_launch(self):
        wm = WindowManager(FizzWindowConfig(width=320, height=240))
        fv = FizzView(wm)
        win = fv.launch("/test.ppm")
        assert "FizzView" in win.title

    def test_zoom(self):
        wm = WindowManager(FizzWindowConfig(width=320, height=240))
        fv = FizzView(wm)
        fv.launch()
        z = fv.zoom_in()
        assert z > 1.0
        z = fv.zoom_out()
        z = fv.zoom_out()
        assert z < 1.0

class TestFizzMonitor:
    def test_launch(self):
        wm = WindowManager(FizzWindowConfig(width=320, height=240))
        fm = FizzMonitor(wm)
        win = fm.launch()
        assert "FizzMonitor" in win.title

    def test_metrics(self):
        wm = WindowManager(FizzWindowConfig(width=320, height=240))
        fm = FizzMonitor(wm)
        fm.launch()
        m = fm.get_metrics()
        assert m["modules_loaded"] == 140
        assert m["operator_stress_pct"] == 94.7

class TestDisplayServer:
    def test_create_and_destroy_window(self, subsystem):
        ds, _, _ = subsystem
        win = ds.create_window("Test")
        assert ds._wm.window_count == 1
        ds.destroy_window(win.window_id)
        assert ds._wm.window_count == 0

    def test_render_frame(self, subsystem):
        ds, _, _ = subsystem
        ds.create_window("Test")
        ds.render_frame()
        assert ds.get_metrics().total_frames >= 1

    def test_capture_screen(self, subsystem):
        ds, _, _ = subsystem
        ppm = ds.capture_screen()
        assert ppm.startswith(b"P6\n")
        assert ds.get_metrics().captures_taken == 1

    def test_launch_app(self, subsystem):
        ds, _, _ = subsystem
        win = ds.launch_app("fizzterm")
        assert win is not None
        assert "FizzTerm" in win.title

    def test_uptime(self, subsystem):
        ds, _, _ = subsystem
        assert ds.uptime > 0
        assert ds.is_running

class TestFizzWindowMiddleware:
    def test_get_name(self, subsystem):
        _, _, mw = subsystem
        assert mw.get_name() == "fizzwindow"

    def test_get_priority(self, subsystem):
        _, _, mw = subsystem
        assert mw.get_priority() == MIDDLEWARE_PRIORITY

    def test_process(self, subsystem):
        _, _, mw = subsystem
        ctx = MagicMock()
        ctx.metadata = {}
        mw.process(ctx, None)
        assert ctx.metadata["fizzwindow_version"] == FIZZWINDOW_VERSION

    def test_render_dashboard(self, subsystem):
        _, _, mw = subsystem
        assert "FizzWindow" in mw.render_dashboard()

    def test_render_status(self, subsystem):
        _, _, mw = subsystem
        assert "UP" in mw.render_status()

    def test_render_capture(self, subsystem):
        _, _, mw = subsystem
        assert "captured" in mw.render_capture().lower()

    def test_render_app(self, subsystem):
        _, _, mw = subsystem
        output = mw.render_app("fizzterm")
        assert "FizzTerm" in output

    def test_render_app_unknown(self, subsystem):
        _, _, mw = subsystem
        output = mw.render_app("nonexistent")
        assert "Unknown" in output

class TestCreateSubsystem:
    def test_returns_tuple(self):
        result = create_fizzwindow_subsystem(width=100, height=100)
        assert len(result) == 3

    def test_started(self):
        ds, _, _ = create_fizzwindow_subsystem(width=100, height=100)
        assert ds.is_running

    def test_custom_theme(self):
        ds, _, _ = create_fizzwindow_subsystem(width=100, height=100, theme="enterprise-light")
        assert ds._themes.get_active().name == "Enterprise Light"

class TestConstants:
    def test_version(self):
        assert FIZZWINDOW_VERSION == "1.0.0"

    def test_priority(self):
        assert MIDDLEWARE_PRIORITY == 126
