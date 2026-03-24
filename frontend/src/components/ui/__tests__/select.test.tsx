import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Select } from "../select";

const options = [
  { label: "Standard", value: "standard" },
  { label: "Chain of Responsibility", value: "chain" },
  { label: "Neural Network", value: "neural" },
];

describe("Select", () => {
  it("renders trigger button with combobox role", () => {
    render(<Select options={options} value="" onChange={() => {}} />);
    expect(screen.getByRole("combobox")).toBeInTheDocument();
  });

  it("displays placeholder when no value is selected", () => {
    render(<Select options={options} value="" onChange={() => {}} placeholder="Choose strategy" />);
    expect(screen.getByText("Choose strategy")).toBeInTheDocument();
  });

  it("displays selected option label in trigger", () => {
    render(<Select options={options} value="chain" onChange={() => {}} />);
    expect(screen.getByText("Chain of Responsibility")).toBeInTheDocument();
  });

  it("dropdown is closed by default", () => {
    render(<Select options={options} value="" onChange={() => {}} />);
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("opens dropdown on trigger click", () => {
    render(<Select options={options} value="" onChange={() => {}} />);
    fireEvent.click(screen.getByRole("combobox"));
    expect(screen.getByRole("listbox")).toBeInTheDocument();
  });

  it("renders all options in the dropdown", () => {
    render(<Select options={options} value="" onChange={() => {}} />);
    fireEvent.click(screen.getByRole("combobox"));
    expect(screen.getAllByRole("option")).toHaveLength(3);
  });

  it("fires onChange with selected value on option click", () => {
    const handleChange = vi.fn();
    render(<Select options={options} value="" onChange={handleChange} />);
    fireEvent.click(screen.getByRole("combobox"));
    fireEvent.click(screen.getByText("Neural Network"));
    expect(handleChange).toHaveBeenCalledWith("neural");
  });

  it("closes dropdown after selection", () => {
    render(<Select options={options} value="" onChange={() => {}} />);
    fireEvent.click(screen.getByRole("combobox"));
    fireEvent.click(screen.getByText("Standard"));
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("closes dropdown on Escape key", () => {
    render(<Select options={options} value="" onChange={() => {}} />);
    fireEvent.click(screen.getByRole("combobox"));
    const root = screen.getByRole("combobox").closest("div")!;
    fireEvent.keyDown(root, { key: "Escape" });
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("navigates options with ArrowDown key", () => {
    render(<Select options={options} value="" onChange={() => {}} />);
    fireEvent.click(screen.getByRole("combobox"));
    const root = screen.getByRole("combobox").closest("div")!;
    fireEvent.keyDown(root, { key: "ArrowDown" });
    // Highlight should move down — option 1 should have highlight class
    const opts = screen.getAllByRole("option");
    expect(opts[1]).toHaveClass("border-l-accent");
  });

  it("selects highlighted option with Enter key", () => {
    const handleChange = vi.fn();
    render(<Select options={options} value="" onChange={handleChange} />);
    fireEvent.click(screen.getByRole("combobox"));
    const root = screen.getByRole("combobox").closest("div")!;
    fireEvent.keyDown(root, { key: "ArrowDown" });
    fireEvent.keyDown(root, { key: "Enter" });
    expect(handleChange).toHaveBeenCalledWith("chain");
  });

  it("renders search input when searchable prop is enabled", () => {
    render(<Select options={options} value="" onChange={() => {}} searchable />);
    fireEvent.click(screen.getByRole("combobox"));
    expect(screen.getByLabelText("Filter options")).toBeInTheDocument();
  });

  it("sets aria-expanded on trigger", () => {
    render(<Select options={options} value="" onChange={() => {}} />);
    const trigger = screen.getByRole("combobox");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
  });

  it("marks selected option with aria-selected", () => {
    render(<Select options={options} value="neural" onChange={() => {}} />);
    fireEvent.click(screen.getByRole("combobox"));
    const opts = screen.getAllByRole("option");
    const selectedOpt = opts.find((o) => o.textContent === "Neural Network")!;
    expect(selectedOpt).toHaveAttribute("aria-selected", "true");
  });
});
