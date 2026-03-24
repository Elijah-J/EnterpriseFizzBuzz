import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { DataProvider } from "@/lib/data-providers";

vi.mock("@/lib/hooks/use-reduced-motion", () => ({
  useReducedMotion: () => true,
}));

vi.mock("@/lib/hooks/use-animated-number", () => ({
  useAnimatedNumber: (value: number, opts?: { decimals?: number; format?: string }) => {
    const d = opts?.decimals ?? 0;
    return value.toFixed(d);
  },
}));

import { CostWidget } from "../cost-widget";

function renderWidget() {
  return render(
    <DataProvider>
      <CostWidget />
    </DataProvider>,
  );
}

describe("CostWidget", () => {
  it("renders skeleton loading state initially", () => {
    const { container } = renderWidget();
    const skeletons = container.querySelectorAll('[role="status"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("renders current period cost label after data loads", async () => {
    renderWidget();
    await waitFor(() => {
      expect(screen.getByText("Current Period Expenditure")).toBeInTheDocument();
    });
  });

  it("renders FizzBuck currency symbol from real provider", async () => {
    renderWidget();
    await waitFor(() => {
      const fbLabels = screen.getAllByText(/FB\$/);
      expect(fbLabels.length).toBeGreaterThan(0);
    });
  });

  it("renders previous period label from real provider", async () => {
    renderWidget();
    await waitFor(() => {
      expect(screen.getByText("Previous Period")).toBeInTheDocument();
    });
  });

  it("renders spend trend label from real provider", async () => {
    renderWidget();
    await waitFor(() => {
      expect(screen.getByText(/Spend trend/)).toBeInTheDocument();
    });
  });

  it("renders cost per evaluation label from real provider", async () => {
    renderWidget();
    await waitFor(() => {
      expect(screen.getByText("Cost per Evaluation")).toBeInTheDocument();
    });
  });
});
