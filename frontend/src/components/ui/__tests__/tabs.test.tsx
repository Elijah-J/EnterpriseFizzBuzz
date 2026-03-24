import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Tabs } from "../tabs";

const items = [
  { label: "Overview", content: <div>Overview panel</div> },
  { label: "Metrics", content: <div>Metrics panel</div> },
  { label: "Traces", content: <div>Traces panel</div> },
];

describe("Tabs", () => {
  it("renders tab list with all tab triggers", () => {
    render(<Tabs items={items} />);
    expect(screen.getByRole("tablist")).toBeInTheDocument();
    expect(screen.getAllByRole("tab")).toHaveLength(3);
  });

  it("renders tab panels for all items", () => {
    render(<Tabs items={items} />);
    expect(screen.getAllByRole("tabpanel", { hidden: true })).toHaveLength(3);
  });

  it("displays the first tab as active by default", () => {
    render(<Tabs items={items} />);
    const tabs = screen.getAllByRole("tab");
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
    expect(tabs[1]).toHaveAttribute("aria-selected", "false");
  });

  it("shows the active panel content and hides others", () => {
    render(<Tabs items={items} />);
    expect(screen.getByText("Overview panel")).toBeVisible();
    expect(screen.getByText("Metrics panel").closest("[role='tabpanel']")).toHaveAttribute("hidden");
  });

  it("switches panel on tab click", () => {
    render(<Tabs items={items} />);
    fireEvent.click(screen.getByText("Metrics"));
    expect(screen.getByText("Metrics panel")).toBeVisible();
    expect(screen.getByText("Overview panel").closest("[role='tabpanel']")).toHaveAttribute("hidden");
  });

  it("fires onChange callback on tab switch", () => {
    const handleChange = vi.fn();
    render(<Tabs items={items} onChange={handleChange} />);
    fireEvent.click(screen.getByText("Traces"));
    expect(handleChange).toHaveBeenCalledWith(2);
  });

  it("respects defaultIndex prop", () => {
    render(<Tabs items={items} defaultIndex={2} />);
    expect(screen.getAllByRole("tab")[2]).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Traces panel")).toBeVisible();
  });

  it("sets aria-controls linking tab to panel", () => {
    render(<Tabs items={items} />);
    const tab = screen.getAllByRole("tab")[0];
    const panelId = tab.getAttribute("aria-controls");
    expect(panelId).toBeTruthy();
    expect(document.getElementById(panelId!)).toBeInTheDocument();
  });

  it("navigates to next tab with ArrowRight key", () => {
    render(<Tabs items={items} />);
    const tablist = screen.getByRole("tablist");
    fireEvent.keyDown(tablist, { key: "ArrowRight" });
    expect(screen.getAllByRole("tab")[1]).toHaveAttribute("aria-selected", "true");
  });

  it("navigates to previous tab with ArrowLeft key", () => {
    render(<Tabs items={items} defaultIndex={2} />);
    const tablist = screen.getByRole("tablist");
    fireEvent.keyDown(tablist, { key: "ArrowLeft" });
    expect(screen.getAllByRole("tab")[1]).toHaveAttribute("aria-selected", "true");
  });

  it("navigates to first tab with Home key", () => {
    render(<Tabs items={items} defaultIndex={2} />);
    const tablist = screen.getByRole("tablist");
    fireEvent.keyDown(tablist, { key: "Home" });
    expect(screen.getAllByRole("tab")[0]).toHaveAttribute("aria-selected", "true");
  });

  it("navigates to last tab with End key", () => {
    render(<Tabs items={items} />);
    const tablist = screen.getByRole("tablist");
    fireEvent.keyDown(tablist, { key: "End" });
    expect(screen.getAllByRole("tab")[2]).toHaveAttribute("aria-selected", "true");
  });

  it("wraps around with ArrowRight on last tab", () => {
    render(<Tabs items={items} defaultIndex={2} />);
    const tablist = screen.getByRole("tablist");
    fireEvent.keyDown(tablist, { key: "ArrowRight" });
    expect(screen.getAllByRole("tab")[0]).toHaveAttribute("aria-selected", "true");
  });

  it("renders animated indicator bar", () => {
    render(<Tabs items={items} />);
    const tablist = screen.getByRole("tablist");
    const indicator = tablist.querySelector("[aria-hidden='true']");
    expect(indicator).toBeInTheDocument();
    expect(indicator).toHaveClass("bg-accent");
  });
});
