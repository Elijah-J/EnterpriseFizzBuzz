import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useKonami } from "../use-konami";

const KONAMI_CODES = [
  "ArrowUp", "ArrowUp", "ArrowDown", "ArrowDown",
  "ArrowLeft", "ArrowRight", "ArrowLeft", "ArrowRight",
  "KeyB", "KeyA",
];

function fireKonamiSequence() {
  for (const code of KONAMI_CODES) {
    document.dispatchEvent(new KeyboardEvent("keydown", { code }));
  }
}

describe("useKonami", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    localStorage.clear();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("returns false initially when sequence has not been entered", () => {
    const { result } = renderHook(() => useKonami());
    expect(result.current.activated).toBe(false);
  });

  it("returns true after the complete Konami code sequence", () => {
    const { result } = renderHook(() => useKonami());
    act(() => {
      fireKonamiSequence();
    });
    expect(result.current.activated).toBe(true);
  });

  it("persists activation state in localStorage", () => {
    const { result } = renderHook(() => useKonami());
    act(() => {
      fireKonamiSequence();
    });
    expect(localStorage.getItem("efp-konami-activated")).toBe("true");
  });

  it("reads persisted state from localStorage on mount", () => {
    localStorage.setItem("efp-konami-activated", "true");
    const { result } = renderHook(() => useKonami());
    expect(result.current.activated).toBe(true);
  });

  it("resets on wrong key in the sequence", () => {
    const { result } = renderHook(() => useKonami());
    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { code: "ArrowUp" }));
      document.dispatchEvent(new KeyboardEvent("keydown", { code: "ArrowUp" }));
      document.dispatchEvent(new KeyboardEvent("keydown", { code: "KeyX" })); // wrong key
    });
    expect(result.current.activated).toBe(false);
  });

  it("resets activation state when reset() is called", () => {
    localStorage.setItem("efp-konami-activated", "true");
    const { result } = renderHook(() => useKonami());
    act(() => {
      result.current.reset();
    });
    expect(result.current.activated).toBe(false);
    expect(localStorage.getItem("efp-konami-activated")).toBeNull();
  });

  it("provides a reset function", () => {
    const { result } = renderHook(() => useKonami());
    expect(typeof result.current.reset).toBe("function");
  });
});
