import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Tooltip } from "../tooltip";

describe("Tooltip", () => {
  it("renders the trigger children", () => {
    render(
      <Tooltip content="Evaluation throughput">
        <button>Hover me</button>
      </Tooltip>,
    );
    expect(screen.getByText("Hover me")).toBeInTheDocument();
  });

  it("renders tooltip content in the DOM", () => {
    render(
      <Tooltip content="Cache hit ratio">
        <button>Trigger</button>
      </Tooltip>,
    );
    expect(screen.getByRole("tooltip")).toHaveTextContent("Cache hit ratio");
  });

  it("hides tooltip by default with opacity-0", () => {
    render(
      <Tooltip content="Hidden info">
        <button>Trigger</button>
      </Tooltip>,
    );
    expect(screen.getByRole("tooltip")).toHaveClass("opacity-0");
  });

  it("shows tooltip on mouse enter with opacity-100", () => {
    render(
      <Tooltip content="Visible info">
        <button>Trigger</button>
      </Tooltip>,
    );
    const wrapper = screen.getByText("Trigger").closest("span")!;
    fireEvent.mouseEnter(wrapper);
    expect(screen.getByRole("tooltip")).toHaveClass("opacity-100");
  });

  it("hides tooltip on mouse leave", () => {
    render(
      <Tooltip content="Disappearing info">
        <button>Trigger</button>
      </Tooltip>,
    );
    const wrapper = screen.getByText("Trigger").closest("span")!;
    fireEvent.mouseEnter(wrapper);
    fireEvent.mouseLeave(wrapper);
    expect(screen.getByRole("tooltip")).toHaveClass("opacity-0");
  });

  it("shows tooltip on focus capture", () => {
    render(
      <Tooltip content="Focus info">
        <button>Trigger</button>
      </Tooltip>,
    );
    const wrapper = screen.getByText("Trigger").closest("span")!;
    fireEvent.focusIn(wrapper);
    expect(screen.getByRole("tooltip")).toHaveClass("opacity-100");
  });

  it("hides tooltip on blur capture", () => {
    render(
      <Tooltip content="Blur info">
        <button>Trigger</button>
      </Tooltip>,
    );
    const wrapper = screen.getByText("Trigger").closest("span")!;
    fireEvent.focusIn(wrapper);
    fireEvent.focusOut(wrapper);
    expect(screen.getByRole("tooltip")).toHaveClass("opacity-0");
  });

  it("applies top positioning classes by default", () => {
    render(
      <Tooltip content="Top tooltip">
        <button>Trigger</button>
      </Tooltip>,
    );
    expect(screen.getByRole("tooltip")).toHaveClass("bottom-full");
    expect(screen.getByRole("tooltip")).toHaveClass("mb-2");
  });

  it("applies bottom positioning classes when side is bottom", () => {
    render(
      <Tooltip content="Bottom tooltip" side="bottom">
        <button>Trigger</button>
      </Tooltip>,
    );
    expect(screen.getByRole("tooltip")).toHaveClass("top-full");
    expect(screen.getByRole("tooltip")).toHaveClass("mt-2");
  });

  it("applies left positioning classes when side is left", () => {
    render(
      <Tooltip content="Left tooltip" side="left">
        <button>Trigger</button>
      </Tooltip>,
    );
    expect(screen.getByRole("tooltip")).toHaveClass("right-full");
    expect(screen.getByRole("tooltip")).toHaveClass("mr-2");
  });

  it("applies right positioning classes when side is right", () => {
    render(
      <Tooltip content="Right tooltip" side="right">
        <button>Trigger</button>
      </Tooltip>,
    );
    expect(screen.getByRole("tooltip")).toHaveClass("left-full");
    expect(screen.getByRole("tooltip")).toHaveClass("ml-2");
  });

  it("sets aria-describedby on the wrapper element", () => {
    render(
      <Tooltip content="Accessible tooltip">
        <button>Trigger</button>
      </Tooltip>,
    );
    const wrapper = screen.getByText("Trigger").closest("span")!;
    const tooltipId = screen.getByRole("tooltip").getAttribute("id");
    expect(wrapper).toHaveAttribute("aria-describedby", tooltipId);
  });

  it("includes pointer-events-none on tooltip surface", () => {
    render(
      <Tooltip content="Non-interactive">
        <button>Trigger</button>
      </Tooltip>,
    );
    expect(screen.getByRole("tooltip")).toHaveClass("pointer-events-none");
  });
});
