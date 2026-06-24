import { describe, it, expect } from "vitest";
import { resolveDataPath } from "../vite-plugin-data";

describe("resolveDataPath", () => {
  it("rejects traversal attempts", () => {
    expect(resolveDataPath("/../secret")).toBeNull();
    expect(resolveDataPath("/../../etc/passwd")).toBeNull();
  });
  it("resolves a normal data path under stories/", () => {
    const p = resolveDataPath("/s02/viz.json");
    expect(p).toBeTruthy();
    expect(p!.replace(/\\/g, "/").endsWith("stories/s02/viz.json")).toBe(true);
  });
});
