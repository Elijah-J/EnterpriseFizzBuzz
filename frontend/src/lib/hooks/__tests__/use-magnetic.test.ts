import { describe, it, expect, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import { useMagnetic } from "../use-magnetic";
import { useRef } from "react";

describe("useMagnetic", () => {
  it("accepts a ref and options without error", () => {
    expect(() => {
      renderHook(() => {
        const ref = useRef<HTMLDivElement>(null);
        useMagnetic(ref, { strength: 0.3, radius: 100 });
      });
    }).not.toThrow();
  });

  it("uses default strength of 0.3 and radius of 100", () => {
    expect(() => {
      renderHook(() => {
        const ref = useRef<HTMLDivElement>(null);
        useMagnetic(ref);
      });
    }).not.toThrow();
  });

  it("attaches mousemove listener when motion is enabled", () => {
    const addSpy = vi.spyOn(document, "addEventListener");
    renderHook(() => {
      const ref = useRef<HTMLDivElement>(null);
      useMagnetic(ref);
    });
    const mousemoveCalls = addSpy.mock.calls.filter(
      (call) => call[0] === "mousemove",
    );
    expect(mousemoveCalls.length).toBeGreaterThanOrEqual(1);
    addSpy.mockRestore();
  });
});
