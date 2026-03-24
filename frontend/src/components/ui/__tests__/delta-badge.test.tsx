import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { DeltaBadge } from "../delta-badge";

describe("DeltaBadge", () => {
  it("renders upward arrow for positive value", () => {
    render(<DeltaBadge value={5.2} />);
    expect(screen.getByText(/\u25B2/)).toBeInTheDocument();
  });

  it("renders downward arrow for negative value", () => {
    render(<DeltaBadge value={-3.1} />);
    expect(screen.getByText(/\u25BC/)).toBeInTheDocument();
  });

  it("renders formatted percentage for positive value", () => {
    render(<DeltaBadge value={5.2} />);
    expect(screen.getByText(/5\.2%/)).toBeInTheDocument();
  });

  it("renders absolute value for negative value", () => {
    render(<DeltaBadge value={-3.1} />);
    expect(screen.getByText(/3\.1%/)).toBeInTheDocument();
  });

  it("applies green color class for positive value", () => {
    render(<DeltaBadge value={1.0} />);
    const badge = screen.getByText(/\u25B2/).closest("span")!;
    expect(badge).toHaveClass("text-fizz-400");
  });

  it("applies error color class for negative value", () => {
    render(<DeltaBadge value={-1.0} />);
    const badge = screen.getByText(/\u25BC/).closest("span")!;
    expect(badge).toHaveClass("text-[var(--status-error)]");
  });

  it("treats zero as positive with upward arrow", () => {
    render(<DeltaBadge value={0} />);
    expect(screen.getByText(/\u25B2/)).toBeInTheDocument();
  });

  it("respects decimals prop", () => {
    render(<DeltaBadge value={3.456} decimals={2} />);
    expect(screen.getByText(/3\.46%/)).toBeInTheDocument();
  });

  it("defaults to 1 decimal place", () => {
    render(<DeltaBadge value={3.456} />);
    expect(screen.getByText(/3\.5%/)).toBeInTheDocument();
  });
});
