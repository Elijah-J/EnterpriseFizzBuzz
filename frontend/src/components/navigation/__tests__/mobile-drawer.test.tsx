import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MobileDrawer } from "../mobile-drawer";

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

// Mock next/navigation
const mockPathname = vi.fn(() => "/");
vi.mock("next/navigation", () => ({
  usePathname: () => mockPathname(),
}));

// Mock sidebar-icons
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

describe("MobileDrawer", () => {
  beforeEach(() => {
    mockPathname.mockReturnValue("/");
  });

  it("renders nothing when closed", () => {
    const { container } = render(
      <MobileDrawer open={false} onClose={vi.fn()} />,
    );
    expect(container.innerHTML).toBe("");
  });

  it("renders the drawer panel when open", () => {
    render(<MobileDrawer open={true} onClose={vi.fn()} />);
    expect(screen.getByText("Operations")).toBeInTheDocument();
  });

  it("renders all five navigation section headings", () => {
    render(<MobileDrawer open={true} onClose={vi.fn()} />);
    expect(screen.getByText("Operations")).toBeInTheDocument();
    expect(screen.getByText("Monitor")).toBeInTheDocument();
    expect(screen.getByText("Platform")).toBeInTheDocument();
    expect(screen.getByText("Finance")).toBeInTheDocument();
    expect(screen.getByText("Research")).toBeInTheDocument();
  });

  it("renders all 21 navigation links", () => {
    render(<MobileDrawer open={true} onClose={vi.fn()} />);
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(21);
  });

  it("renders Dashboard link with root href", () => {
    render(<MobileDrawer open={true} onClose={vi.fn()} />);
    const link = screen.getByRole("link", { name: /Dashboard/ });
    expect(link).toHaveAttribute("href", "/");
  });

  it("highlights the active link", () => {
    mockPathname.mockReturnValue("/blockchain");
    render(<MobileDrawer open={true} onClose={vi.fn()} />);
    const link = screen.getByRole("link", { name: /Blockchain/ });
    expect(link).toHaveClass("bg-surface-raised");
    expect(link).toHaveClass("text-text-primary");
  });

  it("calls onClose when backdrop is clicked", () => {
    const onClose = vi.fn();
    const { container } = render(
      <MobileDrawer open={true} onClose={onClose} />,
    );
    const backdrop = container.querySelector(".bg-surface-ground\\/60");
    fireEvent.click(backdrop!);
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("calls onClose when Escape key is pressed", () => {
    const onClose = vi.fn();
    render(<MobileDrawer open={true} onClose={onClose} />);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("always shows labels in the drawer (not collapsed)", () => {
    render(<MobileDrawer open={true} onClose={vi.fn()} />);
    expect(screen.getByText("Evaluation Console")).toBeInTheDocument();
    expect(screen.getByText("Quantum Workbench")).toBeInTheDocument();
  });

  it("renders icons for each navigation item", () => {
    render(<MobileDrawer open={true} onClose={vi.fn()} />);
    const icons = screen.getAllByTestId("mock-icon");
    expect(icons.length).toBeGreaterThanOrEqual(21);
  });
});
