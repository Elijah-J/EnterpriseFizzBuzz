import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ChartLegend } from "../chart-legend";

const items = [
  { key: "fizz", label: "Fizz", color: "var(--fizz-400)", active: true },
  { key: "buzz", label: "Buzz", color: "var(--buzz-400)", active: true },
  { key: "fizzbuzz", label: "FizzBuzz", color: "var(--fizzbuzz-400)", active: false },
];

describe("ChartLegend", () => {
  it("renders all legend items with labels", () => {
    render(<ChartLegend items={items} />);
    expect(screen.getByText("Fizz")).toBeInTheDocument();
    expect(screen.getByText("Buzz")).toBeInTheDocument();
    expect(screen.getByText("FizzBuzz")).toBeInTheDocument();
  });

  it("fires onToggle callback when a legend item is clicked", () => {
    const onToggle = vi.fn();
    render(<ChartLegend items={items} onToggle={onToggle} />);
    fireEvent.click(screen.getByText("Fizz"));
    expect(onToggle).toHaveBeenCalledWith("fizz");
  });

  it("fires onHighlight callback on mouse enter", () => {
    const onHighlight = vi.fn();
    render(<ChartLegend items={items} onHighlight={onHighlight} />);
    fireEvent.mouseEnter(screen.getByText("Buzz").closest("button")!);
    expect(onHighlight).toHaveBeenCalledWith("buzz");
  });

  it("renders color indicator dots for each item", () => {
    const { container } = render(<ChartLegend items={items} />);
    const dots = container.querySelectorAll("span[class*='rounded-full']");
    expect(dots.length).toBe(items.length);
  });
});
