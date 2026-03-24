import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Pagination } from "../pagination";

describe("Pagination", () => {
  it("renders navigation element with pagination label", () => {
    render(<Pagination total={100} current={1} onPageChange={() => {}} />);
    expect(screen.getByRole("navigation", { name: "Pagination" })).toBeInTheDocument();
  });

  it("renders correct number of page buttons for small total", () => {
    render(<Pagination total={125} current={1} onPageChange={() => {}} pageSize={25} />);
    // 5 pages + prev + next = 7 buttons
    expect(screen.getAllByRole("button")).toHaveLength(7);
  });

  it("highlights current page with accent background", () => {
    render(<Pagination total={100} current={2} onPageChange={() => {}} pageSize={25} />);
    const currentBtn = screen.getByLabelText("Page 2");
    expect(currentBtn).toHaveClass("bg-accent");
    expect(currentBtn).toHaveAttribute("aria-current", "page");
  });

  it("fires onPageChange when page button is clicked", () => {
    const handleChange = vi.fn();
    render(<Pagination total={100} current={1} onPageChange={handleChange} pageSize={25} />);
    fireEvent.click(screen.getByLabelText("Page 3"));
    expect(handleChange).toHaveBeenCalledWith(3);
  });

  it("fires onPageChange with previous page on Previous click", () => {
    const handleChange = vi.fn();
    render(<Pagination total={100} current={3} onPageChange={handleChange} pageSize={25} />);
    fireEvent.click(screen.getByLabelText("Go to previous page"));
    expect(handleChange).toHaveBeenCalledWith(2);
  });

  it("fires onPageChange with next page on Next click", () => {
    const handleChange = vi.fn();
    render(<Pagination total={100} current={2} onPageChange={handleChange} pageSize={25} />);
    fireEvent.click(screen.getByLabelText("Go to next page"));
    expect(handleChange).toHaveBeenCalledWith(3);
  });

  it("disables Previous button on first page", () => {
    render(<Pagination total={100} current={1} onPageChange={() => {}} pageSize={25} />);
    expect(screen.getByLabelText("Go to previous page")).toBeDisabled();
  });

  it("disables Next button on last page", () => {
    render(<Pagination total={100} current={4} onPageChange={() => {}} pageSize={25} />);
    expect(screen.getByLabelText("Go to next page")).toBeDisabled();
  });

  it("renders ellipsis for large page ranges", () => {
    render(<Pagination total={500} current={5} onPageChange={() => {}} pageSize={25} />);
    const ellipses = screen.getAllByText("…");
    expect(ellipses.length).toBeGreaterThanOrEqual(1);
  });

  it("returns null when total fits in single page", () => {
    const { container } = render(
      <Pagination total={10} current={1} onPageChange={() => {}} pageSize={25} />,
    );
    expect(container.firstChild).toBeNull();
  });
});
