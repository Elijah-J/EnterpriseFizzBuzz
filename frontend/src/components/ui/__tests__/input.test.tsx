import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Input } from "../input";

describe("Input", () => {
  it("renders an input element", () => {
    render(<Input />);
    expect(screen.getByRole("textbox")).toBeInTheDocument();
    expect(screen.getByRole("textbox").tagName).toBe("INPUT");
  });

  it("renders with placeholder text", () => {
    render(<Input placeholder="Enter evaluation range" />);
    expect(
      screen.getByPlaceholderText("Enter evaluation range"),
    ).toBeInTheDocument();
  });

  it("disables the input when disabled prop is set", () => {
    render(<Input disabled />);
    expect(screen.getByRole("textbox")).toBeDisabled();
  });

  it("applies disabled opacity class", () => {
    render(<Input disabled />);
    expect(screen.getByRole("textbox")).toHaveClass("disabled:opacity-50");
  });

  it("handles value and onChange", () => {
    const handleChange = vi.fn();
    render(<Input value="42" onChange={handleChange} />);
    const input = screen.getByRole("textbox");
    expect(input).toHaveValue("42");
    fireEvent.change(input, { target: { value: "100" } });
    expect(handleChange).toHaveBeenCalledTimes(1);
  });

  it("includes base structural classes", () => {
    render(<Input />);
    const input = screen.getByRole("textbox");
    expect(input).toHaveClass("w-full");
    expect(input).toHaveClass("rounded");
    expect(input).toHaveClass("bg-surface-raised");
    expect(input).toHaveClass("border");
    expect(input).toHaveClass("border-border-subtle");
    expect(input).toHaveClass("px-3");
    expect(input).toHaveClass("py-2");
    expect(input).toHaveClass("text-sm");
  });

  it("includes focus ring classes for keyboard accessibility", () => {
    render(<Input />);
    const input = screen.getByRole("textbox");
    expect(input).toHaveClass("focus:ring-2");
    expect(input).toHaveClass("focus:ring-[var(--accent)]/50");
  });

  it("merges custom className", () => {
    render(<Input className="max-w-xs" />);
    const input = screen.getByRole("textbox");
    expect(input).toHaveClass("max-w-xs");
    expect(input).toHaveClass("w-full");
  });

  it("passes through additional HTML attributes", () => {
    render(<Input data-testid="range-input" type="number" />);
    expect(screen.getByTestId("range-input")).toBeInTheDocument();
  });

  it("forwards ref to the input element", () => {
    const ref = { current: null } as React.RefObject<HTMLInputElement>;
    render(<Input ref={ref} />);
    expect(ref.current).toBeInstanceOf(HTMLInputElement);
  });
});
