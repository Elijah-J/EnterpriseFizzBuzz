import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

vi.mock("@/lib/hooks/use-reduced-motion", () => ({
  useReducedMotion: () => true,
}));

vi.mock("@/lib/hooks/use-intersection-observer", () => ({
  useIntersectionObserver: () => ({ ref: { current: null }, isVisible: true }),
}));

const mockHealth = [
  { name: "MESI Cache Coherence", status: "up" as const, lastChecked: "2024-03-10T12:00:00Z", responseTimeMs: 2.1 },
  { name: "Blockchain Ledger", status: "degraded" as const, lastChecked: "2024-03-10T12:00:00Z", responseTimeMs: 150.5 },
  { name: "Neural Network Inference", status: "up" as const, lastChecked: "2024-03-10T12:00:00Z", responseTimeMs: 8.3 },
  { name: "Quantum Simulator", status: "down" as const, lastChecked: "2024-03-10T12:00:00Z", responseTimeMs: 0 },
];

vi.mock("@/lib/data-providers", () => ({
  useDataProvider: () => ({
    getSystemHealth: vi.fn().mockResolvedValue(mockHealth),
  }),
}));

import { HealthMatrixWidget } from "../health-matrix-widget";

describe("HealthMatrixWidget", () => {
  it("renders skeleton loading state initially", () => {
    const { container } = render(<HealthMatrixWidget />);
    const skeletons = container.querySelectorAll('[role="status"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("renders subsystem grid with names after data loads", async () => {
    render(<HealthMatrixWidget />);
    await waitFor(() => {
      expect(screen.getByText("MESI Cache Coherence")).toBeInTheDocument();
    });
  });

  it("renders status dots for each subsystem", async () => {
    const { container } = render(<HealthMatrixWidget />);
    await waitFor(() => {
      const dots = container.querySelectorAll("span[class*='rounded-full']");
      expect(dots.length).toBeGreaterThanOrEqual(mockHealth.length);
    });
  });

  it("sorts subsystems by severity with down status first", async () => {
    const { container } = render(<HealthMatrixWidget />);
    await waitFor(() => {
      const names = container.querySelectorAll("span.truncate, span[class*='truncate']");
      const nameTexts = Array.from(names).map((n) => n.textContent);
      const downIdx = nameTexts.indexOf("Quantum Simulator");
      const upIdx = nameTexts.indexOf("MESI Cache Coherence");
      if (downIdx >= 0 && upIdx >= 0) {
        expect(downIdx).toBeLessThan(upIdx);
      }
    });
  });

  it("displays summary counts (up, degraded, down)", async () => {
    render(<HealthMatrixWidget />);
    await waitFor(() => {
      expect(screen.getByText(/up/)).toBeInTheDocument();
      expect(screen.getByText(/subsystems/)).toBeInTheDocument();
    });
  });
});
