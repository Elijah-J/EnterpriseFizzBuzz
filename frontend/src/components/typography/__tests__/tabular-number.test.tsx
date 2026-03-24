import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { TabularNumber } from "../tabular-number";

describe("TabularNumber", () => {
  it("renders children content", () => {
    render(<TabularNumber>12,345</TabularNumber>);
    expect(screen.getByText("12,345")).toBeInTheDocument();
  });

  it("applies tabular-nums class", () => {
    render(<TabularNumber>42</TabularNumber>);
    expect(screen.getByText("42")).toHaveClass("tabular-nums");
  });

  it("renders as a span element", () => {
    render(<TabularNumber>99</TabularNumber>);
    expect(screen.getByText("99").tagName).toBe("SPAN");
  });

  it("applies decimal alignment class when alignDecimal is true", () => {
    render(<TabularNumber alignDecimal>3.14</TabularNumber>);
    expect(screen.getByText("3.14")).toHaveClass("tabular-number-decimal");
  });

  it("does not apply decimal alignment class by default", () => {
    render(<TabularNumber>42</TabularNumber>);
    expect(screen.getByText("42")).not.toHaveClass("tabular-number-decimal");
  });

  it("merges custom className", () => {
    render(<TabularNumber className="text-lg">100</TabularNumber>);
    const el = screen.getByText("100");
    expect(el).toHaveClass("text-lg");
    expect(el).toHaveClass("tabular-nums");
  });
});
