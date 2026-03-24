import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

vi.mock("@/lib/hooks/use-reduced-motion", () => ({
  useReducedMotion: () => true,
}));

vi.mock("@/lib/hooks/use-animated-number", () => ({
  useAnimatedNumber: (value: number) => String(value),
}));

vi.mock("@/lib/hooks/use-intersection-observer", () => ({
  useIntersectionObserver: () => ({ ref: { current: null }, isVisible: true }),
}));

const mockSLA = {
  availabilityPercent: 99.95,
  errorBudgetRemaining: 0.78,
  latencyP99Ms: 5.1,
  correctnessPercent: 100,
  activeIncidents: 2,
  onCallEngineer: "Bob McFizzington",
};

vi.mock("@/lib/data-providers", () => ({
  useDataProvider: () => ({
    getSLAStatus: vi.fn().mockResolvedValue(mockSLA),
  }),
}));

import { IncidentsWidget } from "../incidents-widget";

describe("IncidentsWidget", () => {
  it("renders skeleton loading state initially", () => {
    const { container } = render(<IncidentsWidget />);
    const skeletons = container.querySelectorAll('[role="status"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("renders active incident count after data loads", async () => {
    render(<IncidentsWidget />);
    await waitFor(() => {
      expect(screen.getByText("2")).toBeInTheDocument();
    });
  });

  it("renders severity badge when incidents are active", async () => {
    render(<IncidentsWidget />);
    await waitFor(() => {
      expect(screen.getByText("SEV-3")).toBeInTheDocument();
    });
  });

  it("renders on-call engineer name", async () => {
    render(<IncidentsWidget />);
    await waitFor(() => {
      expect(screen.getByText("Bob McFizzington")).toBeInTheDocument();
    });
  });

  it("renders on-call initials avatar", async () => {
    render(<IncidentsWidget />);
    await waitFor(() => {
      expect(screen.getByText("BM")).toBeInTheDocument();
    });
  });
});
