import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Breadcrumbs } from "../breadcrumbs";

// Mock next/link as passthrough anchor
vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    className,
  }: {
    href: string;
    children: React.ReactNode;
    className?: string;
  }) => (
    <a href={href} className={className}>
      {children}
    </a>
  ),
}));

import { vi } from "vitest";

describe("Breadcrumbs", () => {
  it("renders a navigation element with Breadcrumb label", () => {
    render(<Breadcrumbs items={[{ label: "Home" }]} />);
    expect(
      screen.getByRole("navigation", { name: "Breadcrumb" }),
    ).toBeInTheDocument();
  });

  it("renders all breadcrumb items", () => {
    render(
      <Breadcrumbs
        items={[
          { label: "Platform", href: "/" },
          { label: "Monitor", href: "/monitor" },
          { label: "Metrics" },
        ]}
      />,
    );
    expect(screen.getByText("Platform")).toBeInTheDocument();
    expect(screen.getByText("Monitor")).toBeInTheDocument();
    expect(screen.getByText("Metrics")).toBeInTheDocument();
  });

  it("renders intermediate items with hrefs as links", () => {
    render(
      <Breadcrumbs
        items={[
          { label: "Platform", href: "/" },
          { label: "Metrics" },
        ]}
      />,
    );
    const link = screen.getByRole("link", { name: "Platform" });
    expect(link).toHaveAttribute("href", "/");
  });

  it("renders the last item as plain text with primary styling", () => {
    render(
      <Breadcrumbs
        items={[
          { label: "Platform", href: "/" },
          { label: "Metrics" },
        ]}
      />,
    );
    const terminal = screen.getByText("Metrics");
    expect(terminal.tagName).toBe("SPAN");
    expect(terminal).toHaveClass("text-text-primary");
    expect(terminal).toHaveClass("font-medium");
  });

  it("renders slash separators between items", () => {
    const { container } = render(
      <Breadcrumbs
        items={[
          { label: "A", href: "/" },
          { label: "B", href: "/b" },
          { label: "C" },
        ]}
      />,
    );
    const separators = container.querySelectorAll(".text-text-muted");
    // Two separators for three items
    const slashes = Array.from(separators).filter(
      (el) => el.textContent === "/",
    );
    expect(slashes).toHaveLength(2);
  });

  it("does not render a separator before the first item", () => {
    const { container } = render(
      <Breadcrumbs items={[{ label: "Home" }]} />,
    );
    expect(container.textContent).toBe("Home");
  });

  it("renders intermediate items without href as spans", () => {
    render(
      <Breadcrumbs
        items={[
          { label: "Section" },
          { label: "Page" },
        ]}
      />,
    );
    const section = screen.getByText("Section");
    expect(section.tagName).toBe("SPAN");
    expect(section).toHaveClass("text-text-secondary");
  });

  it("applies secondary text color to intermediate links", () => {
    render(
      <Breadcrumbs
        items={[
          { label: "Root", href: "/" },
          { label: "Current" },
        ]}
      />,
    );
    const link = screen.getByRole("link", { name: "Root" });
    expect(link).toHaveClass("text-text-secondary");
  });
});
