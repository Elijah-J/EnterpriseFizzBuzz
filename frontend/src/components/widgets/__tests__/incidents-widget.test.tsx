import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { DataProvider } from "@/lib/data-providers";

vi.mock("@/lib/hooks/use-reduced-motion", () => ({
  useReducedMotion: () => true,
}));

vi.mock("@/lib/hooks/use-animated-number", () => ({
  useAnimatedNumber: (value: number) => String(value),
}));

vi.mock("@/lib/hooks/use-intersection-observer", () => ({
  useIntersectionObserver: () => ({ ref: { current: null }, isVisible: true }),
}));

import { IncidentsWidget } from "../incidents-widget";

function renderWidget() {
  return render(
    <DataProvider>
      <IncidentsWidget />
    </DataProvider>,
  );
}

describe("IncidentsWidget", () => {
  it("renders skeleton loading state initially", () => {
    const { container } = renderWidget();
    const skeletons = container.querySelectorAll('[role="status"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("renders active incidents label after data loads", async () => {
    renderWidget();
    await waitFor(() => {
      expect(screen.getByText("Active Incidents")).toBeInTheDocument();
    });
  });

  it("renders incident count as a number from real provider", async () => {
    renderWidget();
    await waitFor(() => {
      // SimulationProvider returns either 0 or 1 active incidents
      const zeroOrOne = screen.getByText((content, element) => {
        return element?.tagName !== "SCRIPT" && (content === "0" || content === "1");
      });
      expect(zeroOrOne).toBeInTheDocument();
    });
  });

  it("renders severity badge or all-clear from real provider", async () => {
    renderWidget();
    await waitFor(() => {
      // SimulationProvider: 0 incidents -> "ALL CLEAR", 1 incident -> "SEV-3"
      const badge = screen.getByText((content) => {
        return content === "SEV-3" || content === "ALL CLEAR";
      });
      expect(badge).toBeInTheDocument();
    });
  });

  it("renders on-call engineer from real provider roster", async () => {
    renderWidget();
    await waitFor(() => {
      expect(screen.getByText("On-Call Engineer")).toBeInTheDocument();
    });
  });

  it("renders on-call engineer name from real provider", async () => {
    renderWidget();
    // SimulationProvider picks from ON_CALL_ROSTER based on date
    const rosterNames = [
      "Dr. Elara Modulus",
      "Prof. Byron Divisor",
      "Eng. Cassandra Remainder",
      "Arch. Dmitri Quotient",
      "SRE Jenkins McFizzface",
      "Dir. Priya Evaluator",
    ];
    await waitFor(() => {
      const found = rosterNames.some((name) => screen.queryByText(name));
      expect(found).toBe(true);
    });
  });

  it("renders on-call initials avatar from real provider", async () => {
    renderWidget();
    // Initials are first 2 chars of: split(" ").map(w => w[0]).join("")
    // "Dr. Elara Modulus" -> "DE", "Prof. Byron Divisor" -> "PB",
    // "Eng. Cassandra Remainder" -> "EC", "Arch. Dmitri Quotient" -> "AD",
    // "SRE Jenkins McFizzface" -> "SJ", "Dir. Priya Evaluator" -> "DP"
    const possibleInitials = ["DE", "PB", "EC", "AD", "SJ", "DP"];
    await waitFor(() => {
      const found = possibleInitials.some((initials) => screen.queryByText(initials));
      expect(found).toBe(true);
    });
  });
});
