import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Button } from "../button";

// Mock usePress to avoid side-effects in unit tests
vi.mock("@/lib/hooks/use-press", () => ({
  usePress: vi.fn(),
}));

describe("Button", () => {
  it("renders children text", () => {
    render(<Button>Execute Pipeline</Button>);
    expect(screen.getByRole("button")).toHaveTextContent("Execute Pipeline");
  });

  it("renders as a button element", () => {
    render(<Button>Submit</Button>);
    expect(screen.getByRole("button").tagName).toBe("BUTTON");
  });

  it("applies primary variant classes by default", () => {
    render(<Button>Primary</Button>);
    const btn = screen.getByRole("button");
    expect(btn).toHaveClass("bg-accent");
    expect(btn).toHaveClass("text-text-inverse");
  });

  it("applies secondary variant classes", () => {
    render(<Button variant="secondary">Secondary</Button>);
    const btn = screen.getByRole("button");
    expect(btn).toHaveClass("bg-surface-raised");
    expect(btn).toHaveClass("text-text-secondary");
  });

  it("applies ghost variant classes", () => {
    render(<Button variant="ghost">Ghost</Button>);
    const btn = screen.getByRole("button");
    expect(btn).toHaveClass("bg-transparent");
    expect(btn).toHaveClass("text-text-muted");
  });

  it("applies destructive variant classes", () => {
    render(<Button variant="destructive">Delete</Button>);
    const btn = screen.getByRole("button");
    expect(btn).toHaveClass("bg-[var(--status-error)]");
    expect(btn).toHaveClass("text-text-primary");
  });

  it("applies small size classes", () => {
    render(<Button size="sm">Small</Button>);
    const btn = screen.getByRole("button");
    expect(btn).toHaveClass("h-8");
    expect(btn).toHaveClass("px-3");
    expect(btn).toHaveClass("text-xs");
  });

  it("applies medium size classes by default", () => {
    render(<Button>Medium</Button>);
    const btn = screen.getByRole("button");
    expect(btn).toHaveClass("h-10");
    expect(btn).toHaveClass("px-4");
    expect(btn).toHaveClass("text-sm");
  });

  it("applies large size classes", () => {
    render(<Button size="lg">Large</Button>);
    const btn = screen.getByRole("button");
    expect(btn).toHaveClass("h-12");
    expect(btn).toHaveClass("px-6");
    expect(btn).toHaveClass("text-base");
  });

  it("disables the button when disabled prop is set", () => {
    render(<Button disabled>Disabled</Button>);
    expect(screen.getByRole("button")).toBeDisabled();
  });

  it("disables the button when loading is true", () => {
    render(<Button loading>Loading</Button>);
    expect(screen.getByRole("button")).toBeDisabled();
  });

  it("renders loading indicator with role status when loading", () => {
    render(<Button loading>Processing</Button>);
    const status = screen.getByRole("status");
    expect(status).toBeInTheDocument();
    expect(status).toHaveAttribute("aria-label", "Loading");
  });

  it("renders three animated dots during loading state", () => {
    render(<Button loading>Processing</Button>);
    const status = screen.getByRole("status");
    const dots = status.querySelectorAll("span.rounded-full");
    expect(dots).toHaveLength(3);
  });

  it("does not render children text when loading", () => {
    render(<Button loading>Hidden Text</Button>);
    expect(screen.queryByText("Hidden Text")).not.toBeInTheDocument();
  });

  it("renders icon element before label", () => {
    const icon = <svg data-testid="test-icon" />;
    render(<Button icon={icon}>With Icon</Button>);
    expect(screen.getByTestId("test-icon")).toBeInTheDocument();
    expect(screen.getByText("With Icon")).toBeInTheDocument();
  });

  it("fires onClick handler when clicked", () => {
    const handleClick = vi.fn();
    render(<Button onClick={handleClick}>Click Me</Button>);
    fireEvent.click(screen.getByRole("button"));
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it("does not fire onClick when disabled", () => {
    const handleClick = vi.fn();
    render(
      <Button disabled onClick={handleClick}>
        Disabled
      </Button>,
    );
    fireEvent.click(screen.getByRole("button"));
    expect(handleClick).not.toHaveBeenCalled();
  });

  it("includes base structural classes", () => {
    render(<Button>Base</Button>);
    const btn = screen.getByRole("button");
    expect(btn).toHaveClass("inline-flex");
    expect(btn).toHaveClass("items-center");
    expect(btn).toHaveClass("justify-center");
    expect(btn).toHaveClass("rounded");
    expect(btn).toHaveClass("font-medium");
  });

  it("merges custom className", () => {
    render(<Button className="mt-4">Custom</Button>);
    const btn = screen.getByRole("button");
    expect(btn).toHaveClass("mt-4");
    expect(btn).toHaveClass("inline-flex");
  });

  it("passes through additional HTML attributes", () => {
    render(<Button data-testid="pipeline-trigger">Attr</Button>);
    expect(screen.getByTestId("pipeline-trigger")).toBeInTheDocument();
  });

  it("sets data-cursor attribute for pointer interaction", () => {
    render(<Button>Cursor</Button>);
    expect(screen.getByRole("button")).toHaveAttribute(
      "data-cursor",
      "pointer",
    );
  });
});
