import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import { LiveIndicator } from "../live-indicator";

describe("LiveIndicator", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-03-24T12:00:00Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders 'Connecting...' when lastUpdated is null", () => {
    render(<LiveIndicator lastUpdated={null} />);
    expect(screen.getByText("Connecting...")).toBeInTheDocument();
  });

  it("renders 'Live' text when data is fresh", () => {
    const now = Date.now();
    render(<LiveIndicator lastUpdated={now} />);
    act(() => { vi.advanceTimersByTime(0); });
    expect(screen.getByText(/Live/)).toBeInTheDocument();
  });

  it("renders 'just now' for recent timestamps", () => {
    const now = Date.now();
    render(<LiveIndicator lastUpdated={now - 2000} />);
    act(() => { vi.advanceTimersByTime(0); });
    expect(screen.getByText(/just now/)).toBeInTheDocument();
  });

  it("renders seconds-ago format for timestamps under 60 seconds", () => {
    const now = Date.now();
    render(<LiveIndicator lastUpdated={now - 30000} />);
    act(() => { vi.advanceTimersByTime(0); });
    expect(screen.getByText(/30s ago/)).toBeInTheDocument();
  });

  it("renders amber dot when data is not stale", () => {
    const now = Date.now();
    const { container } = render(<LiveIndicator lastUpdated={now} />);
    const dot = container.querySelector(".bg-accent");
    expect(dot).toBeInTheDocument();
  });

  it("renders muted dot when data is stale", () => {
    const now = Date.now();
    const { container } = render(<LiveIndicator lastUpdated={now} isStale />);
    const dot = container.querySelector(".bg-text-muted");
    expect(dot).toBeInTheDocument();
  });

  it("shows 'Data stale' text when isStale is true", () => {
    const now = Date.now();
    render(<LiveIndicator lastUpdated={now - 5000} isStale />);
    act(() => { vi.advanceTimersByTime(0); });
    expect(screen.getByText(/Data stale/)).toBeInTheDocument();
  });

  it("updates elapsed time every second", () => {
    const now = Date.now();
    render(<LiveIndicator lastUpdated={now} />);
    act(() => { vi.advanceTimersByTime(0); });
    expect(screen.getByText(/just now/)).toBeInTheDocument();
    act(() => { vi.advanceTimersByTime(10000); });
    expect(screen.getByText(/10s ago/)).toBeInTheDocument();
  });
});
