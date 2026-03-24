import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Timeline } from "../timeline";

const items = [
  { timestamp: "14:32:01", title: "Evaluation started", status: "active" as const },
  { timestamp: "14:32:04", title: "Cache miss — cold start", content: <span>L1 cache primed</span>, status: "default" as const },
  { timestamp: "14:32:08", title: "Evaluation complete", status: "success" as const },
];

describe("Timeline", () => {
  it("renders all timeline items in order", () => {
    render(<Timeline items={items} />);
    expect(screen.getByText("Evaluation started")).toBeInTheDocument();
    expect(screen.getByText("Cache miss — cold start")).toBeInTheDocument();
    expect(screen.getByText("Evaluation complete")).toBeInTheDocument();
  });

  it("renders timestamps for each item", () => {
    render(<Timeline items={items} />);
    expect(screen.getByText("14:32:01")).toBeInTheDocument();
    expect(screen.getByText("14:32:04")).toBeInTheDocument();
    expect(screen.getByText("14:32:08")).toBeInTheDocument();
  });

  it("renders optional content when provided", () => {
    render(<Timeline items={items} />);
    expect(screen.getByText("L1 cache primed")).toBeInTheDocument();
  });

  it("applies amber dot class for active status", () => {
    const { container } = render(<Timeline items={[items[0]]} />);
    const dot = container.querySelector(".bg-accent");
    expect(dot).toBeInTheDocument();
  });

  it("applies green dot class for success status", () => {
    const { container } = render(<Timeline items={[items[2]]} />);
    const dot = container.querySelector(".bg-fizz-500");
    expect(dot).toBeInTheDocument();
  });

  it("applies red dot class for error status", () => {
    const errorItem = { timestamp: "14:33:00", title: "Pipeline failure", status: "error" as const };
    const { container } = render(<Timeline items={[errorItem]} />);
    const dot = container.querySelector(".bg-red-500");
    expect(dot).toBeInTheDocument();
  });

  it("renders connecting line between items except last", () => {
    const { container } = render(<Timeline items={items} />);
    const lines = container.querySelectorAll(".bg-border-subtle");
    // Should have connecting lines for first two items, not the last
    expect(lines).toHaveLength(2);
  });

  it("returns null for empty items array", () => {
    const { container } = render(<Timeline items={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("merges custom className", () => {
    const { container } = render(<Timeline items={items} className="mt-4" />);
    expect(container.firstChild).toHaveClass("mt-4");
  });
});
