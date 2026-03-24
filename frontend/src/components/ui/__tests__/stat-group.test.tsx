import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatGroup } from "../stat-group";

const items = [
  { label: "Throughput", value: "12,450 req/s" },
  { label: "Latency P99", value: "4.2ms", trend: { direction: "down" as const, label: "-8.3%" } },
  { label: "Cache Hit", value: "97.2%", trend: { direction: "up" as const, label: "+2.1%" } },
];

describe("StatGroup", () => {
  it("renders all stat item labels", () => {
    render(<StatGroup items={items} />);
    expect(screen.getByText("Throughput")).toBeInTheDocument();
    expect(screen.getByText("Latency P99")).toBeInTheDocument();
    expect(screen.getByText("Cache Hit")).toBeInTheDocument();
  });

  it("renders all stat item values", () => {
    render(<StatGroup items={items} />);
    expect(screen.getByText("12,450 req/s")).toBeInTheDocument();
    expect(screen.getByText("4.2ms")).toBeInTheDocument();
    expect(screen.getByText("97.2%")).toBeInTheDocument();
  });

  it("renders trend indicator with direction arrow for up trend", () => {
    render(<StatGroup items={items} />);
    expect(screen.getByText(/\u2191.*\+2\.1%/)).toBeInTheDocument();
  });

  it("renders trend indicator with direction arrow for down trend", () => {
    render(<StatGroup items={items} />);
    expect(screen.getByText(/\u2193.*-8\.3%/)).toBeInTheDocument();
  });

  it("applies green color for upward trend", () => {
    render(<StatGroup items={items} />);
    const trendEl = screen.getByText(/\u2191.*\+2\.1%/);
    expect(trendEl).toHaveClass("text-fizz-400");
  });

  it("applies red color for downward trend", () => {
    render(<StatGroup items={items} />);
    const trendEl = screen.getByText(/\u2193.*-8\.3%/);
    expect(trendEl).toHaveClass("text-red-400");
  });

  it("does not render trend when omitted", () => {
    render(<StatGroup items={[{ label: "Count", value: "42" }]} />);
    expect(screen.queryByText(/\u2191/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\u2193/)).not.toBeInTheDocument();
  });

  it("renders icon when provided", () => {
    const itemsWithIcon = [
      { label: "Status", value: "OK", icon: <span data-testid="icon">IC</span> },
    ];
    render(<StatGroup items={itemsWithIcon} />);
    expect(screen.getByTestId("icon")).toBeInTheDocument();
  });

  it("returns null for empty items array", () => {
    const { container } = render(<StatGroup items={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("applies responsive grid classes", () => {
    const { container } = render(<StatGroup items={items} />);
    expect(container.firstChild).toHaveClass("grid-cols-2");
    expect(container.firstChild).toHaveClass("sm:divide-x");
  });
});
