import { describe, it, expect } from "vitest";
import { liveQuotes } from "../src/dash/liveQuotes";

/** 規則同 den/spans.py 的 quotes_in:成對「」、內文 2–400 字(code point)、巢狀略過、全標點/空白略過、去重保序。 */
describe("liveQuotes(串流中的引文)", () => {
  it("分段餵:「」收尾那次才回傳", () => {
    const lq = liveQuotes();
    expect(lq.push("她說「潮水")).toEqual([]);
    expect(lq.push("回來」。")).toEqual(["潮水回來"]);
    expect(lq.push("然後")).toEqual([]);
  });
  it("一次收到多段 → 依序回傳", () => {
    expect(liveQuotes().push("「海很藍」和「第二句」")).toEqual(["海很藍", "第二句"]);
  });
  it("太短、太長、全是標點或空白的不回", () => {
    const long = "字".repeat(401);
    expect(liveQuotes().push(`「海」「${long}」「……」「 , 」「  」`)).toEqual([]);
    expect(liveQuotes().push(`「${"字".repeat(400)}」`)).toHaveLength(1);
  });
  it("長度以 code point 算:兩個補充平面字算 2", () => {
    expect(liveQuotes().push("「𠀋𠀋」")).toEqual(["𠀋𠀋"]);
  });
  it("巢狀整段略過(與 quotes_in 一樣:外層到第一個」為止)", () => {
    const lq = liveQuotes();
    expect(lq.push("「外「內文」")).toEqual([]);
    expect(lq.push("尾」「後來」")).toEqual(["後來"]);
  });
  it("同一段第二次出現不再回", () => {
    const lq = liveQuotes();
    expect(lq.push("「海很藍」")).toEqual(["海很藍"]);
    expect(lq.push("又說「海很藍」")).toEqual([]);
  });
});
