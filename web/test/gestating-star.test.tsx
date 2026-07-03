import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import GestatingStar from "../src/journey/GestatingStar";

const ribs = (c: HTMLElement) => [...c.querySelectorAll(".gs-rib")] as SVGElement[];
const nodes = (c: HTMLElement) => [...c.querySelectorAll(".gs-node")];

describe("GestatingStar", () => {
  it("step1:脊椎已描,肋與節點未出", () => {
    const { container } = render(<GestatingStar step={1} />);
    expect(container.querySelector(".gs")?.getAttribute("data-step")).toBe("1");
    expect(ribs(container).every(r => r.style.opacity === "0")).toBe(true);
    expect(nodes(container).every(n => n.getAttribute("r") === "0")).toBe(true);
  });
  it("step2:肋抽長(opacity .76),節點仍未出", () => {
    const { container } = render(<GestatingStar step={2} />);
    expect(ribs(container).every(r => r.style.opacity === "0.76")).toBe(true);
    expect(nodes(container).every(n => n.getAttribute("r") === "0")).toBe(true);
  });
  it("step3:節點冒出(r>0)", () => {
    const { container } = render(<GestatingStar step={3} />);
    expect(nodes(container).some(n => Number(n.getAttribute("r")) > 0)).toBe(true);
  });
  it("step4:點亮(lit)", () => {
    const { container } = render(<GestatingStar step={4} />);
    expect(container.querySelector(".gs")?.classList.contains("lit")).toBe(true);
  });
});
