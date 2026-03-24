import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { DataProvider } from "@/lib/data-providers";

vi.mock("@/lib/hooks/use-reduced-motion", () => ({
  useReducedMotion: () => true,
}));

vi.mock("@/lib/hooks/use-intersection-observer", () => ({
  useIntersectionObserver: () => ({ ref: { current: null }, isVisible: true }),
}));

import { HealthMatrixWidget } from "../health-matrix-widget";

function renderWidget() {
  return render(
    <DataProvider>
      <HealthMatrixWidget />
    </DataProvider>,
  );
}

describe("HealthMatrixWidget", () => {
  it("renders skeleton loading state initially", () => {
    const { container } = renderWidget();
    const skeletons = container.querySelectorAll('[role="status"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("renders subsystem names from real provider after data loads", async () => {
    renderWidget();
    // SimulationProvider returns all SUBSYSTEM_NAMES — check for one that's always present
    await waitFor(() => {
      expect(screen.getByText("MESI Cache Coherence")).toBeInTheDocument();
    });
  });

  it("renders status dots for each subsystem", async () => {
    const { container } = renderWidget();
    await waitFor(() => {
      const dots = container.querySelectorAll("span[class*='rounded-full']");
      expect(dots.length).toBeGreaterThanOrEqual(1);
    });
  });

  it("renders Blockchain Ledger subsystem from real provider", async () => {
    renderWidget();
    await waitFor(() => {
      expect(screen.getByText("Blockchain Ledger")).toBeInTheDocument();
    });
  });

  it("displays subsystem count summary", async () => {
    renderWidget();
    await waitFor(() => {
      expect(screen.getByText(/subsystems/)).toBeInTheDocument();
    });
  });

  it("displays up count from real provider", async () => {
    renderWidget();
    await waitFor(() => {
      expect(screen.getByText(/up/)).toBeInTheDocument();
    });
  });
});
