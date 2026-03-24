import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Sidebar } from "../sidebar";

// Mock next/link as a passthrough anchor
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

// Mock next/navigation
const mockPathname = vi.fn(() => "/");
vi.mock("next/navigation", () => ({
  usePathname: () => mockPathname(),
}));

// Mock sidebar-icons as simple SVG stubs
vi.mock("../sidebar-icons", () => {
  const icon = ({ className }: { className?: string }) => (
    <svg data-testid="mock-icon" className={className} />
  );
  return {
    AlertsIcon: icon,
    AnalyticsIcon: icon,
    ArchaeologyIcon: icon,
    AuditIcon: icon,
    BlockchainIcon: icon,
    CacheIcon: icon,
    ChaosIcon: icon,
    ComplianceIcon: icon,
    ConfigurationIcon: icon,
    ConsensusIcon: icon,
    DashboardIcon: icon,
    DigitalTwinIcon: icon,
    EvaluateIcon: icon,
    EvolutionIcon: icon,
    FederatedLearningIcon: icon,
    FinOpsIcon: icon,
    MetricsIcon: icon,
    MonitorIcon: icon,
    QuantumIcon: icon,
    TracesIcon: icon,
  };
});

// Mock tooltip as passthrough
vi.mock("@/components/ui/tooltip", () => ({
  Tooltip: ({
    children,
    content,
  }: {
    children: React.ReactNode;
    content: string;
  }) => <div data-tooltip={content}>{children}</div>,
}));

describe("Sidebar", () => {
  it("renders as an aside element", () => {
    const { container } = render(
      <Sidebar collapsed={false} onToggle={vi.fn()} />,
    );
    expect(container.querySelector("aside")).toBeInTheDocument();
  });

  it("renders the main navigation landmark", () => {
    render(<Sidebar collapsed={false} onToggle={vi.fn()} />);
    expect(screen.getByRole("navigation", { name: "Main" })).toBeInTheDocument();
  });

  it("renders all five section headings when expanded", () => {
    render(<Sidebar collapsed={false} onToggle={vi.fn()} />);
    expect(screen.getByText("Operations")).toBeInTheDocument();
    expect(screen.getByText("Monitor")).toBeInTheDocument();
    expect(screen.getByText("Platform")).toBeInTheDocument();
    expect(screen.getByText("Finance")).toBeInTheDocument();
    expect(screen.getByText("Research")).toBeInTheDocument();
  });

  it("hides section headings when collapsed", () => {
    render(<Sidebar collapsed={true} onToggle={vi.fn()} />);
    expect(screen.queryByText("Operations")).not.toBeInTheDocument();
    expect(screen.queryByText("Monitor")).not.toBeInTheDocument();
    expect(screen.queryByText("Platform")).not.toBeInTheDocument();
  });

  it("renders 21 navigation links", () => {
    render(<Sidebar collapsed={false} onToggle={vi.fn()} />);
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(21);
  });

  it("renders Dashboard link pointing to root", () => {
    render(<Sidebar collapsed={false} onToggle={vi.fn()} />);
    const dashboardLink = screen.getByRole("link", { name: /Dashboard/ });
    expect(dashboardLink).toHaveAttribute("href", "/");
  });

  it("applies expanded width class when not collapsed", () => {
    const { container } = render(
      <Sidebar collapsed={false} onToggle={vi.fn()} />,
    );
    expect(container.querySelector("aside")).toHaveClass("lg:w-60");
  });

  it("applies collapsed width class when collapsed", () => {
    const { container } = render(
      <Sidebar collapsed={true} onToggle={vi.fn()} />,
    );
    expect(container.querySelector("aside")).toHaveClass("lg:w-14");
  });

  it("renders collapse toggle button with correct aria-label when expanded", () => {
    render(<Sidebar collapsed={false} onToggle={vi.fn()} />);
    expect(
      screen.getByRole("button", { name: "Collapse sidebar" }),
    ).toBeInTheDocument();
  });

  it("renders expand toggle button with correct aria-label when collapsed", () => {
    render(<Sidebar collapsed={true} onToggle={vi.fn()} />);
    expect(
      screen.getByRole("button", { name: "Expand sidebar" }),
    ).toBeInTheDocument();
  });

  it("calls onToggle when collapse button is clicked", () => {
    const onToggle = vi.fn();
    render(<Sidebar collapsed={false} onToggle={onToggle} />);
    fireEvent.click(screen.getByRole("button", { name: "Collapse sidebar" }));
    expect(onToggle).toHaveBeenCalledOnce();
  });

  it("highlights the active link based on pathname", () => {
    mockPathname.mockReturnValue("/analytics");
    render(<Sidebar collapsed={false} onToggle={vi.fn()} />);
    const analyticsLink = screen.getByRole("link", { name: /Analytics/ });
    expect(analyticsLink).toHaveClass("bg-surface-raised");
    expect(analyticsLink).toHaveClass("text-text-primary");
  });

  it("does not highlight inactive links", () => {
    mockPathname.mockReturnValue("/");
    render(<Sidebar collapsed={false} onToggle={vi.fn()} />);
    const analyticsLink = screen.getByRole("link", { name: /Analytics/ });
    expect(analyticsLink).toHaveClass("text-text-secondary");
  });

  it("shows version text in expanded mode", () => {
    render(<Sidebar collapsed={false} onToggle={vi.fn()} />);
    expect(screen.getByText("v0.1.0")).toBeInTheDocument();
  });

  it("shows abbreviated version in collapsed mode", () => {
    render(<Sidebar collapsed={true} onToggle={vi.fn()} />);
    expect(screen.getByText("0.1")).toBeInTheDocument();
  });

  it("wraps collapsed links in tooltips", () => {
    render(<Sidebar collapsed={true} onToggle={vi.fn()} />);
    const tooltips = document.querySelectorAll("[data-tooltip]");
    expect(tooltips.length).toBeGreaterThanOrEqual(21);
  });

  it("hides link labels when collapsed", () => {
    render(<Sidebar collapsed={true} onToggle={vi.fn()} />);
    // In collapsed mode, nav item text labels should not be rendered
    expect(screen.queryByText("Evaluation Console")).not.toBeInTheDocument();
  });

  it("shows link labels when expanded", () => {
    render(<Sidebar collapsed={false} onToggle={vi.fn()} />);
    expect(screen.getByText("Evaluation Console")).toBeInTheDocument();
    expect(screen.getByText("Quantum Workbench")).toBeInTheDocument();
    expect(screen.getByText("Archaeological Recovery")).toBeInTheDocument();
  });
});
