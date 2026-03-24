import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Badge } from "../badge";

describe("Badge", () => {
  it("renders children text", () => {
    render(<Badge>Operational</Badge>);
    expect(screen.getByText("Operational")).toBeInTheDocument();
  });

  it("applies the default info variant classes", () => {
    render(<Badge>Info</Badge>);
    const badge = screen.getByText("Info");

    expect(badge).toHaveClass("bg-buzz-400/15");
    expect(badge).toHaveClass("text-buzz-400");
  });

  it("applies success variant classes", () => {
    render(<Badge variant="success">Healthy</Badge>);
    const badge = screen.getByText("Healthy");

    expect(badge).toHaveClass("bg-fizz-400/15");
    expect(badge).toHaveClass("text-fizz-400");
  });

  it("applies warning variant classes", () => {
    render(<Badge variant="warning">Degraded</Badge>);
    const badge = screen.getByText("Degraded");

    expect(badge).toHaveClass("bg-[var(--accent)]/15");
    expect(badge).toHaveClass("text-[var(--accent)]");
  });

  it("applies error variant classes", () => {
    render(<Badge variant="error">Critical</Badge>);
    const badge = screen.getByText("Critical");

    expect(badge).toHaveClass("bg-[var(--status-error)]/15");
    expect(badge).toHaveClass("text-[var(--status-error)]");
  });

  it("renders as a span element", () => {
    render(<Badge>Status</Badge>);
    const badge = screen.getByText("Status");

    expect(badge.tagName).toBe("SPAN");
  });

  it("includes base structural classes", () => {
    render(<Badge>Base</Badge>);
    const badge = screen.getByText("Base");

    expect(badge).toHaveClass("inline-flex");
    expect(badge).toHaveClass("items-center");
    expect(badge).toHaveClass("rounded-full");
    expect(badge).toHaveClass("text-xs");
    expect(badge).toHaveClass("font-medium");
  });

  it("merges custom className", () => {
    render(<Badge className="ml-2">Custom</Badge>);
    const badge = screen.getByText("Custom");

    expect(badge).toHaveClass("ml-2");
    expect(badge).toHaveClass("inline-flex");
  });

  it("passes through additional HTML attributes", () => {
    render(<Badge data-testid="status-badge">Attr</Badge>);
    expect(screen.getByTestId("status-badge")).toBeInTheDocument();
  });
});
