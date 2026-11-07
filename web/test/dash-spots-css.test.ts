import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const css = readFileSync(join(__dirname, "../src/dash/dash.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");

describe("斑點只在進門", () => {
  it("用到 --dash-spots 的規則都限定 data-view=home", () => {
    const rules = [...css.matchAll(/([^{}]+)\{([^{}]*var\(--dash-spots[^{}]*)\}/g)];
    expect(rules.length).toBeGreaterThan(0);
    for (const [, sel] of rules) expect(sel.trim()).toBe('.dash[data-view="home"]');
  });
});
