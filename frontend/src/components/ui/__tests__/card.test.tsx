import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { Card, CardHeader, CardContent, CardFooter } from "../card";

describe("Card", () => {
  it("renders children content", () => {
    render(<Card>Operational Data</Card>);
    expect(screen.getByText("Operational Data")).toBeInTheDocument();
  });

  it("applies default variant classes", () => {
    render(<Card data-testid="card">Default</Card>);
    const card = screen.getByTestId("card");
    expect(card).toHaveClass("bg-surface-raised");
    expect(card).toHaveClass("border-border-subtle");
  });

  it("applies elevated variant classes", () => {
    render(
      <Card variant="elevated" data-testid="card">
        Elevated
      </Card>,
    );
    const card = screen.getByTestId("card");
    expect(card).toHaveClass("bg-surface-overlay");
    expect(card).toHaveClass("border-border-default");
  });

  it("applies featured variant classes with amber left border", () => {
    render(
      <Card variant="featured" data-testid="card">
        Featured
      </Card>,
    );
    const card = screen.getByTestId("card");
    expect(card).toHaveClass("border-l-2");
    expect(card).toHaveClass("border-l-[var(--accent)]");
  });

  it("renders grain overlay div for editorial texture", () => {
    render(<Card data-testid="card">Content</Card>);
    const card = screen.getByTestId("card");
    const grainOverlay = card.querySelector(".pointer-events-none");
    expect(grainOverlay).toBeInTheDocument();
    expect(grainOverlay).toHaveClass("absolute");
    expect(grainOverlay).toHaveClass("inset-0");
  });

  it("applies interactive hover class when onClick is present", () => {
    const handleClick = vi.fn();
    render(
      <Card data-testid="card" onClick={handleClick}>
        Interactive
      </Card>,
    );
    const card = screen.getByTestId("card");
    expect(card).toHaveClass("hover:-translate-y-[1px]");
    expect(card).toHaveAttribute("data-cursor", "pointer");
  });

  it("does not apply interactive hover class without onClick", () => {
    render(<Card data-testid="card">Static</Card>);
    const card = screen.getByTestId("card");
    expect(card).not.toHaveClass("hover:-translate-y-[1px]");
    expect(card).not.toHaveAttribute("data-cursor");
  });

  it("includes base structural classes", () => {
    render(<Card data-testid="card">Base</Card>);
    const card = screen.getByTestId("card");
    expect(card).toHaveClass("relative");
    expect(card).toHaveClass("rounded-lg");
    expect(card).toHaveClass("border");
    expect(card).toHaveClass("overflow-hidden");
  });

  it("merges custom className", () => {
    render(
      <Card data-testid="card" className="p-8">
        Custom
      </Card>,
    );
    const card = screen.getByTestId("card");
    expect(card).toHaveClass("p-8");
    expect(card).toHaveClass("rounded-lg");
  });
});

describe("CardHeader", () => {
  it("renders children content", () => {
    render(<CardHeader>System Overview</CardHeader>);
    expect(screen.getByText("System Overview")).toBeInTheDocument();
  });

  it("includes border and padding classes", () => {
    render(<CardHeader data-testid="header">Header</CardHeader>);
    const header = screen.getByTestId("header");
    expect(header).toHaveClass("border-b");
    expect(header).toHaveClass("border-border-subtle");
    expect(header).toHaveClass("px-4");
    expect(header).toHaveClass("py-3");
  });

  it("merges custom className", () => {
    render(
      <CardHeader data-testid="header" className="bg-surface-overlay">
        Styled
      </CardHeader>,
    );
    const header = screen.getByTestId("header");
    expect(header).toHaveClass("bg-surface-overlay");
    expect(header).toHaveClass("px-4");
  });
});

describe("CardContent", () => {
  it("renders children content", () => {
    render(<CardContent>Metrics payload</CardContent>);
    expect(screen.getByText("Metrics payload")).toBeInTheDocument();
  });

  it("includes padding classes", () => {
    render(<CardContent data-testid="content">Data</CardContent>);
    const content = screen.getByTestId("content");
    expect(content).toHaveClass("px-4");
    expect(content).toHaveClass("py-3");
  });

  it("merges custom className", () => {
    render(
      <CardContent data-testid="content" className="space-y-4">
        Spaced
      </CardContent>,
    );
    const content = screen.getByTestId("content");
    expect(content).toHaveClass("space-y-4");
    expect(content).toHaveClass("px-4");
  });
});

describe("CardFooter", () => {
  it("renders children content", () => {
    render(<CardFooter>Last updated: 2026-03-24</CardFooter>);
    expect(
      screen.getByText("Last updated: 2026-03-24"),
    ).toBeInTheDocument();
  });

  it("includes border-top and padding classes", () => {
    render(<CardFooter data-testid="footer">Footer</CardFooter>);
    const footer = screen.getByTestId("footer");
    expect(footer).toHaveClass("border-t");
    expect(footer).toHaveClass("border-border-subtle");
    expect(footer).toHaveClass("px-4");
    expect(footer).toHaveClass("py-3");
  });

  it("merges custom className", () => {
    render(
      <CardFooter data-testid="footer" className="flex justify-end">
        Actions
      </CardFooter>,
    );
    const footer = screen.getByTestId("footer");
    expect(footer).toHaveClass("flex");
    expect(footer).toHaveClass("justify-end");
    expect(footer).toHaveClass("px-4");
  });
});
