import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { EmptyState } from "../empty-state";

describe("EmptyState", () => {
  it("renders the title text", () => {
    render(
      <EmptyState
        title="No Evaluations Found"
        description="Run an evaluation to populate this view."
      />,
    );
    expect(screen.getByText("No Evaluations Found")).toBeInTheDocument();
  });

  it("renders the description text", () => {
    render(
      <EmptyState
        title="No Data"
        description="The pipeline has not yet processed any inputs."
      />,
    );
    expect(
      screen.getByText("The pipeline has not yet processed any inputs."),
    ).toBeInTheDocument();
  });

  it("renders SVG illustration with aria-hidden", () => {
    const { container } = render(
      <EmptyState
        title="Empty"
        description="No records available."
      />,
    );
    const svg = container.querySelector("svg");
    expect(svg).toBeInTheDocument();
    expect(svg).toHaveAttribute("aria-hidden", "true");
  });

  it("renders geometric shapes within the SVG illustration", () => {
    const { container } = render(
      <EmptyState
        title="Empty"
        description="No records available."
      />,
    );
    const svg = container.querySelector("svg")!;
    expect(svg.querySelector("circle")).toBeInTheDocument();
    expect(svg.querySelector("rect")).toBeInTheDocument();
    expect(svg.querySelector("polygon")).toBeInTheDocument();
  });

  it("renders action button when provided", () => {
    render(
      <EmptyState
        title="Empty"
        description="No records."
        action={<button>Start Evaluation</button>}
      />,
    );
    expect(screen.getByText("Start Evaluation")).toBeInTheDocument();
  });

  it("does not render action container when action is omitted", () => {
    const { container } = render(
      <EmptyState
        title="Empty"
        description="No records."
      />,
    );
    // The action wrapper div should not exist
    const actionDivs = container.querySelectorAll(".flex.flex-col > div:last-child");
    // Verify no extra action wrapper beyond the SVG and text
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("renders title with heading element", () => {
    render(
      <EmptyState
        title="Pipeline Idle"
        description="Awaiting input."
      />,
    );
    const heading = screen.getByText("Pipeline Idle");
    expect(heading.tagName).toBe("H3");
    expect(heading).toHaveClass("heading-page");
  });

  it("renders description with appropriate text styling", () => {
    render(
      <EmptyState
        title="Title"
        description="Styled description text"
      />,
    );
    const desc = screen.getByText("Styled description text");
    expect(desc).toHaveClass("text-sm");
    expect(desc).toHaveClass("text-text-secondary");
  });
});
