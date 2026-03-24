import { describe, it, expect, vi } from "vitest";
import { render, fireEvent } from "@testing-library/react";
import { ZoomBrush } from "../zoom-brush";

function renderBrush(props: Partial<React.ComponentProps<typeof ZoomBrush>> = {}) {
  return render(
    <svg width={400} height={200}>
      <ZoomBrush
        width={360}
        y={180}
        height={20}
        marginLeft={40}
        onZoom={vi.fn()}
        onReset={vi.fn()}
        {...props}
      />
    </svg>,
  );
}

describe("ZoomBrush", () => {
  it("renders a selection rect within the SVG", () => {
    const { container } = renderBrush();
    const rects = container.querySelectorAll("rect");
    expect(rects.length).toBeGreaterThanOrEqual(1);
  });

  it("calls onReset on double-click", () => {
    const onReset = vi.fn();
    const { container } = renderBrush({ onReset });
    const rect = container.querySelector("rect");
    if (rect) {
      fireEvent.doubleClick(rect);
      expect(onReset).toHaveBeenCalled();
    }
  });
});
