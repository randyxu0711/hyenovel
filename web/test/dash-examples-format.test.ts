import { describe, it, expect } from "vitest";
import { parseExamples } from "../src/dash/examplesFormat";

describe("範例對話解析", () => {
  it("前言 + 每個 <example> 一段;作者/角色分得開", () => {
    const r = parseExamples("聊的是〈冰箱〉。\n\n<example>\n水牛:寫得夠。\n作者:故意的\n</example>\n\n<example>\n作者:怎樣?\n水牛:前半好。\n</example>");
    expect(r).toEqual({
      lead: "聊的是〈冰箱〉。",
      scenes: [
        [{ who: "char", text: "寫得夠。" }, { who: "author", text: "故意的" }],
        [{ who: "author", text: "怎樣?" }, { who: "char", text: "前半好。" }],
      ],
    });
  });
  it("全形冒號、{{user}} 也認;沒說話者的續行接到上一句", () => {
    const r = parseExamples("<example>\n{{user}}：嗨\n鹿：嗯\n還在想\n</example>");
    expect(r!.scenes[0]).toEqual([{ who: "author", text: "嗨" }, { who: "char", text: "嗯\n還在想" }]);
    expect(r!.lead).toBe("");
  });
  it("沒有 <example> 區塊 → null(畫面退回原文)", () => {
    expect(parseExamples("隨便寫的一段")).toBeNull();
    expect(parseExamples("<example>\n\n</example>")).toBeNull();
  });
});
