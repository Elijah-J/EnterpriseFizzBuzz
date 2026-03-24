import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { DataProvider } from "@/lib/data-providers";

vi.mock("@/lib/hooks/use-reduced-motion", () => ({
  useReducedMotion: () => true,
}));

vi.mock("@/lib/hooks/use-animated-number", () => ({
  useAnimatedNumber: (value: number) => String(value),
}));

import { ConsensusWidget } from "../consensus-widget";

function renderWidget() {
  return render(
    <DataProvider>
      <ConsensusWidget />
    </DataProvider>,
  );
}

describe("ConsensusWidget", () => {
  it("renders skeleton loading state initially", () => {
    const { container } = renderWidget();
    const skeletons = container.querySelectorAll('[role="status"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("renders leader node identifier from real provider after data loads", async () => {
    renderWidget();
    // SimulationProvider returns one of the CLUSTER_NODES
    const clusterNodes = [
      "fizz-eval-us-east-1a",
      "fizz-eval-us-west-2b",
      "fizz-eval-eu-west-1c",
      "fizz-eval-ap-south-1a",
      "fizz-eval-eu-central-1b",
    ];
    await waitFor(() => {
      const found = clusterNodes.some((node) => screen.queryByText(node));
      expect(found).toBe(true);
    });
  });

  it("renders consensus badge from real provider", async () => {
    renderWidget();
    await waitFor(() => {
      const badge = screen.getByText((content) => {
        return content === "CONSENSUS ACHIEVED" || content === "ELECTION IN PROGRESS";
      });
      expect(badge).toBeInTheDocument();
    });
  });

  it("renders ballot number label", async () => {
    renderWidget();
    await waitFor(() => {
      expect(screen.getByText("Ballot #")).toBeInTheDocument();
    });
  });

  it("renders cluster consensus label", async () => {
    renderWidget();
    await waitFor(() => {
      expect(screen.getByText("Cluster Consensus")).toBeInTheDocument();
    });
  });

  it("renders node visualization dots matching cluster size", async () => {
    const { container } = renderWidget();
    await waitFor(() => {
      // SimulationProvider cluster has 5 nodes
      const dots = container.querySelectorAll("div[class*='rounded-full'][class*='w-3']");
      expect(dots.length).toBe(5);
    });
  });

  it("renders nodes ACK label from real provider", async () => {
    renderWidget();
    await waitFor(() => {
      expect(screen.getByText("Nodes ACK")).toBeInTheDocument();
    });
  });
});
