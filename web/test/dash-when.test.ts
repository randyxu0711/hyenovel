import { describe, it, expect } from "vitest";
import { whenLabel } from "../src/dash/when";
import { fpPoints } from "../src/dash/Rail";

const at = (y: number, m: number, d: number, h = 12) => new Date(y, m - 1, d, h).getTime() / 1000;
const NOW = at(2026, 11, 2, 9);

describe("whenLabel", () => {
  it("今天 / 昨天 / N 天前 / M/D / 跨年(本地日界)", () => {
    expect(whenLabel(at(2026, 11, 2, 0), NOW, "zh-Hant")).toBe("今天");
    expect(whenLabel(at(2026, 11, 1, 23), NOW, "zh-Hant")).toBe("昨天");
    expect(whenLabel(at(2026, 10, 30), NOW, "zh-Hant")).toBe("3 天前");
    expect(whenLabel(at(2026, 10, 27), NOW, "zh-Hant")).toBe("6 天前");
    expect(whenLabel(at(2026, 10, 23), NOW, "zh-Hant")).toBe("10/23");
    expect(whenLabel(at(2025, 12, 3), NOW, "zh-Hant")).toBe("2025/12/3");
  });
  it("英文", () => {
    expect(whenLabel(at(2026, 11, 2), NOW, "en")).toBe("Today");
    expect(whenLabel(at(2026, 11, 1), NOW, "en")).toBe("Yesterday");
    expect(whenLabel(at(2026, 10, 30), NOW, "en")).toBe("3d ago");
    expect(whenLabel(at(2026, 10, 23), NOW, "en")).toBe("10/23");
  });
});

describe("fpPoints", () => {
  it("兩點以上才畫;x 平均鋪滿、y 由下往上", () => {
    expect(fpPoints([0, 1], 10, 14)).toBe("0,14 10,0");
    expect(fpPoints([0.5, 0.5, 0.5], 10, 14)).toBe("0,7 5,7 10,7");
    expect(fpPoints([], 10, 14)).toBe("");
    expect(fpPoints([0.5], 10, 14)).toBe("");
  });
});
