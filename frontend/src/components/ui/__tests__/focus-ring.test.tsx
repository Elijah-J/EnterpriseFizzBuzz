import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { FocusRing } from "../focus-ring";

describe("FocusRing", () => {
  it("renders children content", () => {
    render(
      <FocusRing>
        <button>Action</button>
      </FocusRing>,
    );
    expect(screen.getByText("Action")).toBeInTheDocument();
  });

  it("applies focus-visible ring classes", () => {
    render(
      <FocusRing data-testid="ring">
        <span>Content</span>
      </FocusRing>,
    );
    const wrapper = screen.getByTestId("ring");
    expect(wrapper).toHaveClass("focus-visible:ring-2");
    expect(wrapper).toHaveClass("focus-visible:ring-[var(--accent)]");
  });

  it("applies rounded class", () => {
    render(
      <FocusRing data-testid="ring">
        <span>Content</span>
      </FocusRing>,
    );
    expect(screen.getByTestId("ring")).toHaveClass("rounded");
  });

  it("applies ring offset classes", () => {
    render(
      <FocusRing data-testid="ring">
        <span>Content</span>
      </FocusRing>,
    );
    const wrapper = screen.getByTestId("ring");
    expect(wrapper).toHaveClass("focus-visible:ring-offset-2");
    expect(wrapper).toHaveClass("focus-visible:ring-offset-surface-ground");
  });

  it("merges custom className", () => {
    render(
      <FocusRing data-testid="ring" className="p-4">
        <span>Content</span>
      </FocusRing>,
    );
    const wrapper = screen.getByTestId("ring");
    expect(wrapper).toHaveClass("p-4");
    expect(wrapper).toHaveClass("rounded");
  });
});
