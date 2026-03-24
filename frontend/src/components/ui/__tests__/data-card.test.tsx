import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { DataCard } from "../data-card";

// Mock dependent components to isolate unit behavior
vi.mock("../animated-number", () => ({
  AnimatedNumber: ({ value, className }: { value: number; className?: string }) => (
    <span className={className} data-testid="animated-number">
      {value}
    </span>
  ),
}));

vi.mock("@/components/charts", () => ({
  Sparkline: ({ data }: { data: number[] }) => (
    <svg data-testid="sparkline" data-points={data.length} />
  ),
}));

describe("DataCard", () => {
  it("renders the label text", () => {
    render(<DataCard label="Throughput" value={1250} />);
    expect(screen.getByText("Throughput")).toBeInTheDocument();
  });

  it("renders the value via AnimatedNumber", () => {
    render(<DataCard label="Evaluations" value={42000} />);
    expect(screen.getByTestId("animated-number")).toHaveTextContent("42000");
  });

  it("renders unit label when provided", () => {
    render(<DataCard label="Latency" value={12} unit="ms" />);
    expect(screen.getByText("ms")).toBeInTheDocument();
  });

  it("does not render unit when omitted", () => {
    render(<DataCard label="Count" value={100} />);
    expect(screen.queryByText("ms")).not.toBeInTheDocument();
    expect(screen.queryByText("req/s")).not.toBeInTheDocument();
  });

  it("renders upward trend arrow for positive trend", () => {
    render(<DataCard label="Cache Hit Rate" value={95} trend={2.5} />);
    expect(screen.getByText(/\u25B2/)).toBeInTheDocument();
    expect(screen.getByText(/2\.5%/)).toBeInTheDocument();
  });

  it("renders downward trend arrow for negative trend", () => {
    render(<DataCard label="Error Rate" value={3} trend={-1.2} />);
    expect(screen.getByText(/\u25BC/)).toBeInTheDocument();
    expect(screen.getByText(/1\.2%/)).toBeInTheDocument();
  });

  it("applies green color class for positive trend", () => {
    render(<DataCard label="Uptime" value={99} trend={0.1} />);
    const trendEl = screen.getByText(/\u25B2/);
    expect(trendEl).toHaveClass("text-fizz-400");
  });

  it("applies error color class for negative trend", () => {
    render(<DataCard label="Errors" value={5} trend={-3.0} />);
    const trendEl = screen.getByText(/\u25BC/);
    expect(trendEl).toHaveClass("text-[var(--status-error)]");
  });

  it("treats zero trend as positive with upward arrow", () => {
    render(<DataCard label="Stable" value={50} trend={0} />);
    expect(screen.getByText(/\u25B2/)).toBeInTheDocument();
    expect(screen.getByText(/\u25B2/)).toHaveClass("text-fizz-400");
  });

  it("does not render trend indicator when trend is omitted", () => {
    render(<DataCard label="Static" value={100} />);
    expect(screen.queryByText(/\u25B2/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\u25BC/)).not.toBeInTheDocument();
  });

  it("renders sparkline SVG when sparklineData is provided", () => {
    render(
      <DataCard label="History" value={80} sparklineData={[10, 20, 30, 40]} />,
    );
    expect(screen.getByTestId("sparkline")).toBeInTheDocument();
  });

  it("does not render sparkline when sparklineData is omitted", () => {
    render(<DataCard label="No History" value={50} />);
    expect(screen.queryByTestId("sparkline")).not.toBeInTheDocument();
  });

  it("does not render sparkline when data has fewer than 2 points", () => {
    render(<DataCard label="Insufficient" value={50} sparklineData={[10]} />);
    expect(screen.queryByTestId("sparkline")).not.toBeInTheDocument();
  });

  it("merges custom className on the outer card", () => {
    const { container } = render(
      <DataCard label="Custom" value={1} className="col-span-2" />,
    );
    const card = container.firstElementChild!;
    expect(card).toHaveClass("col-span-2");
  });

  it("renders label with data-label class", () => {
    render(<DataCard label="Pipeline Metric" value={100} />);
    const label = screen.getByText("Pipeline Metric");
    expect(label).toHaveClass("data-label");
  });
});
