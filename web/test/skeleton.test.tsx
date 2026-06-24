import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import Skeleton from "../src/viz/Skeleton";

describe("Skeleton", () => {
  it("依 beats 數畫出點", () => {
    const { container } = render(<Skeleton beats={[0.2, 0.6, 0.9]} width={200} />);
    expect(container.querySelector("svg")).toBeTruthy();
    expect(container.querySelectorAll("circle").length).toBe(3);
    expect(container.querySelector("path")).toBeTruthy();
  });
  it("每隔一點畫一條肋線", () => {
    const { container } = render(<Skeleton beats={[0.2, 0.6, 0.9, 0.4]} width={200} />);
    // i%2===0 → index 0,2 → 2 條肋
    expect(container.querySelectorAll("line.rib").length).toBe(2);
  });
});
