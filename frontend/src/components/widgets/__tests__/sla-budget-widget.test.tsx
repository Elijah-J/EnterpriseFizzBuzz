import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { DataProvider } from "@/lib/data-providers";

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

import { SLABudgetWidget } from "../sla-budget-widget";

function renderWidget() {
  return render(
    <DataProvider>
      <SLABudgetWidget />
    </DataProvider>,
  );
}

describe("SLABudgetWidget", () => {
  it("renders skeleton loading state initially", () => {
    const { container } = renderWidget();
    const skeletons = container.querySelectorAll('[role="status"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("renders circular gauge after data loads", async () => {
    const { container } = renderWidget();
    await waitFor(() => {
      expect(container.querySelector("svg")).toBeInTheDocument();
    });
  });

  it("displays error budget gauge label", async () => {
    const { container } = renderWidget();
    await waitFor(() => {
      // The circular gauge SVG has an aria-label with error budget info
      const gauge = container.querySelector("svg[aria-label*='Error budget gauge']");
      expect(gauge).toBeInTheDocument();
    });
  });

  it("renders availability label from real provider", async () => {
    renderWidget();
    await waitFor(() => {
      expect(screen.getByText("Availability")).toBeInTheDocument();
    });
  });

  it("renders P99 latency label from real provider", async () => {
    renderWidget();
    await waitFor(() => {
      expect(screen.getByText("P99 Latency")).toBeInTheDocument();
    });
  });

  it("renders correctness label from real provider", async () => {
    renderWidget();
    await waitFor(() => {
      expect(screen.getByText("Correctness")).toBeInTheDocument();
    });
  });

  it("renders 100% correctness from real provider", async () => {
    renderWidget();
    // SimulationProvider always returns correctnessPercent: 100
    await waitFor(() => {
      expect(screen.getByText("100.0%")).toBeInTheDocument();
    });
  });
});
