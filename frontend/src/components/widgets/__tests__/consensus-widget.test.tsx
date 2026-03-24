import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

vi.mock("@/lib/hooks/use-reduced-motion", () => ({
  useReducedMotion: () => true,
}));

vi.mock("@/lib/hooks/use-animated-number", () => ({
  useAnimatedNumber: (value: number) => String(value),
}));

vi.mock("@/lib/data-providers", () => ({
  useDataProvider: () => ({
    getConsensusStatus: vi.fn().mockResolvedValue({
      leaderNode: "fizz-node-alpha-7f3a",
      ballotNumber: 42,
      nodesAcknowledged: 4,
      clusterSize: 5,
      consensusAchieved: true,
    }),
  }),
}));

import { ConsensusWidget } from "../consensus-widget";

describe("ConsensusWidget", () => {
  it("renders skeleton loading state initially", () => {
    const { container } = render(<ConsensusWidget />);
    const skeletons = container.querySelectorAll('[role="status"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("renders leader node identifier after data loads", async () => {
    render(<ConsensusWidget />);
    await waitFor(() => {
      expect(screen.getByText("fizz-node-alpha-7f3a")).toBeInTheDocument();
    });
  });

  it("renders consensus achieved badge", async () => {
    render(<ConsensusWidget />);
    await waitFor(() => {
      expect(screen.getByText("CONSENSUS ACHIEVED")).toBeInTheDocument();
    });
  });

  it("renders ballot number", async () => {
    render(<ConsensusWidget />);
    await waitFor(() => {
      expect(screen.getByText("42")).toBeInTheDocument();
    });
  });

  it("renders node visualization dots matching cluster size", async () => {
    const { container } = render(<ConsensusWidget />);
    await waitFor(() => {
      const dots = container.querySelectorAll("div[class*='rounded-full'][class*='w-3']");
      expect(dots.length).toBe(5);
    });
  });

  it("shows acknowledged nodes with green color", async () => {
    const { container } = render(<ConsensusWidget />);
    await waitFor(() => {
      const greenDots = container.querySelectorAll("div[class*='bg-fizz-500']");
      expect(greenDots.length).toBe(4);
    });
  });
});
