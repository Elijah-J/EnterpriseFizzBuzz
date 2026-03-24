import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

vi.mock("@/lib/hooks/use-reduced-motion", () => ({
  useReducedMotion: () => true,
}));

vi.mock("@/lib/hooks/use-animated-number", () => ({
  useAnimatedNumber: (value: number, opts?: { decimals?: number; format?: string }) => {
    const d = opts?.decimals ?? 0;
    if (opts?.format === "percent") return `${value.toFixed(d)}%`;
    return value.toFixed(d);
  },
}));

vi.mock("@/lib/data-providers", () => ({
  useDataProvider: () => ({
    getSLAStatus: vi.fn().mockResolvedValue({
      availabilityPercent: 99.97,
      errorBudgetRemaining: 0.82,
      latencyP99Ms: 4.2,
      correctnessPercent: 100,
      activeIncidents: 0,
      onCallEngineer: "Bob McFizzington",
    }),
  }),
}));

import { SLABudgetWidget } from "../sla-budget-widget";

describe("SLABudgetWidget", () => {
  it("renders skeleton loading state initially", () => {
    const { container } = render(<SLABudgetWidget />);
    const skeletons = container.querySelectorAll('[role="status"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("renders circular gauge after data loads", async () => {
    const { container } = render(<SLABudgetWidget />);
    await waitFor(() => {
      expect(container.querySelector("svg")).toBeInTheDocument();
    });
  });

  it("displays gauge percentage label", async () => {
    render(<SLABudgetWidget />);
    await waitFor(() => {
      expect(screen.getByText("82.0%")).toBeInTheDocument();
    });
  });

  it("renders availability metric", async () => {
    render(<SLABudgetWidget />);
    await waitFor(() => {
      expect(screen.getByText("99.97%")).toBeInTheDocument();
    });
  });

  it("renders P99 latency metric", async () => {
    render(<SLABudgetWidget />);
    await waitFor(() => {
      expect(screen.getByText("4.2")).toBeInTheDocument();
    });
  });
});
