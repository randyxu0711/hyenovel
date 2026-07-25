import { describe, it, expect } from "vitest";
import { emberMotes } from "../src/lab/BoneStage";
import type { Conclusion } from "../src/types";

const mk = (id: string, stale = false): Conclusion =>
  ({ id, kind: "observation", text: id, refs: ["m1"], quotes: [], stale });

describe("emberMotes", () => {
  it("一條結論一顆、帶 stale、位置確定性", () => {
    const a = emberMotes([mk("c1"), mk("c2", true)], 4);
    expect(a.map(m => m.id)).toEqual(["c1", "c2"]);
    expect(a[1].stale).toBe(true);
    const b = emberMotes([mk("c1"), mk("c2", true)], 4);
    expect(a).toEqual(b);                       // 同輸入同輸出
  });
  it("不同 id 落在不同位置", () => {
    const a = emberMotes([mk("c1"), mk("c2")], 4);
    expect(a[0].dx !== a[1].dx || a[0].dy !== a[1].dy).toBe(true);
  });
});
