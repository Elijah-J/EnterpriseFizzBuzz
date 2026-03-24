import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { AboutPanel } from "../about-panel";

// Mock Dialog as a passthrough
vi.mock("@/components/ui/dialog", () => ({
  Dialog: ({
    open,
    onClose,
    title,
    children,
  }: {
    open: boolean;
    onClose: () => void;
    title: string;
    children: React.ReactNode;
    size?: string;
  }) =>
    open ? (
      <div role="dialog" aria-label={title}>
        <h2>{title}</h2>
        {children}
        <button type="button" onClick={onClose}>Close</button>
      </div>
    ) : null,
}));

describe("AboutPanel", () => {
  it("renders nothing when closed", () => {
    const { container } = render(
      <AboutPanel open={false} onClose={vi.fn()} />,
    );
    expect(container.querySelector("[role='dialog']")).not.toBeInTheDocument();
  });

  it("renders a dialog with correct title when open", () => {
    render(<AboutPanel open={true} onClose={vi.fn()} />);
    expect(
      screen.getByRole("dialog", { name: "About Enterprise FizzBuzz" }),
    ).toBeInTheDocument();
  });

  it("renders the platform description", () => {
    render(<AboutPanel open={true} onClose={vi.fn()} />);
    expect(
      screen.getByText(/mission-critical evaluation infrastructure/),
    ).toBeInTheDocument();
  });

  it("renders all six platform stats", () => {
    render(<AboutPanel open={true} onClose={vi.fn()} />);
    expect(screen.getByText("Lines of Code")).toBeInTheDocument();
    expect(screen.getByText("300,000+")).toBeInTheDocument();
    expect(screen.getByText("Infrastructure Modules")).toBeInTheDocument();
    expect(screen.getByText("110+")).toBeInTheDocument();
    expect(screen.getByText("Custom Exceptions")).toBeInTheDocument();
    expect(screen.getByText("608")).toBeInTheDocument();
    expect(screen.getByText("CLI Flags")).toBeInTheDocument();
    expect(screen.getByText("315+")).toBeInTheDocument();
    expect(screen.getByText("Test Count")).toBeInTheDocument();
    expect(screen.getByText("~11,400")).toBeInTheDocument();
    expect(screen.getByText("Python Files")).toBeInTheDocument();
    expect(screen.getByText("289")).toBeInTheDocument();
  });

  it("credits Bob McFizzington as the engineer", () => {
    render(<AboutPanel open={true} onClose={vi.fn()} />);
    expect(
      screen.getByText("Engineered by Bob McFizzington"),
    ).toBeInTheDocument();
  });

  it("displays the Distinguished Modular Arithmetic Fellow title", () => {
    render(<AboutPanel open={true} onClose={vi.fn()} />);
    expect(
      screen.getByText(
        "Chief FizzBuzz Architect & Distinguished Modular Arithmetic Fellow",
      ),
    ).toBeInTheDocument();
  });

  it("renders stat values with tabular-nums class", () => {
    const { container } = render(
      <AboutPanel open={true} onClose={vi.fn()} />,
    );
    const statValues = container.querySelectorAll(".tabular-nums");
    expect(statValues).toHaveLength(6);
  });

  it("renders stats in a two-column grid", () => {
    const { container } = render(
      <AboutPanel open={true} onClose={vi.fn()} />,
    );
    const grid = container.querySelector(".grid-cols-2");
    expect(grid).toBeInTheDocument();
  });
});
