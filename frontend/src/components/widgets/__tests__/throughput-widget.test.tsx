import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

beforeAll(() => {
  if (!SVGElement.prototype.getTotalLength) {
    SVGElement.prototype.getTotalLength = () => 100;
  }
});

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

const mockGetMetricsSummary = vi.fn().mockResolvedValue({
  totalEvaluations: 1284700,
  evaluationsPerSecond: 12847,
  cacheHitRate: 0.974,
  averageLatencyMs: 4.23,
  uptimeSeconds: 345600,
  throughputHistory: [10, 14, 12, 18, 15, 20, 17, 19],
});

vi.mock("@/lib/data-providers", () => ({
  useDataProvider: () => ({
    getMetricsSummary: mockGetMetricsSummary,
  }),
}));

import { ThroughputWidget } from "../throughput-widget";

describe("ThroughputWidget", () => {
  it("renders skeleton loading state initially", () => {
    mockGetMetricsSummary.mockReturnValueOnce(new Promise(() => {}));
    const { container } = render(<ThroughputWidget />);
    const skeletons = container.querySelectorAll('[role="status"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("renders animated throughput number after data loads", async () => {
    render(<ThroughputWidget />);
    await waitFor(() => {
      expect(screen.getByText("12847")).toBeInTheDocument();
    });
  });

  it("renders eval/s unit label", async () => {
    render(<ThroughputWidget />);
    await waitFor(() => {
      expect(screen.getByText("eval/s")).toBeInTheDocument();
    });
  });

  it("renders average latency metric", async () => {
    render(<ThroughputWidget />);
    await waitFor(() => {
      expect(screen.getByText("4.23")).toBeInTheDocument();
    });
  });

  it("renders sparkline SVG after data loads", async () => {
    const { container } = render(<ThroughputWidget />);
    await waitFor(() => {
      expect(container.querySelector("svg")).toBeInTheDocument();
    });
  });

  it("renders uptime information", async () => {
    render(<ThroughputWidget />);
    await waitFor(() => {
      expect(screen.getByText(/Uptime/)).toBeInTheDocument();
    });
  });
});
