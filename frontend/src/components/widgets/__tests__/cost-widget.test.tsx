import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

vi.mock("@/lib/hooks/use-reduced-motion", () => ({
  useReducedMotion: () => true,
}));

vi.mock("@/lib/hooks/use-animated-number", () => ({
  useAnimatedNumber: (value: number, opts?: { decimals?: number; format?: string }) => {
    const d = opts?.decimals ?? 0;
    return value.toFixed(d);
  },
}));

vi.mock("@/lib/data-providers", () => ({
  useDataProvider: () => ({
    getCostSummary: vi.fn().mockResolvedValue({
      currentPeriodCost: 1247.83,
      previousPeriodCost: 1180.50,
      costPerEvaluation: 0.0000097,
      trend: "up" as const,
      currency: "FizzBuck",
    }),
  }),
}));

import { CostWidget } from "../cost-widget";

describe("CostWidget", () => {
  it("renders skeleton loading state initially", () => {
    const { container } = render(<CostWidget />);
    const skeletons = container.querySelectorAll('[role="status"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("renders current period cost after data loads", async () => {
    render(<CostWidget />);
    await waitFor(() => {
      expect(screen.getByText("1247.83")).toBeInTheDocument();
    });
  });

  it("renders FizzBuck currency symbol", async () => {
    render(<CostWidget />);
    await waitFor(() => {
      const fbLabels = screen.getAllByText(/FB\$/);
      expect(fbLabels.length).toBeGreaterThan(0);
    });
  });

  it("renders previous period cost", async () => {
    render(<CostWidget />);
    await waitFor(() => {
      expect(screen.getByText("1180.50")).toBeInTheDocument();
    });
  });

  it("renders spend trend label", async () => {
    render(<CostWidget />);
    await waitFor(() => {
      expect(screen.getByText(/Spend trend/)).toBeInTheDocument();
    });
  });
});
