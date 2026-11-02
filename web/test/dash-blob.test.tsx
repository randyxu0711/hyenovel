import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import Blob, { blobPath } from "../src/dash/Blob";
import { hyena, ch } from "./dash-fixtures";

describe("blobPath", () => {
  it("同 seed 同形、不同 seed 不同形", () => {
    expect(blobPath("hyena")).toBe(blobPath("hyena"));
    expect(blobPath("hyena")).not.toBe(blobPath("deer"));
  });
  it("M 開頭、七段曲線、不自己收 Z", () => {
    const d = blobPath("hyena");
    expect(d.startsWith("M")).toBe(true);
    expect(d).not.toContain("Z");
    expect(d.match(/ C/g)).toHaveLength(7);
  });
  it("座標都在 viewBox 0 0 100 90 內", () => {
    for (const seed of ["hyena", "buffalo", "deer", "x", ""]) {
      const nums = blobPath(seed).match(/-?\d+(\.\d+)?/g)!.map(Number);
      for (let i = 0; i < nums.length; i += 2) {
        expect(nums[i]).toBeGreaterThanOrEqual(0);
        expect(nums[i]).toBeLessThanOrEqual(100);
        expect(nums[i + 1]).toBeGreaterThanOrEqual(0);
        expect(nums[i + 1]).toBeLessThanOrEqual(90);
      }
    }
  });
});

describe("Blob", () => {
  it("帶狀態、角色色、對讀屏隱藏", () => {
    const { container } = render(<Blob character={hyena} state="speaking" />);
    const svg = container.querySelector("svg.blob")!;
    expect(svg.getAttribute("data-state")).toBe("speaking");
    expect(svg.getAttribute("aria-hidden")).toBe("true");
    expect(svg.getAttribute("style")).toContain("--char");
    expect(svg.querySelector("path.body")).not.toBeNull();
    expect(svg.querySelectorAll("ellipse.eye")).toHaveLength(2);
    expect(svg.querySelector("path.mouth")).not.toBeNull();
  });
  it("不給狀態就是 idle", () => {
    const { container } = render(<Blob character={hyena} />);
    expect(container.querySelector("svg.blob")!.getAttribute("data-state")).toBe("idle");
  });
  it("未知 avatar.kind 的角色照常畫", () => {
    const { container } = render(<Blob character={ch("fox", "slow", "狐狸", "Fox", "zzz")} />);
    expect(container.querySelector("svg.blob path.body")).not.toBeNull();
  });
});
