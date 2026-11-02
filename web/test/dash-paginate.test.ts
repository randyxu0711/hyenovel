import { describe, it, expect } from "vitest";
import { paginate, tcyRuns, type PageSeg } from "../src/dash/paginate";
import { cpLength } from "../src/dash/cp";

const upTo = (n: number) => (page: PageSeg[]) => page.reduce((a, s) => a + cpLength(s.text), 0) <= n;
const lens = (pages: PageSeg[][]) => pages.map(p => p.map(s => cpLength(s.text)));

describe("paginate", () => {
  it("全部放得下 → 一頁、cont 全 false", () => {
    const pages = paginate([{ start: 0, text: "一二" }, { start: 3, text: "三四" }], upTo(10));
    expect(lens(pages)).toEqual([[2, 2]]);
    expect(pages[0].every(s => !s.cont)).toBe(true);
  });

  it("沒有段 → 沒有頁", () => {
    expect(paginate([], upTo(10))).toEqual([]);
  });

  it("段長 4,4,4、每頁 10 字 → 第三段切開,續段 start 往後推", () => {
    const segs = [{ start: 0, text: "甲甲甲甲" }, { start: 5, text: "乙乙乙乙" }, { start: 10, text: "丙丙丙丙" }];
    const pages = paginate(segs, upTo(10));
    expect(lens(pages)).toEqual([[4, 4, 2], [2]]);
    expect(pages[1][0]).toEqual({ start: 12, text: "丙丙", cont: true });
    expect(pages[0][2].cont).toBe(false);
  });

  it("下一段一個字都放不進本頁 → 整段搬到下一頁,不算續段", () => {
    const pages = paginate([{ start: 0, text: "甲".repeat(8) }, { start: 9, text: "乙乙乙乙乙" }], upTo(8));
    expect(lens(pages)).toEqual([[8], [5]]);
    expect(pages[1][0]).toEqual({ start: 9, text: "乙乙乙乙乙", cont: false });
  });

  it("一段比整頁長 → 切成多頁,不會卡住", () => {
    const text = "字".repeat(25);
    const pages = paginate([{ start: 7, text }], upTo(10));
    expect(lens(pages)).toEqual([[10], [10], [5]]);
    expect(pages.map(p => p[0].start)).toEqual([7, 17, 27]);
  });

  it("fits 永遠 false → 每頁一個字,仍會結束", () => {
    const pages = paginate([{ start: 0, text: "一二三" }], () => false);
    expect(lens(pages)).toEqual([[1], [1], [1]]);
  });

  it("代理對字元切在 code point 上,拼回去等於原文", () => {
    const text = "𠀀𠀁𠀂𠀃𠀄";
    const pages = paginate([{ start: 0, text }], upTo(2));
    expect(pages.flat().map(s => s.text).join("")).toBe(text);
    expect(lens(pages)).toEqual([[2], [2], [1]]);
  });
});

describe("tcyRuns", () => {
  const tcy = (s: string) => tcyRuns(s).filter(r => r.tcy).map(r => r.text);
  it("1–2 位半形數字、前後不接英數 → 直立", () => {
    expect(tcyRuns("走了 40 年")).toEqual([{ text: "走了 ", tcy: false }, { text: "40", tcy: true }, { text: " 年", tcy: false }]);
    expect(tcy("第3章")).toEqual(["3"]);
  });
  it("3 位以上、接英文的不直立", () => {
    expect(tcy("1999 年")).toEqual([]);
    expect(tcy("v2")).toEqual([]);
    expect(tcy("COVID19")).toEqual([]);
  });
  it("沒有數字 → 原樣一塊", () => {
    expect(tcyRuns("潮水")).toEqual([{ text: "潮水", tcy: false }]);
  });
});
