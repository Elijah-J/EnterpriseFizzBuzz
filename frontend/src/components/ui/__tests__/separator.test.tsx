import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Separator } from "../separator";

describe("Separator", () => {
  it("renders an hr element", () => {
    render(<Separator />);
    expect(screen.getByRole("separator")).toBeInTheDocument();
    expect(screen.getByRole("separator").tagName).toBe("HR");
  });

  it("applies border-subtle class for low-contrast division", () => {
    render(<Separator />);
    expect(screen.getByRole("separator")).toHaveClass("border-border-subtle");
  });

  it("applies border-t class", () => {
    render(<Separator />);
    expect(screen.getByRole("separator")).toHaveClass("border-t");
  });

  it("merges custom className", () => {
    render(<Separator className="my-6" />);
    const sep = screen.getByRole("separator");
    expect(sep).toHaveClass("my-6");
    expect(sep).toHaveClass("border-border-subtle");
  });

  it("passes through additional HTML attributes", () => {
    render(<Separator data-testid="section-divider" />);
    expect(screen.getByTestId("section-divider")).toBeInTheDocument();
  });
});
