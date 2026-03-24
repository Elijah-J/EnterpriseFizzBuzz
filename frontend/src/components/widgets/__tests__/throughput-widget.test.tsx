import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { DataProvider } from "@/lib/data-providers";

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

import { ThroughputWidget } from "../throughput-widget";

function renderWidget() {
  return render(
    <DataProvider>
      <ThroughputWidget />
    </DataProvider>,
  );
}

describe("ThroughputWidget", () => {
  it("renders skeleton loading state initially", () => {
    const { container } = renderWidget();
    const skeletons = container.querySelectorAll('[role="status"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("renders throughput number after data loads", async () => {
    renderWidget();
    await waitFor(() => {
      expect(screen.getByText("eval/s")).toBeInTheDocument();
    });
  });

  it("renders eval/s unit label", async () => {
    renderWidget();
    await waitFor(() => {
      expect(screen.getByText("eval/s")).toBeInTheDocument();
    });
  });

  it("renders average latency metric", async () => {
    renderWidget();
    await waitFor(() => {
      expect(screen.getByText("Avg Latency")).toBeInTheDocument();
    });
  });

  it("renders sparkline SVG after data loads", async () => {
    const { container } = renderWidget();
    await waitFor(() => {
      expect(container.querySelector("svg")).toBeInTheDocument();
    });
  });

  it("renders uptime information", async () => {
    renderWidget();
    await waitFor(() => {
      expect(screen.getByText(/Uptime/)).toBeInTheDocument();
    });
  });

  it("renders cache hit rate from real provider", async () => {
    renderWidget();
    await waitFor(() => {
      expect(screen.getByText("Cache Hit Rate")).toBeInTheDocument();
    });
  });

  it("renders total evaluations from real provider", async () => {
    renderWidget();
    await waitFor(() => {
      expect(screen.getByText("Total Evaluations")).toBeInTheDocument();
    });
  });
});
