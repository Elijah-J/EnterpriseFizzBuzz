import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MagneticButton } from "../magnetic-button";

// Mock hooks to isolate unit behavior
vi.mock("@/lib/hooks/use-magnetic", () => ({
  useMagnetic: vi.fn(),
}));

vi.mock("@/lib/hooks/use-press", () => ({
  usePress: vi.fn(),
}));

describe("MagneticButton", () => {
  it("renders a button element", () => {
    render(<MagneticButton>Evaluate</MagneticButton>);
    expect(screen.getByRole("button")).toBeInTheDocument();
  });

  it("renders children text", () => {
    render(<MagneticButton>Start Pipeline</MagneticButton>);
    expect(screen.getByText("Start Pipeline")).toBeInTheDocument();
  });

  it("wraps button in a div with inline-block class", () => {
    const { container } = render(<MagneticButton>Test</MagneticButton>);
    const wrapper = container.firstElementChild!;
    expect(wrapper.tagName).toBe("DIV");
    expect(wrapper).toHaveClass("inline-block");
  });

  it("passes variant prop through to Button", () => {
    render(<MagneticButton variant="secondary">Secondary</MagneticButton>);
    expect(screen.getByRole("button")).toHaveClass("bg-surface-raised");
  });

  it("passes size prop through to Button", () => {
    render(<MagneticButton size="lg">Large</MagneticButton>);
    expect(screen.getByRole("button")).toHaveClass("h-12");
  });

  it("merges custom className on the button", () => {
    render(<MagneticButton className="w-full">Full</MagneticButton>);
    expect(screen.getByRole("button")).toHaveClass("w-full");
  });
});
