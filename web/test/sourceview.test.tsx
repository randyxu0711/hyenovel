import { describe, it, expect, beforeEach, vi } from "vitest";
import { render } from "@testing-library/react";
import SourceView from "../src/journey/SourceView";

beforeEach(() => { Element.prototype.scrollIntoView = vi.fn(); });

describe("SourceView", () => {
  it("無 highlight 時純文字,無 mark", () => {
    const { container } = render(<SourceView source="海伊先生說。" highlight={null} />);
    expect(container.querySelector("mark.hl")).toBeNull();
    expect(container.textContent).toContain("海伊先生說。");
  });
  it("有 highlight 時命中段包在 mark.hl", () => {
    const src = "海伊先生說,鬣狗到湖邊。";
    const { container } = render(<SourceView source={src} highlight={{ start: 5, end: 7 }} />);
    const m = container.querySelector("mark.hl");
    expect(m).toBeTruthy();
    expect(m!.textContent).toBe(src.slice(5, 7));
  });
});
