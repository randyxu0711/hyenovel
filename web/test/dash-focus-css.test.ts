import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const css = readFileSync(join(__dirname, "../src/dash/dash.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");

describe("專注轉場不拖累分隔線拖曳", () => {
  it("grid-template-columns 的 transition 只掛在專注的選擇器上", () => {
    const rules = [...css.matchAll(/([^{}]+)\{([^{}]*transition:[^{}]*grid-template-columns[^{}]*)\}/g)];
    expect(rules.length).toBeGreaterThan(0);
    for (const [, sel] of rules) expect(sel.trim()).toMatch(/data-focus="true"/);
  });
});
