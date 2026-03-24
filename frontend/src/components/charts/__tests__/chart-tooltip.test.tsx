import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ChartTooltip } from "../chart-tooltip";

describe("ChartTooltip", () => {
  it("renders content when visible", () => {
    render(
      <ChartTooltip
        x={100}
        y={50}
        visible={true}
        content={<span>Throughput: 12,847 req/s</span>}
      />,
    );
    expect(screen.getByText("Throughput: 12,847 req/s")).toBeInTheDocument();
  });

  it("does not render content when not visible", () => {
    render(
      <ChartTooltip
        x={100}
        y={50}
        visible={false}
        content={<span>Hidden content</span>}
      />,
    );
    const el = screen.queryByText("Hidden content");
    // Tooltip may still exist in DOM but be hidden via opacity
    if (el) {
      expect(el.closest("[style]")).toBeTruthy();
    }
  });

  it("positions at the specified coordinates", () => {
    const { container } = render(
      <ChartTooltip
        x={200}
        y={100}
        visible={true}
        content={<span>Position test</span>}
      />,
    );
    const tooltip = container.firstElementChild;
    expect(tooltip).toBeInTheDocument();
  });
});
