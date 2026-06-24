import { describe, it, expect } from "vitest";
import viz from "./fixtures/viz.json";
import index from "./fixtures/index.json";
import type { VizData, IndexFile } from "../src/types";

describe("contract fixtures", () => {
  it("viz.json 有必要欄位", () => {
    const v = viz as unknown as VizData;
    expect(v.slug).toBeTruthy();
    expect(Array.isArray(v.nodes)).toBe(true);
    expect(Array.isArray(v.edges)).toBe(true);
    expect(typeof v.diag).toBe("object");
    expect(v.nodes[0]).toHaveProperty("type");
    expect(v.nodes[0]).toHaveProperty("evidence");
  });
  it("index.json 有 stories[]", () => {
    const i = index as unknown as IndexFile;
    expect(i.stories.length).toBeGreaterThan(0);
    expect(i.stories[0]).toHaveProperty("slug");
    expect(i.stories[0]).toHaveProperty("has_viz");
  });
});
