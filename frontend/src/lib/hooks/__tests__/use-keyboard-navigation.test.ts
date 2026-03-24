import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useKeyboardNavigation } from "../use-keyboard-navigation";

// Mock next/navigation
vi.mock("next/navigation", () => ({
  usePathname: vi.fn(() => "/"),
}));

describe("useKeyboardNavigation", () => {
  const onOpenSearch = vi.fn();
  const onToggleOverlay = vi.fn();
  const navigate = vi.fn();

  beforeEach(() => {
    vi.useFakeTimers();
    onOpenSearch.mockClear();
    onToggleOverlay.mockClear();
    navigate.mockClear();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  const renderNav = () =>
    renderHook(() =>
      useKeyboardNavigation({ onOpenSearch, onToggleOverlay, navigate }),
    );

  it("calls onOpenSearch when / key is pressed", () => {
    renderNav();
    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "/" }));
    });
    expect(onOpenSearch).toHaveBeenCalledTimes(1);
  });

  it("calls onToggleOverlay when ? key is pressed", () => {
    renderNav();
    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "?" }));
    });
    expect(onToggleOverlay).toHaveBeenCalledTimes(1);
  });

  it("calls navigate for ] key (next page)", () => {
    renderNav();
    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "]" }));
    });
    expect(navigate).toHaveBeenCalledWith("/evaluate");
  });

  it("calls navigate for [ key (previous page)", () => {
    renderNav();
    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "[" }));
    });
    // From "/" (index 0), going back wraps to last page
    expect(navigate).toHaveBeenCalledWith("/archaeology");
  });

  it("scrolls to top on g g key sequence", () => {
    const scrollTo = vi.fn();
    window.scrollTo = scrollTo;
    renderNav();
    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "g" }));
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "g" }));
    });
    expect(scrollTo).toHaveBeenCalledWith({ top: 0, behavior: "smooth" });
  });

  it("scrolls to bottom on G key", () => {
    const scrollTo = vi.fn();
    window.scrollTo = scrollTo;
    renderNav();
    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "G" }));
    });
    expect(scrollTo).toHaveBeenCalledWith({
      top: document.documentElement.scrollHeight,
      behavior: "smooth",
    });
  });

  it("does not fire shortcuts when input element is focused", () => {
    const input = document.createElement("input");
    document.body.appendChild(input);
    input.focus();
    renderNav();
    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "/" }));
    });
    expect(onOpenSearch).not.toHaveBeenCalled();
    document.body.removeChild(input);
  });

  it("blurs active element on Escape key", () => {
    const button = document.createElement("button");
    document.body.appendChild(button);
    button.focus();
    renderNav();
    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    });
    expect(document.activeElement).toBe(document.body);
    document.body.removeChild(button);
  });
});
