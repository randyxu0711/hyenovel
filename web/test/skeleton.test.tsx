import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import Skeleton from "../src/viz/Skeleton";

describe("Skeleton", () => {
  it("畫出脊椎與肋骨(魚骨骨架)", () => {
    const { container } = render(<Skeleton seed={42} width={200} />);
    expect(container.querySelector("path.spine")).toBeTruthy();
    const ribs = container.querySelectorAll("line.rib").length;
    expect(ribs).toBeGreaterThanOrEqual(6);
    // 每根肋一個端點
    expect(container.querySelectorAll("circle").length).toBe(ribs);
  });
});
