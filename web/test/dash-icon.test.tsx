import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import Icon, { ICON_NAMES } from "../src/dash/Icon";

describe("Icon", () => {
  it("每個名字都畫出 18×18、aria-hidden 的 svg,且有筆畫", () => {
    for (const name of ICON_NAMES) {
      const { container, unmount } = render(<Icon name={name} />);
      const svg = container.querySelector("svg")!;
      expect(svg.getAttribute("viewBox")).toBe("0 0 18 18");
      expect(svg.getAttribute("width")).toBe("18");
      expect(svg.getAttribute("aria-hidden")).toBe("true");
      expect(svg.querySelector("path, circle, rect"), name).not.toBeNull();
      unmount();
    }
  });
  it("有第 3 批的四顆", () => {
    for (const n of ["send", "stop", "focus", "sheet2"]) expect(ICON_NAMES).toContain(n);
  });
  it("auto 的右半是實心", () => {
    const { container } = render(<Icon name="auto" />);
    expect(container.querySelector('path[fill="currentColor"]')).not.toBeNull();
  });
});
