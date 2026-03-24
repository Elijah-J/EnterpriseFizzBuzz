import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Accordion } from "../accordion";

const items = [
  { title: "Cache Coherence", content: <p>MESI protocol details</p> },
  { title: "Blockchain Ledger", content: <p>Block mining status</p> },
  { title: "Neural Network", content: <p>Inference pipeline</p> },
];

describe("Accordion", () => {
  it("renders all item titles as trigger buttons", () => {
    render(<Accordion items={items} />);
    expect(screen.getByText("Cache Coherence")).toBeInTheDocument();
    expect(screen.getByText("Blockchain Ledger")).toBeInTheDocument();
    expect(screen.getByText("Neural Network")).toBeInTheDocument();
  });

  it("all items are collapsed by default", () => {
    render(<Accordion items={items} />);
    const buttons = screen.getAllByRole("button");
    buttons.forEach((btn) => {
      expect(btn).toHaveAttribute("aria-expanded", "false");
    });
  });

  it("expands item on click", () => {
    render(<Accordion items={items} />);
    fireEvent.click(screen.getByText("Cache Coherence"));
    expect(screen.getByText("Cache Coherence").closest("button")).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("MESI protocol details")).toBeInTheDocument();
  });

  it("collapses item on second click", () => {
    render(<Accordion items={items} />);
    fireEvent.click(screen.getByText("Cache Coherence"));
    fireEvent.click(screen.getByText("Cache Coherence"));
    expect(screen.getByText("Cache Coherence").closest("button")).toHaveAttribute("aria-expanded", "false");
  });

  it("closes other items in single mode (default)", () => {
    render(<Accordion items={items} />);
    fireEvent.click(screen.getByText("Cache Coherence"));
    fireEvent.click(screen.getByText("Blockchain Ledger"));
    expect(screen.getByText("Cache Coherence").closest("button")).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByText("Blockchain Ledger").closest("button")).toHaveAttribute("aria-expanded", "true");
  });

  it("allows multiple items open when multiple prop is set", () => {
    render(<Accordion items={items} multiple />);
    fireEvent.click(screen.getByText("Cache Coherence"));
    fireEvent.click(screen.getByText("Blockchain Ledger"));
    expect(screen.getByText("Cache Coherence").closest("button")).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Blockchain Ledger").closest("button")).toHaveAttribute("aria-expanded", "true");
  });

  it("respects defaultOpen prop", () => {
    render(<Accordion items={items} defaultOpen={[1]} />);
    expect(screen.getByText("Blockchain Ledger").closest("button")).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Cache Coherence").closest("button")).toHaveAttribute("aria-expanded", "false");
  });

  it("renders chevron icon with rotation on open", () => {
    const { container } = render(<Accordion items={items} defaultOpen={[0]} />);
    const firstTrigger = screen.getByText("Cache Coherence").closest("button")!;
    const svg = firstTrigger.querySelector("svg");
    expect(svg).toHaveClass("rotate-180");
  });

  it("sets aria-controls linking trigger to panel", () => {
    render(<Accordion items={items} />);
    const trigger = screen.getByText("Cache Coherence").closest("button")!;
    const panelId = trigger.getAttribute("aria-controls");
    expect(panelId).toBeTruthy();
    expect(document.getElementById(panelId!)).toBeInTheDocument();
  });

  it("uses CSS grid animation for height transition", () => {
    render(<Accordion items={items} defaultOpen={[0]} />);
    const trigger = screen.getByText("Cache Coherence").closest("button")!;
    const panelId = trigger.getAttribute("aria-controls")!;
    const panel = document.getElementById(panelId)!;
    expect(panel).toHaveClass("transition-[grid-template-rows]");
    expect(panel.style.gridTemplateRows).toBe("1fr");
  });
});
