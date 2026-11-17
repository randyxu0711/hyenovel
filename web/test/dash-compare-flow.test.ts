import { describe, expect, it } from "vitest";
import type { DelRun } from "../src/dash/api";
import { FOLD_MIN, foldOf, mergeBrackets, overlay, sliceCells } from "../src/dash/compareFlow";
import { cpLength } from "../src/dash/cp";
import { segments } from "../src/dash/Paper";

const del = (id: string, at: number, text: string, pinned = false): DelRun =>
  ({ op: "del", id, at, text, chars: [...text].filter(c => !/\s/.test(c)).length, pinned });
const never = () => false;

describe("overlay", () => {
  it("inserts deleted text before at", () => {
    const [s] = overlay("甲。丙。", "", [del("d0", 2, "乙。")], never);
    expect(s.text).toBe("甲。乙。丙。");
    expect(s.cells[2]).toEqual({ kind: "del", id: "d0", at: 2 });
    expect(s.cells[4]).toEqual({ kind: "text", at: 2 });
    expect(s.start).toBe(0);
  });

  it("marks ins cells", () => {
    const [s] = overlay("甲乙", "", [{ op: "ins", id: "i0", start: 0, end: 1 }], never);
    expect(s.cells.map(c => c.kind)).toEqual(["ins", "text"]);
  });

  it("splits deleted paragraph into its own segment", () => {
    const segs = overlay("甲。\n丙。", "", [del("d0", 3, "乙。\n")], never);
    expect(segs.map(s => s.text)).toEqual(["甲。", "乙。", "丙。"]);
    expect(segs[1].cells.every(c => c.kind === "del")).toBe(true);
    expect(segs.map(s => s.start)).toEqual([0, 3, 3]);
  });

  it("deleted text at the very end", () => {
    const segs = overlay("甲。", "", [del("d0", 2, "\n乙。")], never);
    expect(segs.map(s => s.text)).toEqual(["甲。", "乙。"]);
  });

  it("folded run becomes placeholder", () => {
    const r = del("d0", 1, "長".repeat(40));
    const [s] = overlay("甲乙", "", [r], () => true);
    expect(s.text).toBe("甲" + "\uE000".repeat(5) + "乙");
    expect(s.cells[1]).toEqual({ kind: "fold", id: "d0", at: 1, chars: 40 });
  });

  it("drops runs inside skipped title and keeps segment starts", () => {
    const text = "標題\n甲。\n丙。";
    const segs = overlay(text, "標題", [del("d0", 1, "x"), del("d1", 6, "乙。\n")], never);
    expect(segs.map(s => s.text)).toEqual(["甲。", "乙。", "丙。"]);
    expect(segs[0].start).toBe(segments(text, "標題")[0].start);
  });

  it("counts code points beyond BMP", () => {
    const [s] = overlay("😀甲", "", [{ op: "ins", id: "i0", start: 1, end: 2 }], never);
    expect(s.cells).toEqual([{ kind: "text", at: 0 }, { kind: "ins", id: "i0", at: 1 }]);
  });

  it("trims paragraph whitespace like segments()", () => {
    const [s] = overlay("  甲。 ", "", [], never);
    expect(s.text).toBe("甲。");
    expect(s.start).toBe(2);
    expect(s.cells.length).toBe(cpLength(s.text));
  });
});

describe("sliceCells", () => {
  it("keeps cells aligned and recomputes start", () => {
    const [s] = overlay("甲。丙。", "", [del("d0", 2, "乙。")], never);
    const b = sliceCells(s, 4, 6);
    expect(b.text).toBe("丙。");
    expect(b.cells.length).toBe(cpLength(b.text));
    expect(b.start).toBe(2);
  });
});

describe("foldOf", () => {
  const r = (n: number, pinned = false) => del("d0", 0, "長".repeat(n), pinned);
  it("folds long unpinned only", () => {
    expect(FOLD_MIN).toBe(34);
    expect(foldOf(r(33), false, new Set())).toBe(false);
    expect(foldOf(r(34), false, new Set())).toBe(true);
    expect(foldOf(r(80, true), false, new Set())).toBe(false);
  });
  it("clean folds everything unless opened", () => {
    expect(foldOf(r(2, true), true, new Set())).toBe(true);
    expect(foldOf(r(80), true, new Set(["d0"]))).toBe(false);
    expect(foldOf(r(80), false, new Set(["d0"]))).toBe(false);
  });
});

describe("mergeBrackets", () => {
  it("merges overlapping or near ranges and keeps ids in order", () => {
    expect(mergeBrackets([
      { start: 14, end: 20, ids: ["b"] }, { start: 0, end: 10, ids: ["a"] }, { start: 40, end: 50, ids: ["c"] },
    ])).toEqual([{ start: 0, end: 20, ids: ["a", "b"] }, { start: 40, end: 50, ids: ["c"] }]);
  });
});

