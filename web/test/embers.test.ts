import { describe, it, expect } from "vitest";
import { embersByRef } from "../src/data/embers";
import type { Conclusion } from "../src/types";

const mk = (id: string, refs: string[], stale = false): Conclusion =>
  ({ id, kind: "observation", text: id, refs, quotes: [], stale });

describe("embersByRef", () => {
  it("依 refs 把結論攤到每顆節點", () => {
    const map = embersByRef([mk("c1", ["m1", "b1"]), mk("c2", ["m1"])]);
    expect(map["m1"].map(c => c.id)).toEqual(["c1", "c2"]);
    expect(map["b1"].map(c => c.id)).toEqual(["c1"]);
  });
  it("refs=[] 的結論不落任何節點(已知盲點)", () => {
    const map = embersByRef([mk("c1", [])]);
    expect(map).toEqual({});
  });
  it("保留活/冷狀態", () => {
    const map = embersByRef([mk("c1", ["m1"], true)]);
    expect(map["m1"][0].stale).toBe(true);
  });
});
