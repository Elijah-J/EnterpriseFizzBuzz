import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ProgressBar } from "../progress-bar";

describe("ProgressBar", () => {
  it("renders progressbar role element", () => {
    render(<ProgressBar value={50} />);
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
  });

  it("sets aria-valuenow for determinate variant", () => {
    render(<ProgressBar value={75} />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "75");
  });

  it("sets aria-valuemin and aria-valuemax", () => {
    render(<ProgressBar value={50} />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuemin", "0");
    expect(bar).toHaveAttribute("aria-valuemax", "100");
  });

  it("does not set aria-valuenow for indeterminate variant", () => {
    render(<ProgressBar variant="indeterminate" />);
    expect(screen.getByRole("progressbar")).not.toHaveAttribute("aria-valuenow");
  });

  it("clamps value between 0 and 100", () => {
    render(<ProgressBar value={150} />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "100");
  });

  it("renders label text when provided", () => {
    render(<ProgressBar value={30} label="Pipeline Progress" />);
    expect(screen.getByText("Pipeline Progress")).toBeInTheDocument();
  });

  it("renders percentage text for determinate variant with label", () => {
    render(<ProgressBar value={42} label="Loading" />);
    expect(screen.getByText("42%")).toBeInTheDocument();
  });

  it("does not render percentage text for indeterminate with label", () => {
    render(<ProgressBar variant="indeterminate" label="Initializing" />);
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });

  it("sets aria-label from prop", () => {
    render(<ProgressBar value={50} aria-label="Evaluation progress" />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-label", "Evaluation progress");
  });

  it("falls back to label prop for aria-label", () => {
    render(<ProgressBar value={50} label="Upload" />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-label", "Upload");
  });
});
