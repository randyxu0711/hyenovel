import { describe, it, expect } from "vitest";
import { fmtDelta, fmtPct, fmtSeconds, fmtTokens } from "../src/dash/usageFormat";

describe("用量數字格式", () => {
  it("萬以上用萬(一位小數),以下千分位;en 一律千分位", () => {
    expect(fmtTokens(492000, "zh-Hant")).toBe("49.2 萬");
    expect(fmtTokens(6040, "zh-Hant")).toBe("6,040");
    expect(fmtTokens(10000, "zh-Hant")).toBe("1.0 萬");
    expect(fmtTokens(492000, "en")).toBe("492,000");
  });
  it("占比整數 %,增減帶正負號(負號 U+2212)", () => {
    expect(fmtPct(0.456)).toBe("46%");
    expect(fmtDelta(0.14)).toBe("+14%");
    expect(fmtDelta(-0.11)).toBe("−11%");
    expect(fmtDelta(-0.001)).toBe("+0%");
  });
  it("延遲:百秒以上取整,以下一位小數", () => {
    expect(fmtSeconds(212_400)).toBe("212");
    expect(fmtSeconds(9_800)).toBe("9.8");
  });
});
