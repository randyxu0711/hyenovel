import { describe, it, expect } from "vitest";
import { cleanWord, composePlist, parsePlist } from "../src/dash/plistFormat";

describe("每輪提醒拆成詞", () => {
  it("名字或 {{char}} 開頭都拆得開,說話標籤照原文留", () => {
    expect(parsePlist("[鬣狗: 慢條斯理, 固執; 說話: 簡短, 口語]")).toEqual({ traits: ["慢條斯理", "固執"], label: "說話", speech: ["簡短", "口語"] });
    expect(parsePlist("[{{char}}: shy; Speech: slow]")).toEqual({ traits: ["shy"], label: "Speech", speech: ["slow"] });
  });
  it("全形標點與頓號也認", () => {
    expect(parsePlist("[鹿:細心、溫柔;說話:溫和]")).toEqual({ traits: ["細心", "溫柔"], label: "說話", speech: ["溫和"] });
  });
  it("不是這個形狀就不拆,交給文字框", () => {
    expect(parsePlist("話少")).toBeNull();
    expect(parsePlist("[門縫1: 安靜]")).toBeNull();
    expect(parsePlist("[a: b; c: d] 還有尾巴")).toBeNull();
  });
  it("組回去用 {{char}} 開頭,讓改名跟得上;兩邊都空就是空字串", () => {
    expect(composePlist({ traits: ["固執"], label: "說話", speech: ["簡短", "口語"] })).toBe("[{{char}}: 固執; 說話: 簡短, 口語]");
    expect(composePlist({ traits: [], label: "說話", speech: [] })).toBe("");
  });
  it("拆組來回不變詞", () => {
    const p = parsePlist(composePlist({ traits: ["a b", "c"], label: "Speech", speech: ["d"] }));
    expect(p).toEqual({ traits: ["a b", "c"], label: "Speech", speech: ["d"] });
  });
  it("詞裡的分隔字元與巨集括號會被拿掉", () => {
    expect(cleanWord(" 固[執]:;,、{x} ")).toBe("固執x");
  });
});
