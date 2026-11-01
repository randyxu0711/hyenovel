import { describe, it, expect } from "vitest";
import { cpLength, cpSlice, cpToUnit } from "../src/dash/cp";

describe("code point 工具", () => {
  it("長度與切片以 code point 計(補充平面字算 1)", () => {
    expect(cpLength("𠀋石")).toBe(2);
    expect(cpSlice("𠀋石頭", 1, 3)).toBe("石頭");
    expect(cpSlice("𠀋石頭", 1)).toBe("石頭");
    expect(cpSlice("𠀋石頭", -5, 2)).toBe("𠀋石");
    expect(cpSlice("𠀋石頭", 2, 1)).toBe("");
  });
  it("cpToUnit 轉 UTF-16 位移;越界夾到字串長度", () => {
    expect(cpToUnit("𠀋石", 0)).toBe(0);
    expect(cpToUnit("𠀋石", 1)).toBe(2);
    expect(cpToUnit("𠀋石", 2)).toBe(3);
    expect(cpToUnit("𠀋石", 99)).toBe(3);
    expect(cpToUnit("𠀋石", -1)).toBe(0);
  });
});
