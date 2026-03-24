import { describe, it, expect, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import { usePress } from "../use-press";
import { useRef } from "react";

describe("usePress", () => {
  it("accepts a ref without error", () => {
    expect(() => {
      renderHook(() => {
        const ref = useRef<HTMLButtonElement>(null);
        usePress(ref);
      });
    }).not.toThrow();
  });

  it("attaches mouse and touch listeners to the element when motion is enabled", () => {
    const el = document.createElement("button");
    const addSpy = vi.spyOn(el, "addEventListener");

    renderHook(() => {
      const ref = { current: el } as React.RefObject<HTMLButtonElement>;
      usePress(ref);
    });

    const eventNames = addSpy.mock.calls.map((c) => c[0]);
    expect(eventNames).toContain("mousedown");
    expect(eventNames).toContain("mouseup");
    expect(eventNames).toContain("mouseleave");
    expect(eventNames).toContain("touchstart");
    expect(eventNames).toContain("touchend");
    expect(eventNames).toContain("touchcancel");
    addSpy.mockRestore();
  });

  it("cleans up listeners on unmount", () => {
    const el = document.createElement("button");
    const removeSpy = vi.spyOn(el, "removeEventListener");

    const { unmount } = renderHook(() => {
      const ref = { current: el } as React.RefObject<HTMLButtonElement>;
      usePress(ref);
    });

    unmount();
    const eventNames = removeSpy.mock.calls.map((c) => c[0]);
    expect(eventNames).toContain("mousedown");
    expect(eventNames).toContain("mouseup");
    removeSpy.mockRestore();
  });
});
